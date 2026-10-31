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


def test_paris_lyon_scenarios_include_drawable_geometries():
    response = TestClient(app).post(
        "/api/v1/routing/multimodal",
        json={
            "origin": {"lat": 48.8566, "lon": 2.3522},
            "destination": {"lat": 45.764, "lon": 4.8357},
        },
    )
    assert response.status_code == 200
    scenarios = response.json()["scenarios"]
    multimodal = next(item for item in scenarios if item["id"] == "multimodal")
    assert {
        "multimodal",
        "car_thermal",
        "car_electric",
        "carpool",
        "bus",
        "flight",
    }.issubset({item["id"] for item in scenarios})
    assert multimodal["is_recommended"] is True
    assert multimodal["mode"] == "train"
    assert multimodal["geometry"]["type"] == "LineString"
    assert len(multimodal["geometry"]["coordinates"]) >= 2
    assert [segment["mode"] for segment in multimodal["segments"]] == [
        "car",
        "train",
        "car",
    ]


def test_intercity_scenarios_are_available_without_local_station_match():
    response = TestClient(app).post(
        "/api/v1/routing/multimodal",
        json={
            "origin": {"lat": 48.8566, "lon": 2.3522},
            "destination": {"lat": 48.9379, "lon": 4.3946},
        },
    )
    assert response.status_code == 200
    scenarios = response.json()["scenarios"]
    assert {item["id"] for item in scenarios} == {
        "car_thermal",
        "car_electric",
        "carpool",
        "bus",
    }
    assert sum(item["is_recommended"] for item in scenarios) == 1
