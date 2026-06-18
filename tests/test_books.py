"""The «الكتب» library navigator: HadithIndex.collections/chapters/chapter_hadiths + the /books API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.routers.search import get_index
from app.search import HadithIndex, SharhIndex

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


def test_taliq_section_shows_in_library_only_ordered_in_place():
    """A «taliq» باب (تعليق/أثر, no number/isnad) appears in the library in book order (via its
    ``sort`` key), but is excluded from search."""
    idx = HadithIndex(":memory:")
    idx.add([
        {"book_id": 9, "number": 1, "matn": "حديث الأول", "isnad": "س", "chapter": "باب أ", "page": 1, "volume": "1"},
        # a تعليق باب between #1 and #2, no number, sort=1 (after hadith #1):
        {"book_id": 9, "number": None, "matn": "وقال مالك الدين النصيحة", "isnad": "", "chapter": "باب ب — تعليق",
         "page": 2, "volume": "1", "kind": "taliq", "sort": 1},
        {"book_id": 9, "number": 2, "matn": "حديث الثاني", "isnad": "س", "chapter": "باب ج", "page": 3, "volume": "1"},
    ])
    # library: the تعليق باب sits in book order (after باب أ, before باب ج)
    assert [c["chapter"] for c in idx.chapters(9)] == ["باب أ", "باب ب — تعليق", "باب ج"]
    leaf = idx.chapter_hadiths(9, "باب ب — تعليق")
    assert len(leaf) == 1 and leaf[0].kind == "taliq" and leaf[0].number is None
    # search never surfaces a taliق (it is library-only, no isnad to grade)
    assert idx.search("النصيحة") == []
    assert [h.number for h in idx.search("حديث")] == [1, 2]   # the real hadith are still found


def test_sharh_library_navigator():
    """A شرح is browsable like a collection: book → chapters → passages (full text rejoined)."""
    sx = SharhIndex(":memory:")
    sx.add([
        {"book_id": 641, "sharh": "فتح الباري", "base_id": 1284, "base_name": "صحيح البخاري",
         "hadith_number": 1, "chapter": "كتاب بدء الوحي", "page": 9, "page_id": 100,
         "text": "قوله إنما الأعمال بالنيات. هذا الحديث أحد قواعد الإسلام."},
        {"book_id": 641, "sharh": "فتح الباري", "base_id": 1284, "base_name": "صحيح البخاري",
         "hadith_number": 2, "chapter": "كتاب الإيمان", "page": 20, "page_id": 101,
         "text": "قوله بني الإسلام على خمس. شرح أركان الإسلام."},
    ])
    cols = sx.collections()
    assert len(cols) == 1 and cols[0]["book_id"] == 641 and cols[0]["base_name"] == "صحيح البخاري"
    assert cols[0]["count"] == 2                                   # two distinct passages

    chs = sx.chapters(641)
    assert [c["chapter"] for c in chs] == ["كتاب بدء الوحي", "كتاب الإيمان"]   # in hadith-number order

    ps = sx.chapter_passages(641, "كتاب الإيمان")
    assert len(ps) == 1 and ps[0]["hadith_number"] == 2 and "أركان الإسلام" in ps[0]["text"]


def test_sharh_books_endpoints():
    sx = SharhIndex(":memory:")
    sx.add([{"book_id": 641, "sharh": "فتح الباري", "base_id": 1284, "base_name": "صحيح البخاري",
             "hadith_number": 1, "chapter": "كتاب بدء الوحي", "page": 9, "page_id": 100,
             "text": "شرح الحديث الأول."}])
    from app.main import app
    from app.routers.ask import get_sharh_index
    app.dependency_overrides[get_sharh_index] = lambda: sx
    try:
        client = TestClient(app)
        cs = client.get("/sharh-books").json()["commentaries"]
        assert any(c["book_id"] == 641 and c["sharh"] == "فتح الباري" for c in cs)
        ch = client.get("/sharh-books/641/chapters").json()
        assert ch["total"] == 1 and ch["chapters"][0]["chapter"] == "كتاب بدء الوحي"
        pg = client.get("/sharh-books/641/passages", params={"chapter": "كتاب بدء الوحي"}).json()
        assert len(pg["passages"]) == 1 and "شرح الحديث" in pg["passages"][0]["text"]
    finally:
        app.dependency_overrides.clear()


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
