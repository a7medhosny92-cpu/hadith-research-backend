"""Extract structured رجال records from تهذيب الكمال (al-Mizzī) — a *prose* biography source.

Unlike تقريب (one terse verdict per man), تهذيب الكمال gives, per narrator: the Six-Books rumūz,
the full name, the **شيوخ** (روى عن) and **تلاميذ** (روى عنه) — a who-from-whom NETWORK — and the
quoted verdicts of many critics. See ``docs/TAHDHIB.md`` for the study this is built on.

The editor's footnotes are pervasive and name OTHER men, so they are dropped FIRST: each raw page is
laid out «main text ____ footnotes», so we keep only the text *before* the first «____» run, then
strip the inline «(N)» reference marks. Everything else parses off the resulting clean main text.

Each record::

    {"number", "books", "name", "kunya", "death_year", "shuyukh", "talamidh", "verdicts"}

where ``books`` are the rumūz tokens (خ م د …), ``shuyukh``/``talamidh`` are name lists (for the
narrator network), and ``verdicts`` are the quoted جرح وتعديل phrases (each a critic's appraisal).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.appraisals import extract_appraisals
from app.parsing.html_clean import arabic_digits_to_int, clean_block, flexible_word
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _BOUNDARY, _death_year, _first_entry_page


def _alt(*words: str) -> str:
    """Diacritic-tolerant regex alternation of whole words (the source is heavily vocalised:
    «رَوَى عَن» must match the bare «روى عن»)."""
    return "|".join(flexible_word(w) for w in words)

# The Six-Books rumūz (and their sub-works) that head a real tarjama; «تمييز» marks a man listed
# only to disambiguate (NOT one of the Six Books' narrators).
_BOOKS = set("خ م د ت س ق ع ٤ ر ص".split()) | {
    "بخ", "خت", "سي", "مد", "قد", "عخ", "عس", "فق", "كن", "لت", "تم", "كد", "مق", "تمييز",
}

_FOOTNOTE = re.compile(r"_{4,}")                       # «_________» — the footnote separator
_REF = re.compile(r"\s*\([٠-٩0-9]+\)")                 # inline footnote refs «(٢)»
_PAREN = re.compile(r"\s*\([^)]*\)")                   # «(رموز)» after a شيخ/تلميذ name
# شيوخ opener: full «رَوَى عَن:» or the abbreviated «عَن:» minor entries use — the COLON is required
# so the chain-word «عَنْ فلان» (no colon) is never mistaken for the block opener.
_SHU = re.compile("(?:%s)" % _alt("روى عن", "وروى عن", "حدث عن", "عن") + r"\s*:")
# تلاميذ opener: «رَوَى عَنه:» / «وَرَوَى عَنه:» or the abbreviated «وعَنه:» / «عَنه:».
_TAL = re.compile("(?:%s)" % _alt("روى عنه", "وروى عنه", "وعنه", "عنه") + r"\s*:")
# Where the head's NAME ends and the biography begins: a block opener (needs the colon) or a
# biography word. Diacritised throughout.
_NAME_END = re.compile(
    r"\s*(?:"
    + "(?:%s)\\s*:" % _alt("روى عن", "وروى عن", "روى عنه", "روى له", "حدث عن", "عن", "عنه")
    + "|(?:%s)\\b" % _alt("قال", "وقال", "مات", "توفي", "توفى", "وكان", "كان", "ذكره",
                          "وفد", "نزيل", "نزل", "سكن", "أصله", "يقال", "له صحبة")
    + r")"
)
_KUNYA = re.compile(r"(?<!\S)(%s)\s+(\S+)" % _alt("أبو", "أبي", "أبا", "أم"))
# A «قال … : <appraisal>» verdict line; we keep only appraisals carrying a grade word.
_VERDICT = re.compile(
    r"(?:^|[\s.،])(?:%s)\b[^:.\n]{0,55}?:\s*([^.\n]{2,90})" % _alt("قال", "وقال", "قاله")
)
_GRADE_WORDS = ("ثقة", "ثبت", "حافظ", "صدوق", "لا بأس", "ليس به بأس", "صالح", "مقبول", "مستور",
                "لين", "ضعيف", "ليس بثقة", "لا يحتج", "منكر", "متروك", "كذاب", "مجهول", "وضاع",
                "حجة", "إمام", "صحابي")
# Where the تلاميذ list ends and the appraisals / death notice begin.
_TAL_END = re.compile(r"(?:%s)\b" % _alt("قال", "وقال", "مات", "توفي", "توفى", "روى له", "قلت"))
_WS = re.compile(r"\s+")
# A 5th-century-or-later death notice — in words (أربع…تسعمائة) or digits (سنة 4xx–9xx). No Six-Books
# transmitter dies that late; this marks a non-narrator biographee. (_death_year caps at the early
# centuries and returns None for these, so the AUTHOR al-Mizzī's ت742/734 needs its own marker.)
_LATE_FIGURE = re.compile(
    r"(?:أربع|خمس|ست|سبع|ثمان|تسع)\s*م[ئا]ة"
    r"|سنة\s*\D{0,10}[٤-٩4-9][٠-٩0-9]{2}"
)


def book_main_text(data: dict) -> str:
    """Footnote-free, diacritic-free main text of the whole book (from the first numbered entry).

    Cuts each page at the first «____» (dropping the editor's footnotes), joins, strips the inline
    «(N)» refs, and folds the tashkeel — leaving clean prose the entry parser reads."""
    start = _first_entry_page(data)
    pages = [p for p in data.get("pages", []) if start is None or p.get("pg", 0) >= start]
    main = "\n".join(
        _FOOTNOTE.split(clean_block(p.get("text") or ""), 1)[0]
        for p in sorted(pages, key=lambda p: p.get("pg", 0))
    )
    return _REF.sub("", main)   # keep tashkeel + newlines here; bodies are folded per-entry


def _names(block: str) -> list[str]:
    """Split a «X (رموز)، وY، وZ» شيوخ/تلاميذ run into clean name strings."""
    out: list[str] = []
    for part in _PAREN.sub("", block).split("،"):
        name = _WS.sub(" ", part).strip(" .\n")
        if name.startswith("و"):
            name = name[1:].strip()
        if len(name) >= 3:
            out.append(name)
    return out


def _block_between(body: str, start: re.Pattern, *ends: re.Pattern) -> str:
    """The text from after ``start`` up to the earliest of ``ends`` (or the body end)."""
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
    """The quoted جرح وتعديل appraisals (a «قال …: <appraisal>» carrying a grade word)."""
    out: list[str] = []
    for m in _VERDICT.finditer(body):
        phrase = m.group(1).strip(" ،")
        folded = strip_diacritics(phrase)               # «ثِقَةٌ» must match the bare «ثقة»
        if any(w in folded for w in _GRADE_WORDS) and phrase not in out:
            out.append(phrase)
    return out


def parse_entry(number: int | None, body: str) -> dict | None:
    """Turn one تهذيب tarjama body (already footnote-free) into a record, or ``None`` if junk."""
    body = _WS.sub(" ", body).strip()
    if len(body) < 8:
        return None
    colon = body.find(":")
    rumuz, rest = (body[:colon], body[colon + 1:]) if 0 <= colon <= 40 else ("", body)
    books = [t for t in rumuz.split() if t in _BOOKS]
    name = _NAME_END.split(rest.strip(" ،."), 1)[0].strip(" ،.")
    if len(name) < 3:
        return None
    # Skip a NON-narrator: al-Mizzī (the AUTHOR himself) and other late biographees the book/muqaddima
    # describes. A Six-Books transmitter never carries an «X الدين» honorific (a 5th-c.+ laqab) nor dies
    # in the 5th c.+ — so «جمال الدين أبو الحجاج … المزي» (ت742) and «أبا الحجاج المزي» (ت734) leaked in
    # as رجال entries (with panegyric «الإمام … محدث الشام» mis-read as a grade). These markers drop them.
    if "الدين" in name.split() or _LATE_FIGURE.search(body):
        return None
    record: dict = {"number": number, "books": books, "name": name}
    kunya = _KUNYA.search(name)
    if kunya:
        record["kunya"] = f"{kunya.group(1)} {kunya.group(2)}"
    year = _death_year(body)
    if year:
        record["death_year"] = year
    shuyukh = _names(_block_between(body, _SHU, _TAL))
    talamidh = _names(_block_between(body, _TAL, _TAL_END))
    if shuyukh:
        record["shuyukh"] = shuyukh
    if talamidh:
        record["talamidh"] = talamidh
    verdicts = _verdicts(body)
    if verdicts:
        record["verdicts"] = verdicts
    appraisals = extract_appraisals(body)            # «قال ابن معين: ثقة» → named أقوال الأئمة
    if appraisals:
        record["appraisals"] = appraisals
    return record


def _muqaddima_skip(have_books: list[bool]) -> int:
    """Index of the first REAL tarjama, skipping the editor's ~200-page introduction.

    The book has no ``numbers`` index, so ``book_main_text`` keeps the محقق's muqaddima (how he
    prepared the edition — al-Mizzī's life, method, a numbered bibliography, praise quotes). Its
    numbered points are prose / book-titles with no rumūz, whereas the dictionary proper is a
    dense run of narrator entries that DO carry the Six-Books symbols. Return the first index
    where a short window is mostly rumūz-bearing entries — the start of the dictionary."""
    win = 15
    for i in range(len(have_books) - win):
        if sum(have_books[i:i + win]) >= 12:
            return i
    return 0


def iter_tahdhib(data: dict) -> Iterator[dict]:
    """Yield a structured record for every numbered tarjama in a downloaded تهذيب الكمال book."""
    full = book_main_text(data)
    bounds = [m for m in _BOUNDARY.finditer(full) if m.group(1) is not None]
    nums = [arabic_digits_to_int(m.group(1)) for m in bounds]
    records = [
        parse_entry(nums[i], full[m.end():(bounds[i + 1].start() if i + 1 < len(bounds) else len(full))])
        for i, m in enumerate(bounds)
    ]
    start = _muqaddima_skip([bool(r and r.get("books")) for r in records])
    for record in records[start:]:
        if record:
            yield record


def parse_tahdhib_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/3722.json`` (تهذيب الكمال) into narrator records."""
    return list(iter_tahdhib(json.loads(Path(path).read_text(encoding="utf-8"))))
