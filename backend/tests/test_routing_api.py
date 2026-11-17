import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.routing import _to_response
from app.main import _degraded_app, app, create_app
from app.services.multimodal_engine import (
    EmissionBreakdown,
    ItineraryResult,
    RailSegment,
    RoadSegment,
)


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


def test_zero_length_road_leg_is_dropped():
    def road(km):
        return RoadSegment(mode="car", distance_km=km, duration_minutes=km, geometry={})

    def co2(mode, km):
        return EmissionBreakdown(
            mode=mode, distance_km=km, factor_gco2e_km_passenger=1, emissions_gco2e=km
        )

    rail = RailSegment(
        station_origin_uic="1", station_dest_uic="2", distance_km=200, duration_minutes=60, steps=[]
    )
    result = ItineraryResult(
        origin=(0, 0),
        destination=(1, 1),
        access=road(5),
        rail=rail,
        egress=road(0),
        emissions=[co2("car", 5), co2("train", 200), co2("car", 0)],
        total_distance_km=205,
        total_emissions_gco2e=205,
        origin_station_distance_km=1,
        destination_station_distance_km=0,
    )
    response = _to_response(result, "test", 1.0)
    assert [s.mode for s in response.segments] == ["car", "train"]
    assert response.totals.distance_totale == 205_000

    same_point = result.model_copy(
        update={"access": road(0), "rail": None, "egress": None, "emissions": [co2("car", 0)]}
    )
    assert [s.mode for s in _to_response(same_point, "test", 1.0).segments] == ["car"]
