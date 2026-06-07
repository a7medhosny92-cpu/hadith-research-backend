"""Extract structured hadith records from a downloaded turath book.

A book is a list of pages (``{"pg", "meta": {...}, "text"}``). Hadith are marked
inline; the marker style varies by edition, so we detect it per book:

* style **bullet** — ``• [N]``  (e.g. صحيح البخاري ط التأصيل)
* style **dash**   — ``N - …``  (صحيح مسلم، السنن، …)

A single hadith may span several pages, so we scan the page stream and accumulate
across page breaks, tracking the chapter (bab) heading and the starting page for
citation, and skipping the editor's muqaddima via the book ``numbers`` index.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Pattern

from app.parsing.grading import extract_grade, grade_in_ruling
from app.parsing.html_clean import (
    arabic_digits_to_int,
    clean_block,
    extract_s0_grades,
    extract_titles,
    remove_footnote_refs,
    split_footnotes,
)
from app.parsing.isnad_matn import split_isnad_matn
from app.parsing.normalize import normalize_for_search

_NUM = r"[\d٠-٩۰-۹]+"
# "• [N]" bullet (a "* [N]" line is a takhrij note, not a hadith — we anchor on •).
_MARKER_BULLET: Pattern[str] = re.compile(rf"(?:^|\n)[ \t]*•\s*\[\s*({_NUM})\s*\]")
# "N - " at the start of a line.
_MARKER_DASH: Pattern[str] = re.compile(rf"(?:^|\n)[ \t]*({_NUM})\s*-\s+")
# A leading sub-number like "(١)" some editions print after the hadith number.
_LEADING_SUBNUM = re.compile(rf"^\s*\(\s*{_NUM}\s*\)\s*")
_WS = re.compile(r"\s+")
# A dash marker «N - باب …» is a chapter heading printed as a numbered line in some
# editions, not a hadith — recognise it by its leading word so it isn't emitted.
_HEADING_WORDS = {"باب", "كتاب", "فصل", "جماع", "ابواب", "مقدمه"}
# A reference entry repeats the previous hadith's matn through a new chain
# («…مثله» / «…نحوه» / «بهذا الإسناد» / «عن فلانٍ بذلك»). Detected near the text's end.
_RIMANDO = re.compile(r"مثل|نحو|بمعنا|بذلك|بهذا")


@dataclass(slots=True)
class ParsedHadith:
    book_id: int
    number: int | None
    text: str            # full hadith text (isnad + matn), diacritics preserved
    isnad: str
    matn: str
    matn_confidence: str  # quote | phrase | none
    grade: str | None
    chapter: str | None
    volume: str | None
    page: int | None      # printed page (for citation)
    page_id: int | None   # turath sequential page id

    def to_dict(self) -> dict:
        return asdict(self)


def _finish(book_id: int, cur: dict, default_grade: str | None) -> ParsedHadith:
    text = _WS.sub(" ", " ".join(cur["parts"])).strip()
    isnad, matn, confidence = split_isnad_matn(text)
    grade = extract_grade(text) or grade_in_ruling(cur.get("grade_hint")) or default_grade
    return ParsedHadith(
        book_id=book_id,
        number=cur["number"],
        text=text,
        isnad=isnad,
        matn=matn,
        matn_confidence=confidence,
        grade=grade,
        chapter=cur["chapter"],
        volume=cur["volume"],
        page=cur["page"],
        page_id=cur["page_id"],
    )


_DASH_PROBE = re.compile(rf"(?:^|\n)[ \t]*{_NUM}\s*-\s")


def _detect_marker(pages: list[dict], start_page_id: int | None = None) -> Pattern[str]:
    """Pick the marker style for this book by comparing how often each style occurs.

    Sample **content** pages only: the editor's muqaddima often contains dash-style
    numbered lists ("٤ - …") that would otherwise mask the real "• [N]" markers.
    """
    content = [p for p in pages if start_page_id is None or p.get("pg", 0) >= start_page_id]
    text = "\n".join(p.get("text", "") for p in content[:50])
    bullets = text.count("• [")
    dashes = len(_DASH_PROBE.findall(text))
    return _MARKER_BULLET if bullets > 0 and bullets >= dashes else _MARKER_DASH


def iter_hadith(
    book_id: int,
    pages: Iterable[dict],
    *,
    default_grade: str | None = None,
    start_page_id: int | None = None,
) -> Iterator[ParsedHadith]:
    """Yield :class:`ParsedHadith` for every hadith marker in the book.

    ``start_page_id`` skips front matter (the editor's muqaddima, which quotes hadith
    out of sequence): pass the page id where the real numbered text begins.
    """
    pages = list(pages)
    marker = _detect_marker(pages, start_page_id)
    current: dict | None = None
    chapter: str | None = None

    for page in sorted(pages, key=lambda p: p.get("pg", 0)):
        pg = page.get("pg", 0)
        if start_page_id is not None and pg < start_page_id:
            continue
        meta = page.get("meta") or {}
        raw = page.get("text") or ""

        body, footnotes = split_footnotes(raw)
        titles = extract_titles(body) or (meta.get("headings") or [])
        if titles:
            chapter = remove_footnote_refs(titles[-1]).strip()
        page_grades = extract_s0_grades(footnotes) or extract_s0_grades(raw)
        block = clean_block(body)

        matches = list(marker.finditer(block))
        if not matches:
            if current is not None:
                current["parts"].append(block)
            continue

        prefix = block[: matches[0].start()]
        if current is not None and prefix.strip():
            current["parts"].append(prefix)

        for i, match in enumerate(matches):
            if current is not None:
                yield _finish(book_id, current, default_grade)
            end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
            grade_hint = page_grades[i] if i < len(page_grades) else None
            segment = _LEADING_SUBNUM.sub("", block[match.end():end], count=1)
            head = normalize_for_search(segment[:40]).split()
            if head and head[0] in _HEADING_WORDS:   # a numbered «باب/كتاب …» heading, not a hadith
                chapter = remove_footnote_refs(segment.strip().split("\n", 1)[0]).strip() or chapter
                current = None
                continue
            current = {
                "number": arabic_digits_to_int(match.group(1)),
                "chapter": chapter,
                "volume": meta.get("vol"),
                "page": meta.get("page"),
                "page_id": pg,
                "grade_hint": grade_hint,
                "parts": [segment],
            }

    if current is not None:
        yield _finish(book_id, current, default_grade)


def _first_text_page(data: dict) -> int | None:
    """Page id where the real numbered text starts, from the ``numbers`` index
    (hadith number → page id). Used to skip the editor's muqaddima."""
    numbers = (data.get("indexes") or {}).get("numbers") or {}
    pages = [int(v) for v in numbers.values() if str(v).lstrip("-").isdigit()]
    return min(pages) if pages else None


def _is_rimando(text: str) -> bool:
    """Does this entry end by referring to the previous matn («مثله»/«نحوه»/«بذلك»…)?"""
    return bool(_RIMANDO.search(normalize_for_search(text)[-40:]))


def _inherit_rimandi(hadiths: list[ParsedHadith]) -> None:
    """In a book's reading order, an empty-matn reference entry («…مثله») carries the
    SAME text as the hadith it points back to — only the chain differs. Give it that
    matn (marked ``ref``) so the parallel narration is searchable, not blank."""
    last = ""
    for h in hadiths:
        if h.matn and h.matn.strip():
            last = h.matn
        elif last and _is_rimando(h.text):
            h.matn = last
            h.matn_confidence = "ref"


def parse_book_file(path: str | Path, *, default_grade: str | None = None) -> list[ParsedHadith]:
    """Parse a downloaded ``{raw_dir}/books/{id}.json`` file into hadith records."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    hadiths = list(
        iter_hadith(
            int(data["book_id"]),
            data.get("pages", []),
            default_grade=default_grade,
            start_page_id=_first_text_page(data),
        )
    )
    _inherit_rimandi(hadiths)   # reference entries inherit the matn they point back to
    return hadiths
