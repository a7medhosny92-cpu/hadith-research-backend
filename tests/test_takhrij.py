"""Tests for takhrij — finding parallel narrations across collections."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.qa.takhrij import analyze_narrations, find_parallels
from app.routers.search import get_index
from app.search import HadithIndex

KADHIB = "مَنْ كَذَبَ عَلَيَّ مُتَعَمِّدًا فَلْيَتَبَوَّأْ مَقْعَدَهُ مِنَ النَّارِ"

RECORDS = [
    {"book_id": 1284, "number": 110, "matn": KADHIB, "isnad": "حدثنا أبو معمر",
     "grade": "صحيح", "chapter": "العلم", "page": 36, "volume": "1"},
    {"book_id": 1727, "number": 3, "matn": KADHIB, "isnad": "حدثنا أبو بكر",
     "grade": "صحيح", "chapter": "المقدمة", "page": 10, "volume": "1"},
    {"book_id": 1198, "number": 33, "matn": "مَنْ كَذَبَ عَلَيَّ مُتَعَمِّدًا فَلْيَتَبَوَّأْ مَقْعَدَهُ مِنَ النَّارِ",
     "isnad": "حدثنا علي بن محمد", "grade": None, "chapter": "السنة", "page": 13, "volume": "1"},
    {"book_id": 1284, "number": 1, "matn": "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ",
     "isnad": "حدثنا الحميدي", "grade": "صحيح", "chapter": "بدء الوحي", "page": 179, "volume": "1"},
]


@pytest.fixture
def index() -> HadithIndex:
    idx = HadithIndex()
    idx.add(RECORDS)
    return idx


def test_find_parallels_matches_same_report_not_unrelated(index):
    source = index.search("كذب علي متعمدا")[0]
    parallels = find_parallels(source.matn, index, exclude_id=source.id)
    books = {hit.book_id for _, hit in parallels}
    assert {1727, 1198} <= books          # the other narrations of the same hadith
    assert source.id not in {h.id for _, h in parallels}
    assert all(hit.matn != "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ" for _, hit in parallels)  # unrelated excluded
    assert parallels[0][0] >= 0.8         # high overlap for a verbatim parallel


NIYYA = "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى"
NIYYA_VAR = "الْأَعْمَالُ بِالنِّيَّةِ وَلِكُلِّ امْرِئٍ مَا نَوَى"  # same report, different wording

VARIANTS = [
    {"book_id": 1284, "number": 1, "matn": NIYYA, "isnad": "حدثنا الحميدي",
     "grade": "صحيح", "chapter": "بدء الوحي", "page": 1, "volume": "1"},
    {"book_id": 1727, "number": 5, "matn": NIYYA, "isnad": "حدثنا عبد الله",  # verbatim parallel
     "grade": "صحيح", "chapter": "الإمارة", "page": 80, "volume": "3"},
    {"book_id": 1726, "number": 9, "matn": NIYYA_VAR, "isnad": "حدثنا مسدد",  # بنحوه
     "grade": "صحيح", "chapter": "الطلاق", "page": 50, "volume": "2"},
    {"book_id": 1198, "number": 70, "matn": "الصَّلَاةُ عِمَادُ الدِّينِ مَنْ أَقَامَهَا",
     "isnad": "حدثنا علي", "grade": "ضعيف", "chapter": "الصلاة", "page": 5, "volume": "1"},
]


@pytest.fixture
def variants_index() -> HadithIndex:
    idx = HadithIndex()
    idx.add(VARIANTS)
    return idx


def _all_narrations(a):
    return [n for g in a["groups"] for v in g["variants"] for n in v["narrations"]]


def test_analyze_merges_verbatim_into_one_variant(index):
    src = index.search("كذب علي متعمدا")[0]
    a = analyze_narrations(src.matn, index, exclude_id=src.id)
    assert a["total"] == 2 and a["variants"] == 1      # both verbatim → one صيغة
    g = a["groups"][0]
    assert g["variants"][0]["count"] == 2
    assert g["variants"][0]["label"] == "بلفظه"
    assert all("الْأَعْمَالُ" not in n["matn"] for n in _all_narrations(a))  # unrelated excluded


def test_analyze_separates_distinct_wordings(variants_index):
    src = variants_index.search("الأعمال بالنيات")[0]
    a = analyze_narrations(src.matn, variants_index, exclude_id=src.id)
    assert a["total"] == 2 and a["variants"] == 2       # one verbatim + one بنحوه
    labels = {v["label"] for g in a["groups"] for v in g["variants"]}
    assert "بلفظه" in labels and "بنحوه" in labels
    assert all("الصَّلَاةُ" not in n["matn"] for n in _all_narrations(a))  # different report excluded


HADITH = "الطُّهُورُ شَطْرُ الْإِيمَانِ وَالْحَمْدُ لِلَّهِ تَمْلَأُ الْمِيزَانَ"
COMPANION_RECORDS = [
    {"book_id": 1727, "number": 223, "matn": HADITH, "grade": "صحيح", "chapter": "الطهارة",
     "page": 140, "volume": "1", "isnad": "حدثنا إسحاق حدثنا أبو هريرة عن النبي"},
    {"book_id": 1284, "number": 9, "matn": HADITH, "grade": "صحيح", "chapter": "الإيمان",
     "page": 12, "volume": "1", "isnad": "حدثنا قتيبة عن أبي هريرة عن النبي"},
    {"book_id": 1726, "number": 31, "matn": HADITH, "grade": "حسن", "chapter": "الطهارة",
     "page": 18, "volume": "1", "isnad": "حدثنا مسدد عن عائشة عن النبي"},
]


def test_analyze_groups_by_companion():
    idx = HadithIndex()
    idx.add(COMPANION_RECORDS)
    src = idx.search("الطهور شطر الإيمان")[0]   # the أبو هريرة one is indexed first
    a = analyze_narrations(src.matn, idx, exclude_id=src.id)
    companions = {g["companion"] for g in a["groups"]}
    assert "عبد الرحمن بن صخر الدوسي" in companions   # أبو هريرة, recognised in the chain
    assert "عائشة بنت أبي بكر" in companions
    assert a["companions"] == 2
    abu_hurayra = next(g for g in a["groups"] if g["companion"] == "عبد الرحمن بن صخر الدوسي")
    assert abu_hurayra["takhrij"].startswith("أخرجه")     # «أخرجه …» summary present


@pytest.fixture
def client(index) -> TestClient:
    app.dependency_overrides[get_index] = lambda: index
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_takhrij_by_id(client):
    src_id = client.get("/search", params={"q": "كذب علي متعمدا"}).json()["results"][0]["id"]
    body = client.get("/takhrij", params={"hadith_id": src_id}).json()
    assert body["count"] >= 2
    assert "صحيح مسلم" in body["by_collection"]
    assert all(p["id"] != src_id for p in body["parallels"])


def test_api_takhrij_by_text(client):
    body = client.get("/takhrij", params={"q": KADHIB}).json()
    assert {p["collection"] for p in body["parallels"]} >= {"صحيح البخاري", "صحيح مسلم"}


def test_api_takhrij_returns_groups(client):
    body = client.get("/takhrij", params={"q": KADHIB}).json()
    assert body["variants"] >= 1 and "companions" in body
    g = body["groups"][0]
    assert "companion" in g and g["variants"][0]["label"] in ("بلفظه", "بنحوه", "بمعناه")
    assert g["count"] >= 1
    assert "by_collection" in body and body["count"] == len(body["parallels"])


def test_api_takhrij_requires_input(client):
    assert client.get("/takhrij").status_code == 422
    assert client.get("/takhrij", params={"hadith_id": 999999}).status_code == 404
