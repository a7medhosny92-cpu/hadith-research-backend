"""Extract narrator records from لسان الميزان (ابن حجر, expanding al-Dhahabī's ميزان — ت أبي غدة, 36357).

The WEAK and criticised men OUTSIDE the Six Books — a COVERAGE source that adds their شيوخ/تلاميذ network
(the resolver's lever) and the critics' verdicts. The format is the same PROSE as الجرح/الثقات (the NAME in
the «N - … - Name» heading, then «روى عن … وعنه …», quoted «قال فلان: …» verdicts), so it reuses
jarh_extract's field helpers + thiqat_extract's heading machinery. Two real differences from الثقات:

  * the heading carries a رمز between the number and the name — «١ - ز - أبان بن أرقم …» (ز = من زيادات ابن
    حجر على الذهبي, ذ = …) — stripped here; the name comes from the (clean) heading, never the body, whose
    text opens «N - [مصادر المحقق] … روى عن …» with no ism+father;
  * it does NOT grade by inclusion (لسان is الضعفاء, not a ثقات compilation): the grade is the WEAKEST cited
    جرح/تعديل verdict when present, else «غير معروف» — the man is added for his NETWORK, not a guessed grade
    (لسان keeps men Ibn Ḥajar DEFENDS too, so «ضعيف by inclusion» would be wrong).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.appraisals import extract_appraisals
from app.parsing.html_clean import arabic_digits_to_int
from app.parsing.jarh_extract import (_KUNYA, _SHU, _TAL_END, _block_between, _names, _verdicts,
                                      book_main_text)
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _BOUNDARY, _death_year
from app.parsing.thiqat_extract import _SIGNAL, _clean_name
from app.rijal.grades import classify

LISAN_BOOK_ID = 36357
_SOURCE = "لسان الميزان (رقم 36357)"

_WS = re.compile(r"\s+")
# «١ - ز - أبان بن أرقم …» / «٥ - أبان بن جبلة …»: a number, an OPTIONAL single-letter رمز, then the name.
# (the optional رمز group only matches a lone letter FOLLOWED BY a dash, so «أبان» — أ+بان — never matches.)
_HEAD = re.compile(r"^\s*([\d٠-٩۰-۹]+)\s*-\s*(?:[ء-ي]\s*-\s*)?(.+)$")
# لسان writes تلاميذ as the abbreviated «وعنه …» (الجرح uses «روى عنه»); accept both.
_TAL = re.compile(r"رو[ىي]\s+عنه|وعنه")


def _heading_names(data: dict) -> dict[int, str]:
    """``{tarjama-number → name}`` from the «N - [رمز] - Name» headings — the clean, authoritative name."""
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
    """The WEAKEST cited جرح/تعديل verdict (الجرحُ المفسَّر مقدَّم); لسان does NOT grade by inclusion, so with
    no verdict the man is «غير معروف» (added for his network, not a guessed grade)."""
    graded = [(rank, v) for v in verdicts if (rank := classify(v)[1]) is not None]
    return min(graded, key=lambda g: g[0])[1] if graded else "غير معروف"


def parse_entry(number: int | None, body: str, heading_name: str | None = None) -> dict | None:
    """One tarjama → a record, or ``None`` for junk / a محقق book-title (the muqaddima's «N -» items)."""
    body = _WS.sub(" ", body).strip()
    if len(body) < 8:
        return None
    name = heading_name or _clean_name(body)
    if not name or name.startswith(("باب", "كتاب", "فصل", "حرف")):
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


def iter_lisan(data: dict) -> Iterator[dict]:
    """Yield a record for every real tarjama in لسان الميزان (book 36357)."""
    names = _heading_names(data)
    full = book_main_text(data)
    bounds = [m for m in _BOUNDARY.finditer(full) if m.group(1) is not None]
    for i, m in enumerate(bounds):
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(full)
        num = arabic_digits_to_int(m.group(1))
        rec = parse_entry(num, strip_diacritics(full[m.end():end]), names.get(num))
        if rec:
            yield rec


def parse_lisan_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/36357.json`` (لسان الميزان) into narrator records."""
    return list(iter_lisan(json.loads(Path(path).read_text(encoding="utf-8"))))
