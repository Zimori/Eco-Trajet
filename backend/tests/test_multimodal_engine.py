import networkx as nx
import pytest

from app.services.multimodal_engine import MultimodalRoutingEngine


def test_rail_dijkstra_uses_distance_and_duration():
    graph = nx.Graph()
    graph.add_node("A", name="A", lat=48.0, lon=2.0)
    graph.add_node("B", name="B", lat=49.0, lon=3.0)
    graph.add_edge("A", "B", distance_km=427, duration_seconds=7080)
    engine = MultimodalRoutingEngine(matcher=None, rail_graph=graph)
    result = engine.get_rail_segment("A", "B")
    assert result.distance_km == 427
    assert result.duration_minutes == 118
    assert result.geometry["coordinates"] == [(2.0, 48.0), (3.0, 49.0)]


def test_rail_emissions_use_each_edge_service():
    class Matcher:
        def get_emission_factor(self, mode, vehicle_type):
            return {"factor": {"TGV": 2.93, "TER": 27.7}[vehicle_type], "ademe_id": vehicle_type}

    graph = nx.Graph()
    for uic in "ABC":
        graph.add_node(uic, name=uic, lat=48.0, lon=2.0)
    graph.add_edge("A", "B", distance_km=400, duration_seconds=7200, service="TGV")
    graph.add_edge("B", "C", distance_km=50, duration_seconds=1800, service="TER")
    engine = MultimodalRoutingEngine(matcher=Matcher(), rail_graph=graph)
    rail = engine.get_rail_segment("A", "C")
    emission = engine._rail_emission(rail)
    assert rail.distance_km_by_service == {"TGV": 400, "TER": 50}
    assert emission.emissions_gco2e == pytest.approx(400 * 2.93 + 50 * 27.7)
    assert emission.ademe_id == "TER,TGV"


@pytest.mark.parametrize("country", ["85", "80", "88", "82", "83", "71"])
def test_stations_off_the_road_map_cannot_start_or_end_a_trip(country):
    # Every foreign country in the SNCF graph; the road map is France-only.
    french, foreign = "87765008", f"{country}014001"
    graph = nx.Graph()
    graph.add_node(french, name="FR", lat=43.94, lon=4.81)
    graph.add_node(foreign, name="X", lat=46.32, lon=6.96)
    graph.add_edge(french, foreign, distance_km=400, duration_seconds=14400)
    engine = MultimodalRoutingEngine(matcher=None, rail_graph=graph)
    assert engine._rail_nodes == {french}
    # Trains may still cross the border.
    assert engine.get_rail_segment(french, foreign).distance_km == 400
