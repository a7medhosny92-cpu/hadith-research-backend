from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_lists_endpoints():
    body = client.get("/").json()
    assert {"/search", "/ask", "/takhrij", "/verify-isnad", "/narrator"} <= set(body["endpoints"])


def test_ingestion_status_shape():
    response = client.get("/health/ingestion")
    assert response.status_code == 200
    assert "started" in response.json()


def test_app_ui_is_served():
    response = client.get("/app")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "بحث" in response.text  # the Arabic desktop UI is returned
