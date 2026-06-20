"""The /reader endpoints — read a downloaded turath book as PDF, inline, in the app («قراءة الكتب»).

The books are stored as structured page-text JSON, not PDF; this lists the downloaded books and renders a
PAGE RANGE to a real Arabic PDF on demand (so a 15,000-page book is served a slice at a time). The loaded
book is cached, so turning pages is instant after the first load.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.config import get_settings

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


@router.get("/reader/books/{book_id}.pdf")
def reader_book_pdf(
    book_id: int,
    start: int = Query(1, ge=1, description="first page (turath page number)"),
    count: int = Query(12, ge=1, le=40, description="how many pages in this slice"),
) -> Response:
    """Render pages [start, start+count) of a downloaded book to an inline Arabic PDF."""
    try:
        data = _load_book(book_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"الكتاب {book_id} غير منزَّل")
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
