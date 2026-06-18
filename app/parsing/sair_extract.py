"""Extract narrator records from سير أعلام النبلاء (الذهبي, ط الرسالة, 10906).

A COVERAGE source covering post-Six-Books men (الأصم-class محدّثون, 5th–8th centuries). Like الجرح/الثقات,
it is a PROSE rijal dictionary with documented شيوخ/تلاميذ network — the key for joint-resolver disambiguation.

**Segmentation (heading-driven).** سير's tarjama heads «N - Name» flow INLINE in the body («… مات سنة ٢٠٠.
١٤٦ - فلان …»), so the line-anchored `rijal_extract._BOUNDARY` caught only ~7 % of them (407 of 5893), and
almost none of the LATE الأصم-class (the whole point of the source). al-Thiqāt got away with `_BOUNDARY`
because its heads are line-anchored AND it maps heading→body BY NUMBER; سير can't — its numbers RESTART each
طبقة and `indexes.numbers` is empty. So here every «N -» in the body is found (inline included) and ALIGNED
to the ordered `indexes.headings` «N - Name» list by number + name-prefix — robust to false «N -» (date ranges
«٢٠٠ - ٢١٠») since a candidate must match the expected heading's number AND the start of its name.

The name comes from the (clean) heading; the body gives the network «حدّث عن … حدّث عنه …» (or «روى عن/عنه»),
the death «مات سنة …», and the quoted جرح/تعديل critics. Grade = weakest cited verdict, else «غير معروف»
(coverage pattern: no inclusion توثيق like الثقات, so no default «ثقة»).
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
    _block_between,
    _names,
    _verdicts,
)
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _death_year
from app.rijal.grades import classify

SAIR_BOOK_ID = 10906
_SOURCE = "سير أعلام النبلاء (الذهبي، ط الرسالة، رقم 10906)"

_WS = re.compile(r"\s+")
_FOOTNOTE = re.compile(r"_{4,}")
_EDIT = re.compile(r"\[[^\]]*\]|\([^)]*\)")
# سير's network markers (verified on the real book's LATE الأصم-class tarjamas): شيوخ by «حدّث عن» /
# «روى عن», تلاميذ by «حدّث/روى عنه» AND — the dominant form — the bare «وعنه». Missing «وعنه» dropped
# most تلاميذ AND (since it ends the شيوخ block) leaked the students into the teachers.
_SHU_SAIR = re.compile(r"(?:حدّ?ث|رو[ىي])\s+عن(?!ه)")
_TAL_SAIR = re.compile(r"(?:حدّ?ث\s+عنه|رو[ىي]\s+عنه|وعنه)")
# Where a network block ends: a transmission/speech verb, a death, a verdict verb («ضعّفه/وثّقه»), or a
# list-terminator («وآخرون/وخلق/وجماعة») — سير closes a تلاميذ list with these BEFORE the critics' verdicts,
# so this keeps a cited critic (أبو حاتم…) from being read as a تلميذ.
_NET_END = re.compile(
    r"سمعت|حدثنا|أخبرنا|أنبأنا|قال|سئل|مات|توفي|قاله|يقال|ذكره|قلت|"
    r"ضعّفه|ضعفه|وثّقه|وثقه|آخرون|وجماعة|وخلق|وغيرهم"
)
# A «N - Name» tarjama heading (in indexes.headings) — «١٤٥ - عمرو بن دينار البصري».
_HEAD = re.compile(r"^\s*([\d٠-٩۰-۹]+)\s*[-–—]\s*(.+)$")
# Every «N -» boundary in the body, INLINE too (not line-anchored). The lookbehind keeps «٤٥» from
# matching inside «٢٤٥»; the alignment to the heading sequence rejects spurious hits (date ranges).
_INLINE_HEAD = re.compile(r"(?<![\d٠-٩۰-۹])([\d٠-٩۰-۹]+)\s*[-–—]\s*")
# Name boundary: where tarjama body text begins (network markers, transmission verbs, verdict/death).
_NAME_END = re.compile(
    r"حدّ?ث|رو[ىي]\s+عنه?|سمعت|أخبرنا|أنبأنا|قال|يقال|مات|توفي|كان|وكان|ذكره|وفي|بل|إن|لكن"
)
_JUNK_HEAD = ("باب", "كتاب", "فصل", "ذكر", "مقدمة", "فأما", "وأما", "أخوه", "وابنه", "ابنه")


def _clean_name(raw: str) -> str | None:
    """Extract a clean name from a raw tarjama head, stopping at a network/verdict marker."""
    name = _EDIT.sub(" ", raw)
    name = _NAME_END.split(name, 1)[0]
    name = _WS.sub(" ", name).strip(" .،:-—*")
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


def _tarjama_heads(data: dict) -> list[tuple[int, str]]:
    """Ordered ``(number, name)`` for every «N - Name» heading — the reliable tarjama list."""
    out: list[tuple[int, str]] = []
    for h in (data.get("indexes") or {}).get("headings") or []:
        m = _HEAD.match(_WS.sub(" ", h.get("title") or "").strip())
        if not m:
            continue
        num, name = arabic_digits_to_int(m.group(1)), _clean_name(m.group(2))
        if num and name and not name.startswith(_JUNK_HEAD):
            out.append((num, name))
    return out


def _segment(full: str, heads: list[tuple[int, str]]) -> Iterator[tuple[str, str]]:
    """Align the ordered heading list to the body's «N -» boundaries and yield ``(name, body)``.

    A heading is matched to the next forward body-boundary whose number equals it AND whose following
    text begins with the heading's name — so a stray «N -» (a date range «٢٠٠ - ٢١٠», a list item) is
    skipped, and the right tarjama body (this boundary → the next matched one) is returned."""
    cands = [(m.start(), arabic_digits_to_int(m.group(1)), m.end()) for m in _INLINE_HEAD.finditer(full)]
    starts: list[int] = []
    ci = 0
    for num, name in heads:
        first = strip_diacritics(name).split()
        prefix = first[0][:4] if first else ""
        found = -1
        cj = ci
        while cj < len(cands):
            pos, cnum, end = cands[cj]
            if cnum == num:
                after = strip_diacritics(full[end : end + 30]).lstrip(" :-،*")
                if not prefix or after.startswith(prefix):
                    found, ci = pos, cj + 1
                    break
            cj += 1
        starts.append(found)
    for i, (num, name) in enumerate(heads):
        s = starts[i]
        if s < 0:
            continue
        e = len(full)
        for j in range(i + 1, len(heads)):
            if starts[j] >= 0:
                e = starts[j]
                break
        yield name, full[s:e]


def parse_entry(number: int | None, body: str, heading_name: str | None = None) -> dict | None:
    """One tarjama → a graded record, or ``None`` for junk / non-narrator entries. The name is taken
    from the (clean) ``heading_name`` when given, else read from the body head."""
    body = _WS.sub(" ", body).strip()
    if len(body) < 8:
        return None
    name = heading_name or _clean_name(body)
    if not name or name.startswith(_JUNK_HEAD):
        return None
    # Network, verdicts, death year.
    shuyukh = _names(_block_between(body, _SHU_SAIR, _TAL_SAIR, _NET_END))
    talamidh = _names(_block_between(body, _TAL_SAIR, _NET_END))
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
    """Yield a graded record for every «N - Name» tarjama in سير أعلام النبلاء (book 10906)."""
    full = book_main_text(data)
    for name, body in _segment(full, _tarjama_heads(data)):
        rec = parse_entry(None, strip_diacritics(body), heading_name=name)
        if rec:
            yield rec


def parse_sair_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/10906.json`` (سير أعلام النبلاء) into graded narrator records."""
    return list(iter_sair(json.loads(Path(path).read_text(encoding="utf-8"))))
