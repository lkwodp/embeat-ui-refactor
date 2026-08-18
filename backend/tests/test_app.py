"""Smoke tests for the FastAPI application wiring."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_wired():
    response = client.get("/api/health")
    assert response.status_code == 503 or response.status_code == 200
    body = response.json()
    assert "ready" in body
    assert body["service"] == "embeat-web"


def test_recommend_missing_track_id_rejected():
    response = client.post("/api/recommend", json={"track_id": ""})
    assert response.status_code == 404


def test_recommend_missing_track_id_field_rejected():
    response = client.post("/api/recommend", json={})
    assert response.status_code == 422


def test_spa_serves_frontend_build():
    response = client.get("/")
    assert response.status_code == 200
    assert "Embeat Music Discovery" in response.text