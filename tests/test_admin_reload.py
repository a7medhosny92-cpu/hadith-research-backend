"""/admin/reload drops the cached index singletons (audit API-5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.routers.search import get_index


def test_reload_clears_cached_singletons():
    client = TestClient(app)
    before = get_index()
    r = client.post("/admin/reload")
    assert r.status_code == 200
    assert "get_index" in r.json()["reloaded"]
    # the next access rebuilds — a fresh instance, so an updated file would be picked up
    assert get_index() is not before
