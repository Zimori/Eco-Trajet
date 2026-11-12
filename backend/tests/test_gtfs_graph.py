import importlib.util
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "seed_data", Path(__file__).resolve().parents[1] / "scripts/seed_data.py"
)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)

STOPS = """stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station
StopArea:OCE87000001,Alpha,48.0,2.0,1,
StopArea:OCE87000002,Beta,48.0,3.0,1,
StopArea:OCE87000003,Gamma,48.5,3.0,1,
StopArea:OCE87000004,Delta,49.0,3.0,1,
StopPoint:OCETGV INOUI-87000001,Alpha,48.0,2.0,0,StopArea:OCE87000001
StopPoint:OCETGV INOUI-87000002,Beta,48.0,3.0,0,StopArea:OCE87000002
StopPoint:OCETrain TER-87000002,Beta,48.0,3.0,0,StopArea:OCE87000002
StopPoint:OCETrain TER-87000003,Gamma,48.5,3.0,0,StopArea:OCE87000003
StopPoint:OCECar TER-87000003,Gamma,48.5,3.0,0,StopArea:OCE87000003
StopPoint:OCECar TER-87000004,Delta,49.0,3.0,0,StopArea:OCE87000004
"""
ROUTES = "route_id,route_type\nrail,2\nbus,3\n"
TRIPS = "route_id,trip_id\nrail,tgv_out\nrail,tgv_back\nrail,ter\nrail,coach\nbus,bus\n"
STOP_TIMES = """trip_id,arrival_time,departure_time,stop_id,stop_sequence
tgv_out,08:00:00,08:00:00,StopPoint:OCETGV INOUI-87000001,0
tgv_out,09:00:00,09:00:00,StopPoint:OCETGV INOUI-87000002,1
tgv_back,23:50:00,23:50:00,StopPoint:OCETGV INOUI-87000002,0
tgv_back,25:10:00,25:10:00,StopPoint:OCETGV INOUI-87000001,1
ter,10:00:00,10:00:00,StopPoint:OCETrain TER-87000002,0
ter,10:30:00,10:30:00,StopPoint:OCETrain TER-87000003,1
coach,11:00:00,11:00:00,StopPoint:OCECar TER-87000003,0
coach,11:40:00,11:40:00,StopPoint:OCECar TER-87000004,1
bus,12:00:00,12:00:00,StopPoint:OCECar TER-87000003,0
bus,12:40:00,12:40:00,StopPoint:OCECar TER-87000004,1
"""


@pytest.fixture
def graph(tmp_path):
    feed = tmp_path / "gtfs.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        archive.writestr("stops.txt", STOPS)
        archive.writestr("routes.txt", ROUTES)
        archive.writestr("trips.txt", TRIPS)
        archive.writestr("stop_times.txt", STOP_TIMES)
    return seed.build_rail_graph_from_gtfs(tmp_path / "graph.json", feed)


def test_only_rail_trips_become_edges(graph):
    assert set(graph.nodes) == {"87000001", "87000002", "87000003"}
    assert set(map(frozenset, graph.edges)) == {
        frozenset({"87000001", "87000002"}),
        frozenset({"87000002", "87000003"}),
    }


def test_edge_duration_is_the_median_over_both_directions(graph):
    # 60 min out, 80 min back across midnight (23:50 -> 25:10).
    assert graph.edges["87000001", "87000002"]["duration_seconds"] == 70 * 60


def test_edge_carries_service_and_straight_line_distance(graph):
    edge = graph.edges["87000002", "87000003"]
    assert edge["service"] == "TER"
    assert edge["distance_km"] == pytest.approx(55.6, abs=0.1)
    assert graph.edges["87000001", "87000002"]["service"] == "TGV"
    assert graph.nodes["87000001"] == {"name": "Alpha", "lat": 48.0, "lon": 2.0}
