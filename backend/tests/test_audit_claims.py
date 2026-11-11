from __future__ import annotations

import importlib.util
import json
import statistics
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import _load_rail_graph, create_app
from app.services.entity_matcher import (
    AmbiguousEmissionFactorError,
    EmissionEntityMatcher,
)
from app.services.multimodal_engine import MultimodalRoutingEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
PARIS = (48.8566, 2.3522)
LYON = (45.7640, 4.8357)
BORDEAUX = (44.8378, -0.5792)


def _load_seed_module():
    spec = importlib.util.spec_from_file_location(
        "seed_data", REPO_ROOT / "backend/scripts/seed_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load_seed_module()


def _write_stations(path: Path, extra=()) -> None:
    stations = [(name, *hub) for name, hub in seed.HUBS.items()] + list(extra)
    features = [
        {
            "type": "Feature",
            "properties": {"name": name, "code_uic": uic},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        }
        for name, uic, lat, lon in stations
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


class OsrmRecorder:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.urls: list[httpx.URL] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(request.url)
        if self.status_code != 200:
            return httpx.Response(self.status_code)
        start, end = request.url.path.rsplit("/", 1)[-1].split(";")
        coordinates = [list(map(float, start.split(","))), list(map(float, end.split(",")))]
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distance": 5000.0,
                        "duration": 600.0,
                        "geometry": {"type": "LineString", "coordinates": coordinates},
                    }
                ]
            },
        )


def _build(tmp_path: Path, osrm: OsrmRecorder, extra_stations=(), max_retries: int = 3):
    ademe = tmp_path / "ademe.parquet"
    stations = tmp_path / "stations.geojson"
    graph_path = tmp_path / "graph.json"
    seed.build_ademe_dataset(ademe)
    _write_stations(stations, extra_stations)
    seed.build_rail_graph(graph_path)
    engine = MultimodalRoutingEngine(
        EmissionEntityMatcher(ademe, stations),
        _load_rail_graph(graph_path),
        client=httpx.AsyncClient(transport=httpx.MockTransport(osrm)),
        max_retries=max_retries,
        road_vehicle_type="thermique",
        rail_vehicle_type="TGV",
    )
    return engine, TestClient(create_app(engine=engine))


def _body(origin, destination):
    return {
        "origin": {"lat": origin[0], "lon": origin[1]},
        "destination": {"lat": destination[0], "lon": destination[1]},
    }


def test_paris_lyon_end_to_end_road_rail_road(tmp_path):
    osrm = OsrmRecorder()
    _, client = _build(tmp_path, osrm)
    response = client.post("/api/v1/routing/multimodal", json=_body(PARIS, LYON))
    assert response.status_code == 200, response.text
    body = response.json()
    assert [s["mode"] for s in body["segments"]] == ["car", "train", "car"]
    train = body["segments"][1]
    assert train["distance_m"] == pytest.approx(427_000)
    assert train["duration_s"] == pytest.approx(7080)
  
    assert train["co2_grams"] == pytest.approx(427 * 2.93)
    assert body["totals"]["co2_total"] == pytest.approx(427 * 2.93 + 10 * 218)
    assert body["totals"]["co2_total"] == pytest.approx(
        sum(s["co2_grams"] for s in body["segments"])
    )
  
    assert train["geometry"]["coordinates"][0] == [2.3730, 48.8443]


def test_osrm_is_called_with_lon_lat_order(tmp_path):
    osrm = OsrmRecorder()
    _, client = _build(tmp_path, osrm)
    client.post("/api/v1/routing/multimodal", json=_body(PARIS, LYON))
    assert len(osrm.urls) == 2
    first_leg = osrm.urls[0].path.rsplit("/", 1)[-1]
    assert first_leg.startswith(f"{PARIS[1]},{PARIS[0]};")


def test_short_trip_falls_back_to_road_only(tmp_path):
    osrm = OsrmRecorder()
    _, client = _build(tmp_path, osrm)
    near = (PARIS[0] + 0.05, PARIS[1] + 0.05)
    body = client.post("/api/v1/routing/multimodal", json=_body(PARIS, near)).json()
    assert [s["mode"] for s in body["segments"]] == ["car"]
    assert body["metadata"]["matching_reliability_score"] == 0.0


def test_osrm_outage_is_retried_then_mapped_to_502(tmp_path):
    osrm = OsrmRecorder(status_code=503)
    _, client = _build(tmp_path, osrm, max_retries=2)
    response = client.post("/api/v1/routing/multimodal", json=_body(PARIS, LYON))
    assert response.status_code == 502
    assert len(osrm.urls) == 4


def test_pydantic_rejects_out_of_range_coordinates(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    response = client.post(
        "/api/v1/routing/multimodal", json=_body((123.0, 2.0), LYON)
    )
    assert response.status_code == 422


def test_long_trip_outside_france_is_422_not_500(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    berlin = (52.52, 13.405)
    response = client.post("/api/v1/routing/multimodal", json=_body(PARIS, berlin))
    assert response.status_code == 422


def test_ademe_factor_unit_conversion_and_ambiguity(tmp_path):
    ademe, stations = tmp_path / "a.parquet", tmp_path / "s.geojson"
    seed.build_ademe_dataset(ademe)
    _write_stations(stations)
    matcher = EmissionEntityMatcher(ademe, stations)
    assert matcher.get_emission_factor("voiture", "thermique")["factor"] == pytest.approx(218)
    assert matcher.get_emission_factor("TGV", "TGV")["factor"] == pytest.approx(2.93)
    with pytest.raises(AmbiguousEmissionFactorError):
        matcher.get_emission_factor("train")


def test_in_process_overhead_is_well_under_120ms(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    timings = []
    for _ in range(10):
        started = time.perf_counter()
        client.post("/api/v1/routing/multimodal", json=_body(PARIS, LYON))
        timings.append((time.perf_counter() - started) * 1000)
    assert statistics.median(timings) < 120


def test_non_hub_nearest_station_still_routes(tmp_path):
    chatelet = ("Châtelet-Les Halles", "87758607", 48.8619, 2.3470)
    _, client = _build(tmp_path, OsrmRecorder(), extra_stations=[chatelet])
    response = client.post("/api/v1/routing/multimodal", json=_body(PARIS, LYON))
    assert response.status_code == 200, response.text
    assert [s["mode"] for s in response.json()["segments"]] == ["car", "train", "car"]


def test_paris_bordeaux_takes_the_direct_line(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    body = client.post("/api/v1/routing/multimodal", json=_body(PARIS, BORDEAUX)).json()
    assert body["segments"][1]["distance_m"] == pytest.approx(585_000)


def test_same_station_on_both_ends_is_road_only(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    villeurbanne_east = (45.7700, 5.0500)
    body = client.post(
        "/api/v1/routing/multimodal", json=_body(LYON, villeurbanne_east)
    ).json()
    assert [s["mode"] for s in body["segments"]] == ["car"]


def test_absurd_rail_detour_falls_back_to_road(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    south_of_paris = (48.6800, 2.3500)
    body = client.post(
        "/api/v1/routing/multimodal", json=_body(PARIS, south_of_paris)
    ).json()
    assert [s["mode"] for s in body["segments"]] == ["car"]


def test_station_search_can_be_restricted_to_graph_nodes(tmp_path):
    chatelet = ("Châtelet-Les Halles", "87758607", 48.8619, 2.3470)
    ademe, stations = tmp_path / "a.parquet", tmp_path / "s.geojson"
    seed.build_ademe_dataset(ademe)
    _write_stations(stations, [chatelet])
    matcher = EmissionEntityMatcher(ademe, stations)
    assert matcher.find_nearest_station(*PARIS)["code_uic"] == "87758607"
    hubs = {uic for uic, _, _ in seed.HUBS.values()}
    restricted = matcher.find_nearest_stations(*PARIS, uics=hubs, limit=2)
    assert [s["code_uic"] for s in restricted] == ["87686006", "87391003"]
    assert restricted[0]["distance_km"] <= restricted[1]["distance_km"]


@pytest.mark.xfail(
    strict=True,
    reason="C1: request models use Pydantic lax mode",
)
def test_request_contract_is_strict(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    body = _body(PARIS, LYON)
    body["origin"]["lat"] = "48.8566"
    body["unexpected"] = True
    response = client.post("/api/v1/routing/multimodal", json=body)
    assert response.status_code == 422


@pytest.mark.xfail(
    strict=True,
    reason="B8: agent tool schema does not match its endpoint",
)
def test_agent_tool_schema_matches_its_endpoint(tmp_path):
    _, client = _build(tmp_path, OsrmRecorder())
    schema = client.get("/api/v1/agent-tools/schema").json()["function"]["parameters"]
    endpoint = client.app.openapi()["components"]["schemas"]["AgentTripRequest"]
    assert set(schema["required"]) <= set(endpoint["properties"])
