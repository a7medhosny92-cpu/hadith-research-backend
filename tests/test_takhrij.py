"""Tests for takhrij — finding parallel narrations across collections."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.qa.takhrij import find_parallels
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


def test_api_takhrij_requires_input(client):
    assert client.get("/takhrij").status_code == 422
    assert client.get("/takhrij", params={"hadith_id": 999999}).status_code == 404
