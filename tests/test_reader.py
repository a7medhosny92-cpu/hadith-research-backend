"""The in-app book reader («قراءة الكتب») — list downloaded books + render a page range to PDF."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parsing.book_pdf import _MissingDeps, render_book_pdf


def _seed_book(tmp_path, monkeypatch):
    """A tiny on-disk book + the reader pointed at it (returns the books dir)."""
    books = tmp_path / "books"
    books.mkdir()
    (books / "1284.json").write_text(json.dumps(
        {"book_id": 1284, "name": "صحيح البخاري", "page_count": 3,
         "pages": [
             {"pg": 1, "text": "إنَّما الأعمالُ بالنِّيّاتِ"},
             {"pg": 2, "text": "حدَّثنا الحُمَيديُّ عبدُ اللهِ بنُ الزُّبَيرِ"},
             {"pg": 3, "text": ""},
         ]}), encoding="utf-8")
    from app.routers import reader
    monkeypatch.setattr(reader, "_books_dir", lambda: books)
    reader._load_book.cache_clear()
    return books


def test_reader_books_lists_downloaded_books(tmp_path, monkeypatch):
    _seed_book(tmp_path, monkeypatch)
    body = TestClient(app).get("/reader/books").json()
    assert body["count"] == 1
    assert body["books"][0] == {"id": 1284, "title": "صحيح البخاري", "pages": 3}


def test_reader_pages_returns_cleaned_text_for_native_reading(tmp_path, monkeypatch):
    _seed_book(tmp_path, monkeypatch)
    body = TestClient(app).get("/reader/books/1284/pages?start=1&count=2").json()
    assert body["title"] == "صحيح البخاري"
    assert [p["pg"] for p in body["pages"]] == [1, 2]
    assert "الأعمال" in body["pages"][0]["text"]


def test_reader_search_finds_a_word_across_the_book_diacritic_folded(tmp_path, monkeypatch):
    _seed_book(tmp_path, monkeypatch)
    # «الزبير» (unvocalised) must match the vocalised «الزُّبَيرِ» on page 2
    body = TestClient(app).get("/reader/books/1284/search?q=الزبير").json()
    assert body["count"] == 1
    assert body["matches"][0]["pg"] == 2


def test_reader_pages_404_for_an_absent_book(tmp_path, monkeypatch):
    _seed_book(tmp_path, monkeypatch)
    assert TestClient(app).get("/reader/books/9999/pages").status_code == 404


def test_render_book_pdf_produces_a_pdf_for_the_page_range():
    pages = [{"pg": i, "text": f"هذه صفحةٌ رقم {i} فيها نصٌّ عربيٌّ مشكول."} for i in range(1, 30)]
    try:                                  # the renderer needs fpdf2/uharfbuzz + the Noto Naskh font
        pdf = render_book_pdf("صحيح البخاري", pages, start=5, count=3)
    except _MissingDeps as exc:           # absent in a bare CI runner — the endpoint returns 503 there
        pytest.skip(f"book PDF deps/font absent: {exc}")
    assert pdf[:4] == b"%PDF"            # a real PDF
    assert len(pdf) > 1000
