"""Extract narrator records from الثقات ممن لم يقع في الكتب الستة (ابن قطلوبغا, 96165).

A COVERAGE source: trustworthy narrators OUTSIDE the Six Books, to pull men out of «مجهول». The format
is the same PROSE as الجرح (a name, then «يروي عن… روى عنه…», quoted «قال فلان: …» verdicts, footnotes at
«____»), so it reuses jarh_extract's field helpers (network, verdicts) + appraisals. The one thing الجرح
doesn't do — and الثقات must — is GRADE the men it adds: inclusion in a «ثقات» compilation is a توثيق, but a
cited critic may DISAGREE («ذكره في الثقات» yet «قال أبو حاتم: ضعيف»). Following «الجرحُ المفسَّر مقدَّمٌ على
التعديل», the grade is the WEAKEST cited جرح/تعديل verdict when any is present, else «ثقة» by inclusion; the
NAMED verdicts are kept verbatim in ``appraisals`` (أقوال الأئمة) so the dossier shows the disagreement.

Two real quirks of this book are handled here:
  * the name is often only in the «N - Name» HEADING, not the body (whose text opens «. سمع وحدث…») — so
    the heading name is used when present (authoritative & clean), the body name otherwise;
  * a dedicated name boundary (the book writes «يَروي عن» in the PRESENT — jarh is tuned to the past «روى»,
    which would leave a dangling «ي» — and a relational tail «أخو فلان / من أهل …») keeps the name clean;
  * the محقق's long muqaddima carries numbered «N -» items too (his source-list «قضاء الوطر…», the dirasa
    sections) — so an entry is kept only with a real-tarjama SIGNAL (a network, «سمع/يروي/روى», a verdict).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.appraisals import extract_appraisals
from app.parsing.html_clean import arabic_digits_to_int
from app.parsing.jarh_extract import _KUNYA, _SHU, _TAL, _TAL_END, _block_between, _names, _verdicts, book_main_text
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _BOUNDARY, _death_year
from app.rijal.grades import classify

THIQAT_BOOK_ID = 96165
_SOURCE = "الثقات ممن لم يقع في الكتب الستة (رقم 96165)"

_WS = re.compile(r"\s+")
_HEAD = re.compile(r"^\s*([\d٠-٩۰-۹]+)\s*-\s*(.+)$")        # «٥٠١٨ - شافع بن علي …»
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|«[^»]*»")
_SIGNAL = re.compile(r"يروي|رو[ىي]|سمع")                    # a real tarjama (not a محقق book-title)
# Where the head NAME ends and the body begins — incl. the PRESENT «يروي» and a relational tail.
_NAME_END = re.compile(r"يروي|رو[ىي]\s+عنه?|سمع|حدث|قال|يقال|مات|توفي|وكان|كان|ذكر|سئل|أخو|أخت|من أهل|نزيل")


def _clean_name(raw: str) -> str | None:
    name = _BRACKETS.sub(" ", raw)
    name = _NAME_END.split(name, 1)[0]
    name = _WS.sub(" ", name).strip(" .،:-—")
    return name if len(name.split()) >= 2 else None


def _heading_names(data: dict) -> dict[int, str]:
    """``{tarjama-number → name}`` from the «N - Name» headings — the clean, authoritative name."""
    out: dict[int, str] = {}
    for h in (data.get("indexes") or {}).get("headings") or []:
        m = _HEAD.match(_WS.sub(" ", h.get("title") or "").strip())
        if not m:
            continue
        num, name = arabic_digits_to_int(m.group(1)), _clean_name(m.group(2))
        if num and name and num not in out:
            out[num] = name
    return out


def _grade_from(verdicts: list[str]) -> str:
    """The rijal grade: the WEAKEST cited جرح/تعديل verdict (الجرح المفسَّر مقدَّم), else «ثقة» by
    inclusion in «الثقات»."""
    graded = [(rank, v) for v in verdicts if (rank := classify(v)[1]) is not None]
    return min(graded, key=lambda g: g[0])[1] if graded else "ثقة"


def parse_entry(number: int | None, body: str, heading_name: str | None = None) -> dict | None:
    """One tarjama → a graded record, or ``None`` for junk / a محقق book-title."""
    body = _WS.sub(" ", body).strip()
    if len(body) < 8:
        return None
    name = heading_name or _clean_name(body)
    if not name or name.startswith(("باب", "كتاب", "فصل")):
        return None
    shuyukh = _names(_block_between(body, _SHU, _TAL, _TAL_END))
    talamidh = _names(_block_between(body, _TAL, _TAL_END))
    verdicts = _verdicts(body)
    if not (shuyukh or talamidh or verdicts or _SIGNAL.search(body)):
        return None                                  # a محقق book-title / dirasa section — not a narrator
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


def iter_thiqat(data: dict) -> Iterator[dict]:
    """Yield a graded record for every real tarjama in الثقات (book 96165)."""
    names = _heading_names(data)
    full = book_main_text(data)
    bounds = [m for m in _BOUNDARY.finditer(full) if m.group(1) is not None]
    for i, m in enumerate(bounds):
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(full)
        num = arabic_digits_to_int(m.group(1))
        rec = parse_entry(num, strip_diacritics(full[m.end():end]), names.get(num))
        if rec:
            yield rec


def parse_thiqat_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/96165.json`` (الثقات) into graded narrator records."""
    return list(iter_thiqat(json.loads(Path(path).read_text(encoding="utf-8"))))
