"""API robustness: typed notebook bodies, health on a bad manifest, LLM timeout (Wave 3)."""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.notebook import Notebook
from app.routers.notebook import get_notebook


@pytest.fixture
def client(tmp_path):
    nb = Notebook(tmp_path / "nb.db")
    app.dependency_overrides[get_notebook] = lambda: nb
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_notebook_wrong_field_types_are_422_not_500(client):
    assert client.post("/notebook", json={"title": "x", "tags": ["a", "b"]}).status_code == 422
    assert client.post("/notebook", json={"title": "x", "note": ["y"]}).status_code == 422
    assert client.post("/notebook", json={"title": "x", "meta": "oops"}).status_code == 422
    assert client.patch("/notebook/1", json={"tags": ["a"]}).status_code == 422
    # a valid dict meta still works and round-trips as an object
    created = client.post("/notebook", json={"title": "t", "meta": {"grade": "صحيح"}}).json()
    assert created["meta"]["grade"] == "صحيح"


def test_health_ingestion_tolerates_a_malformed_manifest(tmp_path, monkeypatch):
    import app.routers.health as health
    raw = tmp_path / "raw" / "turath"
    raw.mkdir(parents=True)
    (raw / "manifest.json").write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(health, "get_settings", lambda: Settings(data_dir=tmp_path))
    r = TestClient(app).get("/health/ingestion")
    assert r.status_code == 200 and "error" in r.json()


def test_llm_call_passes_a_timeout(monkeypatch):
    from app.qa.llm import litellm_synthesizer

    seen = {}

    def fake_completion(**kwargs):
        seen.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setitem(sys.modules, "litellm",
                        type("M", (), {"completion": staticmethod(fake_completion)}))
    litellm_synthesizer("ollama/x", timeout=12.5)("q", [], [])
    assert seen["timeout"] == 12.5 and seen["num_retries"] == 0
