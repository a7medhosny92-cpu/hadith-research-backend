"""/search facets (collection/grade counts) and report grouping (variant de-duplication)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.search import get_embedder, get_index, get_vectors
from app.search import HadithIndex

NIYYA = "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى"          # the same report, twice
AHAB = "أحب الأعمال إلى الله أدومها وإن قل"                   # a different report (also «الأعمال»)


@pytest.fixture
def client() -> TestClient:
    idx = HadithIndex()
    idx.add([
        {"book_id": 1284, "number": 1, "matn": NIYYA, "grade": "صحيح", "chapter": "a", "page": 1, "volume": "1"},
        {"book_id": 1727, "number": 2, "matn": NIYYA, "grade": "صحيح", "chapter": "b", "page": 2, "volume": "1"},
        {"book_id": 1198, "number": 3, "matn": AHAB, "grade": "حسن", "chapter": "c", "page": 3, "volume": "1"},
    ])
    app.dependency_overrides[get_index] = lambda: idx
    app.dependency_overrides[get_vectors] = lambda: None
    app.dependency_overrides[get_embedder] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_facets_count_collections_and_grades(client):
    d = client.get("/search", params={"q": "الأعمال"}).json()
    assert d["count"] == 3
    assert sum(c["count"] for c in d["facets"]["collections"]) == 3   # facet totals == results
    grades = {g["grade"]: g["count"] for g in d["facets"]["grades"]}
    assert grades == {"صحيح": 2, "حسن": 1}


def test_group_report_merges_variants_keeps_distinct_reports(client):
    d = client.get("/search", params={"q": "الأعمال", "group": "report"}).json()
    assert d["group_count"] == 2                       # «إنما الأعمال» (×2) + «أحب الأعمال» (×1)
    big = max(d["groups"], key=lambda g: g["count"])
    assert big["count"] == 2 and len(big["sources"]) == 2   # the two صحيح copies merged
    assert len(big["members"]) == 2
