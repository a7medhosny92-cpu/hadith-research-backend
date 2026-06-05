from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_lists_endpoints():
    body = client.get("/").json()
    assert {"/search", "/ask", "/takhrij"} <= set(body["endpoints"])   # now live
    assert "/verify-isnad" in body["endpoints_planned"]               # still to come


def test_ingestion_status_shape():
    response = client.get("/health/ingestion")
    assert response.status_code == 200
    assert "started" in response.json()
