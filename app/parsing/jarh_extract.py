"""Extract narrator records from الجرح والتعديل لابن أبي حاتم (book 2170).

An early, **independent** multi-critic رجال source — full names + a شيوخ/تلاميذ network + many quoted
critic verdicts — covering men **beyond the Six Books**. Genuinely new signal vs تقريب/الكاشف/تهذيب,
so it feeds ``build_graph`` (network → «مشترك» disambiguation) and the rijal double-opinion (verdicts).

Format: numbered entries, **no rumūz**, and a network written **without a colon**, names joined by «و»::

    ١٥٤١ - بشير بن كعب بصري أبو أيوب العدوي روى عن أبي الدرداء وأبي ذر روى عنه طلق بن حبيب والعلاء ...
    حدثنا عبد الرحمن … قال عليّ بن المديني: … سمعت أبي يقول: … ثقة

So the boundary is the numbered head (shared with تهذيب), but the شيوخ/تلاميذ blocks open on «روى عن»
/ «روى عنه» (no colon) and split on the conjunction «و», and verdicts sit inside «… قال فلان: …» lines.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.html_clean import arabic_digits_to_int, clean_block
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _BOUNDARY, _death_year, _first_entry_page

_WS = re.compile(r"\s+")
_FOOTNOTE = re.compile(r"_{4,}")                         # «_________» — the editor's footnote separator
_EDIT = re.compile(r"\[[^\]]*\]|\([^)]*\)")              # editor annotations «[معروف - ١]» / «(٢٦ م ٢)»
_SHU = re.compile(r"رو[ىي]\s+عن(?!ه)")                  # «روى عن» — NOT «روى عنه»
_TAL = re.compile(r"رو[ىي]\s+عنه")                      # «روى عنه»
# Where the head NAME ends and the body begins.
_NAME_END = re.compile(r"رو[ىي]\s+عنه?|سمعت|حدثنا|أخبرنا|\bنا\b|قال|يقال|مات|توفي|كان|وكان|ذكره|سئل")
# Where the تلاميذ run ends (a verdict/isnad/next clause begins).
_TAL_END = re.compile(r"سمعت|حدثنا|أخبرنا|قال|سئل|مات|توفي|وهو|قاله|يقال|ذكره")
_KUNYA = re.compile(r"(?<!\w)(أبو|أبي|أبا|أم)\s+(\S+)")
# A quoted appraisal: «قال [critic]: <verdict>» / «سمعت أبي يقول: <verdict>», kept if it carries a grade.
_VERDICT = re.compile(r"(?:قال|قاله|سمعت)\b[^:.\n]{0,40}?:\s*([^.\n]{2,90})")
_GRADE_WORDS = ("ثقة", "ثبت", "حافظ", "صدوق", "لا بأس", "ليس به بأس", "صالح", "مقبول", "مستور",
                "لين", "ضعيف", "ليس بثقة", "لا يحتج", "منكر", "متروك", "كذاب", "مجهول", "وضاع",
                "حجة", "إمام", "صحابي", "محله الصدق", "شيخ", "لا يعرف", "مرسل")


def book_main_text(data: dict) -> str:
    """Footnote-free clean text of the whole book from the first numbered entry (skips the مقدمة).

    Each raw page is «main text ____ footnotes»; we keep only the text before the first «____» run,
    so the editor's notes (which name OTHER men / printings) never leak into a narrator's record."""
    start = _first_entry_page(data)
    pages = [p for p in data.get("pages", []) if start is None or p.get("pg", 0) >= start]
    return "\n".join(
        _FOOTNOTE.split(clean_block(p.get("text") or ""), 1)[0]
        for p in sorted(pages, key=lambda p: p.get("pg", 0))
    )


def _names(block: str) -> list[str]:
    """Split a «X وY والz» شيوخ/تلاميذ run into clean name strings (conjunction «و»-separated)."""
    block = _EDIT.sub(" ", block)
    out: list[str] = []
    for part in re.split(r"\s+و|،", block):
        name = _WS.sub(" ", part).strip(" .،\n")
        if len(name) >= 3 and not name.startswith(("سمعت", "قال", "حدثنا")):
            out.append(name)
    return out


def _block_between(body: str, start: re.Pattern, *ends: re.Pattern) -> str:
    m = start.search(body)
    if not m:
        return ""
    rest = body[m.end():]
    cut = len(rest)
    for end in ends:
        e = end.search(rest)
        if e:
            cut = min(cut, e.start())
    return rest[:cut]


def _verdicts(body: str) -> list[str]:
    out: list[str] = []
    for m in _VERDICT.finditer(body):
        phrase = _WS.sub(" ", m.group(1)).strip(" ،")
        if any(w in phrase for w in _GRADE_WORDS) and phrase not in out:
            out.append(phrase)
    return out[:8]


def parse_entry(number: int | None, body: str) -> dict | None:
    """Turn one الجرح والتعديل tarjama body into a record, or ``None`` if junk."""
    body = _WS.sub(" ", _EDIT.sub(" ", body)).strip()
    if len(body) < 8:
        return None
    name = _NAME_END.split(body, 1)[0].strip(" ،.")
    if len(name) < 4 or name.startswith(("باب", "كتاب", "فصل")):
        return None
    record: dict = {"number": number, "name": name}
    kunya = _KUNYA.search(name)
    if kunya:
        record["kunya"] = f"{kunya.group(1)} {kunya.group(2)}"
    year = _death_year(body)
    if year:
        record["death_year"] = year
    shuyukh = _names(_block_between(body, _SHU, _TAL, _TAL_END))
    talamidh = _names(_block_between(body, _TAL, _TAL_END))
    if shuyukh:
        record["shuyukh"] = shuyukh
    if talamidh:
        record["talamidh"] = talamidh
    verdicts = _verdicts(body)
    if verdicts:
        record["verdicts"] = verdicts
    return record


def iter_jarh(data: dict) -> Iterator[dict]:
    """Yield a structured record for every numbered tarjama in الجرح والتعديل (book 2170)."""
    full = book_main_text(data)
    bounds = [m for m in _BOUNDARY.finditer(full) if m.group(1) is not None]
    for i, m in enumerate(bounds):
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(full)
        record = parse_entry(arabic_digits_to_int(m.group(1)), strip_diacritics(full[m.end():end]))
        if record:
            yield record


def parse_jarh_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/2170.json`` (الجرح والتعديل) into narrator records."""
    return list(iter_jarh(json.loads(Path(path).read_text(encoding="utf-8"))))
