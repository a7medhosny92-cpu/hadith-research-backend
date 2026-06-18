"""Extract narrator records from سير أعلام النبلاء (الذهبي, ط الرسالة, 10906).

A COVERAGE source covering post-Six-Books men (الأصم-class محدّثون, 5th–8th centuries). Like الجرح/الثقات,
it is a PROSE rijal dictionary with documented شيوخ/تلاميذ network — the key for joint-resolver disambiguation.
Format: numbered tarjamas via line-start «N -» (rijal_extract._BOUNDARY), NO headings index, طبقة restart.
Network is written with the standard markers: «حدّث عن … حدّث عنه …» (same as الجرح) or possibly «روى عن/عنه»
variants. Verdicts are quoted جرح/تعديل critics. Grade = weakest cited verdict, else «غير معروف» (coverage pattern).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.appraisals import extract_appraisals
from app.parsing.html_clean import arabic_digits_to_int, clean_block
from app.parsing.jarh_extract import (
    _KUNYA,
    _SHU,
    _TAL,
    _TAL_END,
    _block_between,
    _names,
    _verdicts,
)
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _BOUNDARY, _death_year
from app.rijal.grades import classify

SAIR_BOOK_ID = 10906
_SOURCE = "سير أعلام النبلاء (الذهبي، ط الرسالة، رقم 10906)"

_WS = re.compile(r"\s+")
_FOOTNOTE = re.compile(r"_{4,}")
_EDIT = re.compile(r"\[[^\]]*\]|\([^)]*\)")
# سير may use «حدّث عن» as well as «روى عن»; both patterns are checked.
_SHU_SAIR = re.compile(r"(?:حدّ?ث|رو[ىي])\s+عن(?!ه)")
_TAL_SAIR = re.compile(r"(?:حدّ?ث|رو[ىي])\s+عنه")
# Name boundary: where tarjama body text begins (network markers, transmission verbs, حدّث/روى, verdict/death).
_NAME_END = re.compile(
    r"حدّ?ث|رو[ىي]\s+عنه?|سمعت|أخبرنا|أنبأنا|قال|يقال|مات|توفي|كان|وكان|ذكره|وفي|بل|إن|لكن"
)


def _clean_name(raw: str) -> str | None:
    """Extract a clean name from a raw tarjama head, stopping at a network/verdict marker."""
    name = _EDIT.sub(" ", raw)
    name = _NAME_END.split(name, 1)[0]
    name = _WS.sub(" ", name).strip(" .،:-—")
    return name if len(name.split()) >= 2 else None


def _grade_from(verdicts: list[str]) -> str:
    """The rijal grade: WEAKEST cited جرح/تعديل verdict (الجرح المفسَّر مقدَّم), else «غير معروف»
    (coverage pattern: no inclusion توثيق like الثقات, so no default «ثقة»)."""
    graded = [(rank, v) for v in verdicts if (rank := classify(v)[1]) is not None]
    return min(graded, key=lambda g: g[0])[1] if graded else "غير معروف"


def book_main_text(data: dict) -> str:
    """Full cleaned text of the book, skipping footnotes (editor's notes on «____» boundaries)."""
    pages = sorted(data.get("pages", []), key=lambda p: p.get("pg", 0))
    return "\n".join(
        _FOOTNOTE.split(clean_block(p.get("text") or ""), 1)[0] for p in pages
    )


def parse_entry(number: int | None, body: str) -> dict | None:
    """One tarjama → a graded record, or ``None`` for junk / non-narrator entries."""
    body = _WS.sub(" ", body).strip()
    if len(body) < 8:
        return None
    name = _clean_name(body)
    if not name or name.startswith(("باب", "كتاب", "فصل", "ذكر", "مقدمة")):
        return None
    # Network, verdicts, death year.
    shuyukh = _names(_block_between(body, _SHU_SAIR, _TAL_SAIR, _TAL_END))
    talamidh = _names(_block_between(body, _TAL_SAIR, _TAL_END))
    verdicts = _verdicts(body)
    record: dict = {"number": number, "name": name, "grade": _grade_from(verdicts), "source": _SOURCE}
    kunya = _KUNYA.search(name)
    if kunya:
        record["kunya"] = f"{kunya.group(1)} {kunya.group(2)}"
    year = _death_year(body)
    if year:
        record["death_year"] = year
    if shuyukh:
        record["shuyukh"] = shuyukh
    if talamidh:
        record["talamidh"] = talamidh
    if verdicts:
        record["verdicts"] = verdicts
    appraisals = extract_appraisals(body)
    if appraisals:
        record["appraisals"] = appraisals
    return record


def iter_sair(data: dict) -> Iterator[dict]:
    """Yield a graded record for every tarjama in سير أعلام النبلاء (book 10906)."""
    full = book_main_text(data)
    bounds = [m for m in _BOUNDARY.finditer(full) if m.group(1) is not None]
    for i, m in enumerate(bounds):
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(full)
        num = arabic_digits_to_int(m.group(1))
        rec = parse_entry(num, strip_diacritics(full[m.end() : end]))
        if rec:
            yield rec


def parse_sair_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/10906.json`` (سير أعلام النبلاء) into graded narrator records."""
    return list(iter_sair(json.loads(Path(path).read_text(encoding="utf-8"))))
