"""The in-app book reader («قراءة الكتب») — list downloaded books + render a page range to PDF."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.parsing.book_pdf import render_book_pdf


def test_reader_books_lists_downloaded_books(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir()
    (books / "1284.json").write_text(json.dumps(
        {"book_id": 1284, "name": "صحيح البخاري", "page_count": 3,
         "pages": [{"pg": 1, "text": "نصٌّ"}]}), encoding="utf-8")

    from app.routers import reader
    monkeypatch.setattr(reader, "_books_dir", lambda: books)
    reader._load_book.cache_clear()
    body = TestClient(app).get("/reader/books").json()
    assert body["count"] == 1
    assert body["books"][0] == {"id": 1284, "title": "صحيح البخاري", "pages": 3}


def test_render_book_pdf_produces_a_pdf_for_the_page_range():
    pages = [{"pg": i, "text": f"هذه صفحةٌ رقم {i} فيها نصٌّ عربيٌّ مشكول."} for i in range(1, 30)]
    pdf = render_book_pdf("صحيح البخاري", pages, start=5, count=3)
    assert pdf[:4] == b"%PDF"            # a real PDF
    assert len(pdf) > 1000
