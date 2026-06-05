"""Tests for the lexical hadith index and the search API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.search import get_index
from app.search import HadithIndex, SharhIndex

SAMPLE = [
    {
        "book_id": 1284, "number": 1,
        "matn": "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ",
        "isnad": "حدثنا الْحُمَيْدِيُّ، عَنْ سُفْيَانَ",
        "grade": "صحيح", "chapter": "بدء الوحي", "page": 179, "volume": "1",
    },
    {
        "book_id": 1727, "number": 3,
        "matn": "مَنْ كَذَبَ عَلَيَّ مُتَعَمِّدًا فَلْيَتَبَوَّأْ مَقْعَدَهُ مِنَ النَّارِ",
        "isnad": "حدثنا أَبُو بَكْرٍ، عَنْ شُعْبَةَ",
        "grade": "صحيح", "chapter": "المقدمة", "page": 10, "volume": "1",
    },
    {
        "book_id": 1726, "number": 1,
        "matn": "كَانَ النَّبِيُّ ﷺ إِذَا ذَهَبَ الْمَذْهَبَ أَبْعَدَ",
        "isnad": "حدثنا الْقَعْنَبِيُّ",
        "grade": "حسن صحيح", "chapter": "الطهارة", "page": 1, "volume": "1",
    },
]


@pytest.fixture
def index() -> HadithIndex:
    idx = HadithIndex()
    idx.add(SAMPLE)
    return idx


def test_build_and_count(index):
    assert index.count() == 3


def test_search_matn_ranks_exact_first(index):
    hits = index.search("الأعمال بالنيات")
    assert hits and hits[0].book_id == 1284 and hits[0].number == 1
    assert hits[0].collection == "صحيح البخاري"
    assert "«" in hits[0].snippet  # match is highlighted


def test_search_is_diacritics_insensitive(index):
    # bare query (no tashkeel, alef-folded) still matches the diacritised matn
    assert index.search("الاعمال بالنيات")[0].number == 1


def test_search_collection_filter(index):
    hits = index.search("النبي المذهب", collection_id=1726)
    assert hits and all(h.book_id == 1726 for h in hits)


def test_search_grade_filter_is_exact(index):
    # "حسن صحيح" must not be returned when filtering for "صحيح"
    grades = {h.grade for h in index.search("علي العمل النبي كذب", grade="صحيح")}
    assert grades <= {"صحيح"}


def test_search_isnad_field(index):
    hits = index.search("سفيان", field="isnad")
    assert hits and hits[0].book_id == 1284


def test_search_or_fallback_when_and_has_no_hits(index):
    # "القمر" appears nowhere; AND yields nothing, OR recovers the نيات hadith
    hits = index.search("الأعمال القمر")
    assert any(h.number == 1 for h in hits)


def test_get_and_missing(index):
    first = index.search("الأعمال")[0]
    assert index.get(first.id).number == 1
    assert index.get(999999) is None


def test_search_matches_chapter_not_just_matn(index):
    # the topical term lives in the bab heading, not the matn
    index.add([{
        "book_id": 1284, "number": 99, "matn": "حديثٌ بلا اللفظ المقصود",
        "isnad": "إسناد", "grade": "صحيح", "chapter": "باب فضل الصدقة",
        "page": 5, "volume": "1",
    }])
    assert any(h.number == 99 for h in index.search("الصدقة"))


def test_sharh_index_chunks_long_passages():
    si = SharhIndex()
    si.add([{
        "book_id": 1673, "sharh": "فتح الباري", "base_id": 1284,
        "base_name": "صحيح البخاري", "hadith_number": 1, "chapter": None,
        "page": 1, "page_id": 1, "text": "هذه جملة شرحٍ مطوّلة. " * 400,  # ~8k chars
    }])
    assert si.count() > 1  # one long passage → several chunks
    assert all(h.hadith_number == 1 for h in si.by_hadith(1284, 1, limit=20))


# ── API ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(index) -> TestClient:
    app.dependency_overrides[get_index] = lambda: index
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_search(client):
    r = client.get("/search", params={"q": "من كذب علي متعمدا"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert body["results"][0]["collection"] == "صحيح مسلم"
    assert body["results"][0]["number"] == 3


def test_api_search_collection_filter(client):
    r = client.get("/search", params={"q": "النبي المذهب", "collection": 1726})
    assert r.status_code == 200
    assert all(h["book_id"] == 1726 for h in r.json()["results"])


def test_api_search_requires_query(client):
    assert client.get("/search").status_code == 422


def test_api_get_hadith_and_404(client):
    hit_id = client.get("/search", params={"q": "الأعمال"}).json()["results"][0]["id"]
    assert client.get(f"/hadith/{hit_id}").json()["number"] == 1
    assert client.get("/hadith/999999").status_code == 404
