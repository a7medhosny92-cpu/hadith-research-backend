"""The «الكتب» library navigator: HadithIndex.collections/chapters/chapter_hadiths + the /books API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.routers.search import get_index
from app.search import HadithIndex

REC = [
    {"book_id": 1284, "number": 1, "matn": "إنما الأعمال بالنيات", "isnad": "س", "grade": "صحيح",
     "chapter": "كتاب بدء الوحي", "page": 1, "volume": "1"},
    {"book_id": 1284, "number": 2, "matn": "بني الإسلام على خمس", "isnad": "س", "grade": "صحيح",
     "chapter": "كتاب الإيمان", "page": 2, "volume": "1"},
    {"book_id": 1284, "number": 3, "matn": "المسلم من سلم المسلمون", "isnad": "س", "grade": "صحيح",
     "chapter": "كتاب الإيمان", "page": 3, "volume": "1"},
    {"book_id": 1727, "number": 1, "matn": "الطهور شطر الإيمان", "isnad": "س", "grade": "صحيح",
     "chapter": "كتاب الطهارة", "page": 1, "volume": "1"},
]


def _idx() -> HadithIndex:
    idx = HadithIndex()
    idx.add(REC)
    return idx


def test_chapters_ordered_by_hadith_number_not_insertion():
    """Chapters order by their first hadith NUMBER (book order), even when hadiths are inserted out of
    that order (rowid). This is the ابن ماجه bug: كتب interleaved because MIN(rowid) ≠ book order."""
    idx = HadithIndex(":memory:")
    idx.add([
        {"book_id": 7, "number": 5, "matn": "x", "isnad": "س", "chapter": "باب الثاني", "page": 1, "volume": "1"},
        {"book_id": 7, "number": 1, "matn": "y", "isnad": "س", "chapter": "باب الأول", "page": 1, "volume": "1"},
        {"book_id": 7, "number": 6, "matn": "z", "isnad": "س", "chapter": "باب الثاني", "page": 1, "volume": "1"},
    ])
    assert [c["chapter"] for c in idx.chapters(7)] == ["باب الأول", "باب الثاني"]   # number 1 before 5


def test_collections_chapters_hadiths():
    idx = _idx()
    cols = {c["book_id"]: c for c in idx.collections()}
    assert set(cols) == {1284, 1727} and cols[1284]["count"] == 3

    chs = idx.chapters(1284)
    assert [c["chapter"] for c in chs] == ["كتاب بدء الوحي", "كتاب الإيمان"]   # in BOOK order
    assert next(c for c in chs if c["chapter"] == "كتاب الإيمان")["count"] == 2

    hs = idx.chapter_hadiths(1284, "كتاب الإيمان")
    assert len(hs) == 2 and all(h.chapter == "كتاب الإيمان" for h in hs)
    assert len(idx.chapter_hadiths(1284)) == 3                                # whole book when no chapter
    assert len(idx.chapter_hadiths(1284, "كتاب الإيمان", offset=1, limit=1)) == 1   # paged


def test_books_endpoints():
    idx = _idx()
    from app.main import app
    app.dependency_overrides[get_index] = lambda: idx
    try:
        client = TestClient(app)
        cols = client.get("/books").json()["collections"]
        assert any(c["book_id"] == 1284 and c["count"] == 3 for c in cols)

        ch = client.get("/books/1284/chapters").json()
        assert ch["total"] == 2 and ch["chapters"][0]["chapter"] == "كتاب بدء الوحي"

        hd = client.get("/books/1284/hadiths", params={"chapter": "كتاب الإيمان"}).json()
        assert hd["chapter"] == "كتاب الإيمان" and len(hd["hadiths"]) == 2
        assert hd["hadiths"][0]["matn"]
    finally:
        app.dependency_overrides.clear()
