import networkx as nx

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
