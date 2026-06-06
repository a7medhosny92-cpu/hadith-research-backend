"""Tests for the study notebook (store + endpoints)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.notebook import Notebook
from app.routers.notebook import get_notebook


# ── store ───────────────────────────────────────────────────────────────────────
def test_add_list_update_delete(tmp_path):
    nb = Notebook(tmp_path / "notebook.db")
    item = nb.add("hadith", "صحيح البخاري · رقم 1", "إنما الأعمال بالنيات",
                  meta={"grade": "صحيح"}, tags="النية")
    assert item["id"] and item["meta"]["grade"] == "صحيح"
    assert nb.count() == 1

    found = nb.list("الأعمال")
    assert len(found) == 1 and found[0]["title"].startswith("صحيح البخاري")
    assert nb.list("لا يوجد") == []

    nb.update(item["id"], note="حديث النية — أصل عظيم")
    assert nb.get(item["id"])["note"] == "حديث النية — أصل عظيم"

    assert nb.delete(item["id"]) and nb.count() == 0


def test_persists_to_disk(tmp_path):
    path = tmp_path / "notebook.db"
    Notebook(path).add("answer", "سؤال", "جواب")
    assert Notebook(path).count() == 1   # reopened, still there


# ── endpoints ───────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path):
    nb = Notebook(tmp_path / "notebook.db")
    app.dependency_overrides[get_notebook] = lambda: nb
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_notebook_roundtrip(client):
    created = client.post("/notebook", json={
        "kind": "hadith", "title": "صحيح مسلم · رقم 1907",
        "body": "إنما الأعمال بالنيات", "meta": {"grade": "صحيح"}, "tags": "النية",
    }).json()
    assert created["id"]

    listing = client.get("/notebook").json()
    assert listing["count"] == 1 and listing["items"][0]["meta"]["grade"] == "صحيح"

    edited = client.patch(f"/notebook/{created['id']}", json={"note": "مهم"}).json()
    assert edited["note"] == "مهم"

    assert client.get("/notebook", params={"q": "النيات"}).json()["count"] == 1
    assert client.delete(f"/notebook/{created['id']}").json()["deleted"] == created["id"]
    assert client.get("/notebook").json()["count"] == 0


def test_api_notebook_validation_and_404(client):
    assert client.post("/notebook", json={"kind": "note"}).status_code == 422
    assert client.delete("/notebook/99999").status_code == 404
