from fastapi.testclient import TestClient


def test_health_returns_200():
    from core.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body():
    from core.main import app

    client = TestClient(app)
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
    assert "neo4j" in body
