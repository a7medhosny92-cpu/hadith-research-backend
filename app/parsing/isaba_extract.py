"""Extract Companion records from الإصابة في تمييز الصحابة (book 9767).

Ibn Ḥajar's culminating Companion dictionary («جامعٌ لما تفرّق مع تحقيق»). Its structure —
per letter, repeated across the four sections الأسماء/الكنى/النساء/كنى النساء — is four أقسام,
and the قسم IS the grade signal:

  I   ثبتت صحبته بطريق روايةٍ ما            → صحابي
  II  وُلد في العهد النبويّ وله رؤية (إلحاق)  → صحابي
  III المخضرمون: أدركوا ولم يلقوه            → NOT a Companion («ليسوا أصحابه باتفاق») — skipped
  IV  ذُكر في الصحابة غلطًا ووهمًا            → NOT a Companion (Ibn Ḥajar's corrections) — skipped

Extraction reads the book's ``indexes.headings`` — every tarjama is itself a heading
(«٨٢٠٣- مقسم بن بجرة») under its حرف/قسم section headings — NOT the body text, so the long
muqaddima (whose numbered «١-» lists look exactly like tarjamas) and the editor's footnotes
never pollute the records. A small state machine walks the headings in order: «حرف …» opens a
letter (القسم الأول always opens it), «القسم …» switches the قسم, a numbered heading under
قسم I/II yields ``{"name", "grade": "صحابي", "source"}``.

Conservative by design (لا يختلق): a combined section heading («القسم الثاني والثالث») takes the
MOST RESTRICTIVE قسم mentioned (skip rather than mis-grade); unnamed/relational heads («امرأة من
بني فلان»، «ابن اللتبية») and single-token names are dropped — a one-word entry would
containment-match every namesake citation and grade it صحابي.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.normalize import normalize_for_search

ISABA_BOOK_ID = 9767
_SOURCE = "الإصابة في تمييز الصحابة (رقم 9767)"

_WS = re.compile(r"\s+")
# «حرف الألف» / «تتمة حرف العين» / «ذكر بقية حرف الحاء» — a letter opens (its القسم الأول follows).
_HARF = re.compile(r"^(?:تتمة\s+|ذكر\s+بقية\s+)?حرف\s")
# «القسم الأول» / «تتمة القسم الأول» / «وكذا القسم الرابع» / the OCR'd «لقسم الثالث…».
_QISM = re.compile(r"^(?:تتمة\s+|وكذا\s+)?ا?لقسم\s")
_QISM_ORD = {"الأول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4}
_QISM_WORD = re.compile(r"(الأول|الثاني|الثالث|الرابع)")
# A tarjama heading: «٨٢٠٣- مقسم بن بجرة» / «٥٣٣٥ ز- عبيد الله بن مقسم:» («ز» = an added entry).
_HEAD = re.compile(r"^\s*[\d٠-٩۰-۹]+\s*(?:ز)?\s*[-–—]\s*(.+)$")
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|«[^»]*»")
_ANOTHER = re.compile(r"[،,]?\s*آخر\.?$")            # «مقسم، آخر» — the disambiguating tag, not a name
# An alternate-kunya/nasab run «… أو أبو زهير …» / «… أو ابن فلان …»: الإصابة often gives a second
# كنية for the same man inside the heading. Strip the «أو <particle> <token>» so the canonical name
# (and any trailing nisba) stays clean and folds with تقريب, instead of becoming a doubled entry.
_ALT_OR = re.compile(
    r"\s+[أا]و\s+(?:ابن|بن|[أا]ب[ويا]|[أا]م)(?:\s+(?:ابن|بن|[أا]ب[ويا]|[أا]م))?\s+\S+"
)
# Relational/unnamed heads (the مبهمات style) — not matchable names; the famous «ابن فلان»
# designations are already in تقريب under their real names.
_MUBHAM_LEAD = {
    "رجل", "امرأة", "غلام", "جارية", "مولى", "مولاة", "خادم", "ابن", "ابنة", "بنت",
    "أخو", "أخت", "عم", "عمة", "خال", "خالة", "جد", "جدة", "والد", "والدة", "زوج", "زوجة",
}
# A name ENDING on a dangling theophoric/particle is truncated — no real name ends on a bare «عبد»
# (عبد needs its second half: الله/الرحمن…) nor on «بن/أبو/ابن…». «عبد الله بن عبد» (a صحابي heading
# cut short) became a magnet that resolved every «عبد الله بن عبد …» citation to itself (11k+ ×).
_DANGLING_TAIL = {normalize_for_search(w) for w in ("عبد", "بن", "ابن", "أبو", "أبي", "أبا", "أم", "ذو", "ذي", "آل")}


def _clean_name(raw: str) -> str | None:
    """The tarjama head as a matchable name — or ``None`` when it isn't one."""
    name = _BRACKETS.sub(" ", raw)
    name = _WS.sub(" ", name).strip(" :.،-—_")
    name = _ANOTHER.sub("", name).strip(" :.،-—_")
    name = _WS.sub(" ", _ALT_OR.sub(" ", name)).strip(" :.،-—_")  # «أبو الأزهر أو أبو زهير الأنماري»
    tokens = name.split()                                          #   → «أبو الأزهر الأنماري» (the «أو …» dropped)
    if len(tokens) < 2:                      # a one-word entry would over-match every namesake
        return None
    if tokens[0] in _MUBHAM_LEAD:
        return None
    norm = normalize_for_search(name).split()
    if norm and norm[-1] in _DANGLING_TAIL:  # «عبد الله بن عبد» — truncated theophoric/particle tail
        return None
    return name


def iter_isaba(data: dict) -> Iterator[dict]:
    """Yield one Companion record per قسم-I/II tarjama heading, walking the headings in order."""
    harf_seen = False
    qism = 0
    for h in (data.get("indexes") or {}).get("headings") or []:
        title = _WS.sub(" ", h.get("title") or "").strip()
        if not title:
            continue
        if _HARF.match(title):
            harf_seen = True
            qism = 1                          # every letter opens with القسم الأول
            continue
        if _QISM.match(title):
            words = _QISM_WORD.findall(title)
            if words:                         # combined sections → the most restrictive قسم
                qism = max(_QISM_ORD[w] for w in words)
            continue
        if not harf_seen or qism not in (1, 2):
            continue                          # muqaddima, or قسم III (مخضرمون) / IV (وهم)
        m = _HEAD.match(title)
        if not m:
            continue
        name = _clean_name(m.group(1))
        if name:
            yield {"name": name, "grade": "صحابي", "source": _SOURCE}


def parse_isaba_file(path: Path) -> list[dict]:
    """All قسم-I/II Companion records of a downloaded الإصابة json file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(iter_isaba(data))
