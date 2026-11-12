import pytest
from fastapi.testclient import TestClient

from app.main import _degraded_app, app, create_app


def test_health_is_degraded_when_datasets_are_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTING_DATA_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="Missing files") as exc:
        create_app()
    response = TestClient(_degraded_app(str(exc.value))).get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert "Missing files" in response.json()["detail"]


def test_cors_preflight_is_accepted():
    response = TestClient(app).options(
        "/api/v1/routing/multimodal",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:3000"
    )
    assert "POST" in response.headers["access-control-allow-methods"]


def test_agent_tool_schema_is_openai_compatible():
    response = TestClient(app).get("/api/v1/agent-tools/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "function"
    assert body["function"]["name"] == "calculate_multimodal_trip"


def test_cors_rejects_unlisted_origin():
    response = TestClient(app).options(
        "/api/v1/routing/multimodal",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
