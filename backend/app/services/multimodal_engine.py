"""Asynchronous multimodal routing over OSRM and a railway NetworkX graph."""

from __future__ import annotations

import asyncio
import itertools
import math
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from .entity_matcher import EmissionEntityMatcher, InvalidCoordinatesError


class RoutingError(RuntimeError):
    """Base exception for routing failures."""


class RoadRoutingError(RoutingError):
    """Raised when OSRM cannot provide a valid route."""


class RailRoutingError(RoutingError):
    """Raised when no railway path exists or graph data is invalid."""


class ItineraryInputError(RoutingError):
    """Raised when an itinerary input is invalid."""


class RoadSegment(BaseModel):
    """A route returned by OSRM."""

    model_config = ConfigDict(frozen=True)

    mode: str
    distance_km: float = Field(ge=0)
    duration_minutes: float = Field(ge=0)
    geometry: dict[str, Any]


class RailStep(BaseModel):
    """One station visited by a railway route."""

    uic: str
    name: str | None = None


class RailSegment(BaseModel):
    """A shortest path through the railway graph."""

    model_config = ConfigDict(frozen=True)

    station_origin_uic: str
    station_dest_uic: str
    distance_km: float = Field(ge=0)
    duration_minutes: float = Field(ge=0)
    steps: list[RailStep]
    # Train type (ADEME vehicle type) -> km travelled with it.
    distance_km_by_service: dict[str, float] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None


class EmissionBreakdown(BaseModel):
    """Emissions for one itinerary segment."""

    mode: str
    distance_km: float = Field(ge=0)
    factor_gco2e_km_passenger: float = Field(ge=0)
    ademe_id: str | None = None
    emissions_gco2e: float = Field(ge=0)


class ItineraryResult(BaseModel):
    """Complete multimodal itinerary and its emission summary."""

    model_config = ConfigDict(frozen=True)

    origin: tuple[float, float]
    destination: tuple[float, float]
    access: RoadSegment
    rail: RailSegment | None = None
    egress: RoadSegment | None = None
    emissions: list[EmissionBreakdown]
    total_distance_km: float = Field(ge=0)
    total_emissions_gco2e: float = Field(ge=0)
    origin_station_distance_km: float | None = Field(default=None, ge=0)
    destination_station_distance_km: float | None = Field(default=None, ge=0)


class MultimodalRoutingEngine:
    """Orchestrate road access, rail routing and ADEME emission accounting.

    Coordinates are consistently represented as ``(latitude, longitude)`` at
    this service boundary.  OSRM requests are converted to ``longitude,
    latitude`` as required by its API.
    """

    _OSRM_PROFILES: Mapping[str, str] = {
        "car": "driving",
        "voiture": "driving",
        "bus": "driving",
        "bike": "cycling",
        "velo": "cycling",
        "foot": "foot",
        "marche": "foot",
    }

    def __init__(
        self,
        matcher: EmissionEntityMatcher,
        rail_graph: nx.Graph,
        *,
        osrm_base_url: str = "https://router.project-osrm.org",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
        road_mode: str = "car",
        road_vehicle_type: str | None = None,
        rail_vehicle_type: str = "TGV",
        station_candidates: int = 3,
        max_rail_detour_ratio: float = 2.0,
    ) -> None:
        if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
            raise ValueError("timeout_seconds must be finite and greater than zero.")
        if max_retries < 1:
            raise ValueError("max_retries must be at least one.")
        if station_candidates < 1:
            raise ValueError("station_candidates must be at least one.")
        if not math.isfinite(max_rail_detour_ratio) or max_rail_detour_ratio < 1:
            raise ValueError("max_rail_detour_ratio must be finite and at least 1.")
        if not isinstance(rail_graph, nx.Graph) or rail_graph.is_multigraph():
            raise TypeError("rail_graph must be a NetworkX Graph or DiGraph.")
        _validate_rail_graph(rail_graph)
        self.matcher = matcher
        self.rail_graph = rail_graph
        self.osrm_base_url = osrm_base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.max_retries = max_retries
        # One pooled client for every OSRM call; close it with aclose().
        self._client = client or httpx.AsyncClient(timeout=self.timeout)
        self.road_mode = road_mode
        self.road_vehicle_type = road_vehicle_type
        self.rail_vehicle_type = rail_vehicle_type
        self.station_candidates = station_candidates
        self.max_rail_detour_ratio = max_rail_detour_ratio
        # Only stations that exist in the rail graph can start or end a rail leg.
        self._rail_nodes = frozenset(str(node) for node in rail_graph.nodes)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_road_segment(
        self,
        origin: tuple[float, float],
        dest: tuple[float, float],
        mode: str = "car",
    ) -> RoadSegment:
        """Fetch a route from OSRM, retrying transient failures."""
        self._validate_coordinate_pair(origin, "origin")
        self._validate_coordinate_pair(dest, "dest")
        profile = self._OSRM_PROFILES.get(mode.strip().lower())
        if profile is None:
            raise ItineraryInputError(f"Unsupported road mode: {mode!r}.")

        url = (
            f"{self.osrm_base_url}/route/v1/{profile}/"
            f"{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
        )
        response = await self._request_with_retries(self._client, url)
        try:
            payload = response.json()
            route = payload["routes"][0]
            geometry = route["geometry"]
            distance_m = float(route["distance"])
            duration_s = float(route["duration"])
            if geometry.get("type") != "LineString" or not geometry.get("coordinates"):
                raise ValueError("OSRM returned an empty or invalid GeoJSON geometry.")
            if distance_m < 0 or duration_s < 0:
                raise ValueError("OSRM returned negative distance or duration.")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RoadRoutingError("OSRM returned an invalid route payload.") from exc
        return RoadSegment(
            mode=mode,
            distance_km=distance_m / 1000.0,
            duration_minutes=duration_s / 60.0,
            geometry=geometry,
        )

    async def _request_with_retries(
        self, client: httpx.AsyncClient, url: str
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = await client.get(
                    url,
                    params={"overview": "full", "geometries": "geojson"},
                )
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    await asyncio.sleep(0.2 * (2**attempt))
        raise RoadRoutingError(
            f"OSRM request failed after {self.max_retries} attempt(s)."
        ) from last_error

    def get_rail_segment(
        self, station_origin_uic: str, station_dest_uic: str
    ) -> RailSegment:
        """Compute the shortest rail path using Dijkstra and edge distances."""
        origin = str(station_origin_uic).strip()
        destination = str(station_dest_uic).strip()
        if not origin or not destination:
            raise RailRoutingError("Station UIC codes must not be empty.")
        if origin not in self.rail_graph or destination not in self.rail_graph:
            raise RailRoutingError(
                f"Rail graph does not contain both stations ({origin}, {destination})."
            )
        try:
            distance_km, path = nx.single_source_dijkstra(
                self.rail_graph, origin, destination, weight="distance_km"
            )
        except nx.NetworkXNoPath as exc:
            raise RailRoutingError(
                f"No rail path found between {origin} and {destination}."
            ) from exc
        nodes = [self.rail_graph.nodes[node] for node in path]
        edges = [self.rail_graph.edges[edge] for edge in itertools.pairwise(path)]
        distance_km_by_service: dict[str, float] = {}
        for edge in edges:
            service = edge.get("service", self.rail_vehicle_type)
            distance_km_by_service[service] = (
                distance_km_by_service.get(service, 0.0) + edge["distance_km"]
            )
        return RailSegment(
            station_origin_uic=origin,
            station_dest_uic=destination,
            distance_km=distance_km,
            duration_minutes=sum(edge["duration_seconds"] for edge in edges) / 60.0,
            distance_km_by_service=distance_km_by_service,
            steps=[RailStep(uic=uic, name=node["name"]) for uic, node in zip(path, nodes)],
            geometry=(
                {"type": "LineString", "coordinates": [(n["lon"], n["lat"]) for n in nodes]}
                if len(path) >= 2
                else None
            ),
        )

    async def resolve_full_multimodal_itinerary(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> ItineraryResult:
        """Resolve station matches, road access/egress, rail path and emissions."""
        self._validate_coordinate_pair(origin, "origin")
        self._validate_coordinate_pair(destination, "destination")
        if self._coordinate_distance_km(origin, destination) <= 15:
            direct = await self.get_road_segment(origin, destination, self.road_mode)
            return self._road_only_result(origin, destination, direct)

        try:
            station_pair = self._select_station_pair(origin, destination)
        except InvalidCoordinatesError:  # outside Lambert-93: no SNCF rail, road only
            station_pair = None
        if station_pair is None:
            direct = await self.get_road_segment(origin, destination, self.road_mode)
            return self._road_only_result(origin, destination, direct)
        origin_station, destination_station = station_pair
        origin_uic = origin_station["code_uic"]
        destination_uic = destination_station["code_uic"]
        access, egress = await asyncio.gather(
            self.get_road_segment(origin, self._station_coordinate(origin_uic), self.road_mode),
            self.get_road_segment(
                self._station_coordinate(destination_uic), destination, self.road_mode
            ),
        )
        rail = self.get_rail_segment(origin_uic, destination_uic)
        emissions = [
            self._emission(access.distance_km, "voiture", self.road_vehicle_type),
            self._rail_emission(rail),
            self._emission(egress.distance_km, "voiture", self.road_vehicle_type),
        ]
        return ItineraryResult(
            origin=origin,
            destination=destination,
            access=access,
            rail=rail,
            egress=egress,
            emissions=emissions,
            total_distance_km=sum(item.distance_km for item in emissions),
            total_emissions_gco2e=sum(item.emissions_gco2e for item in emissions),
            origin_station_distance_km=origin_station["distance_km"],
            destination_station_distance_km=destination_station["distance_km"],
        )

    def _select_station_pair(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Return the graph station pair minimising access + rail + egress km.

        ``None`` (road-only fallback) when every pair shares a station, has no
        rail path, or exceeds ``max_rail_detour_ratio`` x the straight-line trip.
        """
        max_cost = self.max_rail_detour_ratio * self._coordinate_distance_km(
            origin, destination
        )
        origin_stations = self.matcher.find_nearest_stations(
            *origin, limit=self.station_candidates, uics=self._rail_nodes
        )
        destination_stations = self.matcher.find_nearest_stations(
            *destination, limit=self.station_candidates, uics=self._rail_nodes
        )

        best_pair: tuple[dict[str, Any], dict[str, Any]] | None = None
        best_cost = math.inf
        for origin_station in origin_stations:
            origin_uic = origin_station["code_uic"]
            rail_lengths = nx.single_source_dijkstra_path_length(
                self.rail_graph, origin_uic, cutoff=max_cost, weight="distance_km"
            )
            for destination_station in destination_stations:
                destination_uic = destination_station["code_uic"]
                if destination_uic == origin_uic or destination_uic not in rail_lengths:
                    continue
                cost = (
                    origin_station["distance_km"]
                    + rail_lengths[destination_uic]
                    + destination_station["distance_km"]
                )
                if cost <= max_cost and cost < best_cost:
                    best_pair, best_cost = (origin_station, destination_station), cost
        return best_pair

    def _road_only_result(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        road: RoadSegment,
    ) -> ItineraryResult:
        emissions = [
            self._emission(road.distance_km, "voiture", self.road_vehicle_type)
        ]
        return ItineraryResult(
            origin=origin,
            destination=destination,
            access=road,
            rail=None,
            egress=None,
            emissions=emissions,
            total_distance_km=road.distance_km,
            total_emissions_gco2e=emissions[0].emissions_gco2e,
        )

    def _emission(
        self, distance_km: float, mode: str, vehicle_type: str | None
    ) -> EmissionBreakdown:
        factor = self.matcher.get_emission_factor(mode, vehicle_type)
        value = float(factor["factor"])
        return EmissionBreakdown(
            mode=mode,
            distance_km=distance_km,
            factor_gco2e_km_passenger=value,
            ademe_id=factor.get("ademe_id"),
            emissions_gco2e=distance_km * value,
        )

    def _rail_emission(self, rail: RailSegment) -> EmissionBreakdown:
        parts = [
            self._emission(km, "train", service)
            for service, km in rail.distance_km_by_service.items()
        ]
        emissions = sum(part.emissions_gco2e for part in parts)
        return EmissionBreakdown(
            mode="train",
            distance_km=rail.distance_km,
            factor_gco2e_km_passenger=emissions / rail.distance_km if rail.distance_km else 0.0,
            ademe_id=",".join(sorted({part.ademe_id for part in parts if part.ademe_id})) or None,
            emissions_gco2e=emissions,
        )

    def _station_coordinate(self, uic: str) -> tuple[float, float]:
        node = self.rail_graph.nodes[uic]
        return node["lat"], node["lon"]

    @staticmethod
    def _coordinate_distance_km(
        origin: tuple[float, float], destination: tuple[float, float]
    ) -> float:
        earth_radius_km = 6371.0088
        origin_lat, origin_lon = map(math.radians, origin)
        destination_lat, destination_lon = map(math.radians, destination)
        delta_lat = destination_lat - origin_lat
        delta_lon = destination_lon - origin_lon
        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(origin_lat)
            * math.cos(destination_lat)
            * math.sin(delta_lon / 2) ** 2
        )
        return 2 * earth_radius_km * math.asin(math.sqrt(haversine))

    @staticmethod
    def _validate_coordinate_pair(
        coordinates: Sequence[float], label: str
    ) -> None:
        if len(coordinates) != 2:
            raise ItineraryInputError(f"{label} must contain (latitude, longitude).")
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinates):
            raise ItineraryInputError(f"{label} must contain finite numeric coordinates.")


def _validate_rail_graph(graph: nx.Graph) -> None:
    for uic, node in graph.nodes(data=True):
        if not {"name", "lat", "lon"} <= node.keys():
            raise RailRoutingError(f"Rail graph node {uic} needs name, lat and lon.")
    for source, target, edge in graph.edges(data=True):
        values = [edge.get("distance_km"), edge.get("duration_seconds")]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values):
            raise RailRoutingError(
                f"Rail graph edge {source}-{target} needs distance_km and duration_seconds >= 0."
            )
