"""The /reader endpoints — read a downloaded turath book in the app («قراءة الكتب»).

The books are stored as structured page-text JSON, not PDF. This lists the downloaded books and serves a
PAGE RANGE two ways (so a 15,000-page book is served a slice at a time, never whole):
  • native text  — ``/reader/books/{id}/pages`` returns the cleaned page text as JSON for fast in-app RTL
    reading (no PDF to generate), plus ``/reader/books/{id}/search`` to find a word across the whole book;
  • a real PDF   — ``/reader/books/{id}.pdf`` renders the slice to an Arabic PDF for inline view / download.
The loaded book is cached, so turning pages is instant after the first load.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.config import get_settings
from app.parsing.html_clean import clean_block
from app.parsing.normalize import normalize_for_search

router = APIRouter(tags=["reader"])


def _books_dir():
    return get_settings().raw_dir / "books"


@lru_cache(maxsize=3)
def _load_book(book_id: int) -> dict:
    """Load + cache a raw book JSON (big files — keep the last few in memory for fast page-turns)."""
    path = _books_dir() / f"{book_id}.json"
    if not path.exists():
        raise FileNotFoundError(book_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _require_book(book_id: int) -> dict:
    try:
        return _load_book(book_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"الكتاب {book_id} غير منزَّل")


def _page_text(p: dict) -> str:
    """The display text of one stored book page (HTML markup cleaned to plain Arabic)."""
    return clean_block(p.get("text") or "").strip()


@router.get("/reader/books")
def reader_books() -> dict:
    """The downloaded raw books available to read: ``[{id, title, pages}]`` (sorted by title)."""
    d = _books_dir()
    out: list[dict] = []
    if d.exists():
        for p in d.glob("*.json"):
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            out.append({
                "id": meta.get("book_id") or int(p.stem),
                "title": (meta.get("name") or p.stem).strip(),
                "pages": meta.get("page_count") or len(meta.get("pages") or []),
            })
    out.sort(key=lambda b: b["title"])
    return {"books": out, "count": len(out)}


@router.get("/reader/books/{book_id}/pages")
def reader_book_pages(
    book_id: int,
    start: int = Query(1, ge=1, description="first page (turath page number)"),
    count: int = Query(8, ge=1, le=40, description="how many pages in this slice"),
) -> dict:
    """Pages [start, start+count) of a downloaded book as cleaned Arabic TEXT (for native in-app reading)."""
    data = _require_book(book_id)
    pages = data.get("pages") or []
    page_count = data.get("page_count") or len(pages)
    sel = [
        {"pg": p.get("pg"), "vol": p.get("vol"), "text": _page_text(p)}
        for p in pages if start <= (p.get("pg") or 0) < start + count
    ]
    return {
        "book_id": book_id,
        "title": (data.get("name") or str(book_id)).strip(),
        "page_count": page_count,
        "start": start,
        "count": count,
        "pages": sel,
    }


@router.get("/reader/books/{book_id}/search")
def reader_book_search(
    book_id: int,
    q: str = Query(..., min_length=2, description="a word/phrase to find in the book"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Find ``q`` across the whole book (diacritic/hamza-folded) — returns the matching pages + a snippet."""
    data = _require_book(book_id)
    needle = normalize_for_search(q).strip()
    matches: list[dict] = []
    if needle:
        for p in data.get("pages") or []:
            text = _page_text(p)
            if not text:
                continue
            ntext = normalize_for_search(text)        # snippet from the normalised text — the diacritic-
            pos = ntext.find(needle)                   # folded match window always contains the word found
            if pos < 0:
                continue
            lo, hi = max(0, pos - 40), min(len(ntext), pos + len(needle) + 40)
            snippet = ("…" if lo else "") + ntext[lo:hi].strip() + ("…" if hi < len(ntext) else "")
            matches.append({"pg": p.get("pg"), "vol": p.get("vol"), "snippet": snippet})
            if len(matches) >= limit:
                break
    return {"book_id": book_id, "q": q, "count": len(matches), "matches": matches}


@router.get("/reader/books/{book_id}.pdf")
def reader_book_pdf(
    book_id: int,
    start: int = Query(1, ge=1, description="first page (turath page number)"),
    count: int = Query(12, ge=1, le=40, description="how many pages in this slice"),
) -> Response:
    """Render pages [start, start+count) of a downloaded book to an inline Arabic PDF (view / download)."""
    data = _require_book(book_id)
    from app.parsing.book_pdf import _MissingDeps, render_book_pdf
    try:
        pdf = render_book_pdf(
            (data.get("name") or str(book_id)).strip(),
            data.get("pages") or [],
            start=start, count=count,
        )
    except _MissingDeps as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="book_{book_id}_{start}.pdf"'},
    )
