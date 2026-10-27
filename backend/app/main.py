"""FastAPI application bootstrap for the multimodal routing backend."""

from __future__ import annotations

import json
import os
from pathlib import Path

import networkx as nx
from fastapi import FastAPI, Response, status

from .api.v1.endpoints.routing import NominatimGeocoder, create_routing_router
from .api.v1.router import router as v1_router
from .core.config import Settings
from .services.entity_matcher import EmissionEntityMatcher
from .services.multimodal_engine import MultimodalRoutingEngine


def create_app(
    *,
    engine: MultimodalRoutingEngine | None = None,
    geocoder: NominatimGeocoder | None = None,
) -> FastAPI:
    """Build the application, allowing fully injected test dependencies."""
    app = FastAPI(
        title="Eco-Trajet Multimodal Routing API",
        version=os.getenv("APP_VERSION", "1.0.0"),
        description="Agent-ready multimodal routing with ADEME carbon metrics.",
    )
    settings = Settings.from_env()
    if engine is None:
        engine = _build_engine_from_environment(settings)
    if geocoder is None:
        geocoder = NominatimGeocoder()

    app.include_router(
        create_routing_router(
            engine,
            geocoder,
            ademe_database_version=settings.ademe_database_version,
        )
    )
    app.include_router(v1_router)

    @app.get("/health", tags=["operations"], summary="Check backend health")
    async def health() -> dict[str, object]:
        return {
            "status": "healthy",
            "datasets_loaded": True,
            "version": settings.app_version,
        }

    return app


def _build_engine_from_environment(settings: Settings) -> MultimodalRoutingEngine:
    ademe_path = Path(os.getenv("ADEME_DATASET_PATH", settings.ademe_path))
    stations_path = Path(os.getenv("STATIONS_DATASET_PATH", settings.stations_path))
    graph_path = Path(os.getenv("RAIL_GRAPH_PATH", settings.rail_graph_path))
    missing = [
        str(path)
        for path in (ademe_path, stations_path, graph_path)
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(
            "Routing backend data is incomplete. Missing files: "
            + ", ".join(missing)
            + ". Set ADEME_DATASET_PATH, STATIONS_DATASET_PATH and "
            "RAIL_GRAPH_PATH or provide the datasets under data/."
        )

    matcher = EmissionEntityMatcher(ademe_path, stations_path)
    graph = _load_rail_graph(graph_path)
    return MultimodalRoutingEngine(
        matcher,
        graph,
        osrm_base_url=os.getenv(
            "OSRM_BASE_URL", settings.osrm_base_url
        ),
        timeout_seconds=settings.osrm_timeout_seconds,
        max_retries=settings.osrm_max_retries,
        road_vehicle_type=os.getenv("ROAD_VEHICLE_TYPE", "thermique"),
        rail_vehicle_type=os.getenv("RAIL_VEHICLE_TYPE", "TGV"),
    )


def _load_rail_graph(path: Path) -> nx.Graph:
    """Load a NetworkX node-link graph produced by the data pipeline."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        graph = nx.node_link_graph(payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Unable to load rail graph {path}.") from exc
    if not isinstance(graph, nx.Graph):
        raise TypeError(f"Rail graph {path} is not a NetworkX graph.")
    if graph.number_of_nodes() == 0:
        raise RuntimeError(f"Rail graph {path} contains no stations.")
    return graph


try:
    app = create_app()
except RuntimeError as exc:
    _startup_error = str(exc)
    app = FastAPI(
        title="Eco-Trajet Multimodal Routing API",
        version=os.getenv("APP_VERSION", "0.1.0"),
        description="Unavailable until routing datasets are installed.",
    )
    app.include_router(v1_router)

    @app.get("/health", tags=["operations"], summary="Check backend health")
    async def unavailable_health(response: Response) -> dict[str, object]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded",
            "datasets_loaded": False,
            "version": os.getenv("APP_VERSION", "1.0.0"),
            "detail": _startup_error,
        }
