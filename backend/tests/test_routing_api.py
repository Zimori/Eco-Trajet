from app.main import app
from fastapi.testclient import TestClient


def test_health_reports_dataset_state():
    response = TestClient(app).get("/health")
    assert response.status_code in (200, 503)
    assert response.json()["status"] in ("healthy", "degraded")


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
