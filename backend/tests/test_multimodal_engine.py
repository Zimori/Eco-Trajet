import networkx as nx
from app.services.multimodal_engine import MultimodalRoutingEngine


def test_rail_dijkstra_uses_distance_and_duration(tmp_path):
    class Matcher:
        _uic_column = None

    graph = nx.Graph()
    graph.add_node("A", lat=48.0, lon=2.0)
    graph.add_node("B", lat=49.0, lon=3.0)
    graph.add_edge("A", "B", distance_km=427, duration_seconds=7080)
    engine = MultimodalRoutingEngine.__new__(MultimodalRoutingEngine)
    engine.matcher = Matcher()
    engine.rail_graph = graph
    result = engine.get_rail_segment("A", "B")
    assert result.distance_km == 427
    assert result.duration_minutes == 118
