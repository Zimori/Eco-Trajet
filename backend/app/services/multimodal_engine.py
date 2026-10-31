"""Asynchronous multimodal routing over OSRM and a railway NetworkX graph."""

from __future__ import annotations

import asyncio
import itertools
import math
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import httpx
import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from .entity_matcher import EmissionEntityMatcher


class RoutingError(RuntimeError):
    """Base exception for routing failures."""


class RoadRoutingError(RoutingError):
    """Raised when OSRM cannot provide a valid route."""


class RailRoutingError(RoutingError):
    """Raised when no railway path exists or graph data is invalid."""


class ItineraryInputError(RoutingError):
    """Raised when an itinerary input is invalid."""


class RailGraphLike(Protocol):
    """Minimal graph protocol accepted by the engine."""

    def has_node(self, node: object) -> bool: ...


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
    rail: RailSegment
    egress: RoadSegment
    emissions: list[EmissionBreakdown]
    total_distance_km: float = Field(ge=0)
    total_emissions_gco2e: float = Field(ge=0)


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
        rail_vehicle_type: str | None = None,
    ) -> None:
        if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
            raise ValueError("timeout_seconds must be finite and greater than zero.")
        if max_retries < 1:
            raise ValueError("max_retries must be at least one.")
        if not isinstance(rail_graph, nx.Graph):
            raise TypeError("rail_graph must be a NetworkX Graph or DiGraph.")
        self.matcher = matcher
        self.rail_graph = rail_graph
        self.osrm_base_url = osrm_base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.max_retries = max_retries
        self._client = client
        self.road_mode = road_mode
        self.road_vehicle_type = road_vehicle_type
        self.rail_vehicle_type = rail_vehicle_type

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

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        url = (
            f"{self.osrm_base_url}/route/v1/{profile}/"
            f"{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
        )
        try:
            response = await self._request_with_retries(client, url)
        finally:
            if owns_client:
                await client.aclose()
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
            distance_km=round(distance_m / 1000.0, 1),
            duration_minutes=round(duration_s / 60.0, 0),
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
            path = nx.shortest_path(
                self.rail_graph, origin, destination, weight=self._edge_weight
            )
            distance_km = float(
                nx.shortest_path_length(
                    self.rail_graph, origin, destination, weight=self._edge_weight
                )
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound, TypeError, ValueError) as exc:
            raise RailRoutingError(
                f"No rail path found between {origin} and {destination}."
            ) from exc
        steps = [RailStep(uic=str(node), name=self._station_name(str(node))) for node in path]
        duration_minutes = self._rail_duration_minutes(path)
        rail_geometry = self._rail_geometry(path)
        return RailSegment(
            station_origin_uic=origin,
            station_dest_uic=destination,
            distance_km=round(distance_km, 1),
            duration_minutes=round(duration_minutes, 0),
            steps=steps,
            geometry=(
                {"type": "LineString", "coordinates": rail_geometry}
                if len(rail_geometry) >= 2
                else None
            ),
        )

    async def resolve_full_multimodal_itinerary(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        max_walking_distance: float | None = None,
        access_mode: str | None = None,
    ) -> ItineraryResult | None:
        """Resolve station matches, road access/egress, rail path and emissions."""
        if max_walking_distance is not None and (
            not math.isfinite(max_walking_distance) or max_walking_distance < 0
        ):
            raise ItineraryInputError(
                "max_walking_distance must be a finite non-negative distance in metres."
            )
        self._validate_coordinate_pair(origin, "origin")
        self._validate_coordinate_pair(destination, "destination")
        origin_hub = self._nearest_rail_hub(origin)
        destination_hub = self._nearest_rail_hub(destination)
        if (
            origin_hub is None
            or destination_hub is None
            or origin_hub[0] == destination_hub[0]
            or not nx.has_path(self.rail_graph, origin_hub[0], destination_hub[0])
        ):
            return None
        origin_uic, station_origin = origin_hub
        destination_uic, station_destination = destination_hub
        resolved_access_mode = access_mode or self.road_mode
        access, egress = await asyncio.gather(
            self.get_road_segment(origin, station_origin, resolved_access_mode),
            self.get_road_segment(station_destination, destination, resolved_access_mode),
        )
        rail = self.get_rail_segment(origin_uic, destination_uic)
        emission_mode = {
            "foot": "marche",
            "walk": "marche",
            "marche": "marche",
            "bike": "bike",
        }.get(resolved_access_mode, "voiture")
        emissions = [
            self._emission(
                access.distance_km,
                emission_mode,
                self.road_vehicle_type if emission_mode == "voiture" else None,
            ),
            self._emission(rail.distance_km, "train", self.rail_vehicle_type),
            self._emission(
                egress.distance_km,
                emission_mode,
                self.road_vehicle_type if emission_mode == "voiture" else None,
            ),
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
        )

    def _nearest_rail_hub(
        self, coordinates: tuple[float, float], max_distance_km: float = 80.0
    ) -> tuple[str, tuple[float, float]] | None:
        nearest: tuple[float, str, tuple[float, float]] | None = None
        for node, data in self.rail_graph.nodes(data=True):
            latitude = data.get("lat", data.get("latitude", data.get("y")))
            longitude = data.get(
                "lon", data.get("longitude", data.get("lng", data.get("x")))
            )
            if latitude is None or longitude is None:
                continue
            try:
                station = (float(latitude), float(longitude))
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in station):
                continue
            distance_km = self._great_circle_distance_km(coordinates, station)
            if nearest is None or distance_km < nearest[0]:
                nearest = (distance_km, str(node), station)
        if nearest is None or nearest[0] > max_distance_km:
            return None
        return nearest[1], nearest[2]

    @staticmethod
    def _great_circle_distance_km(
        origin: tuple[float, float], destination: tuple[float, float]
    ) -> float:
        radius_km = 6371.0088
        lat1, lon1 = map(math.radians, origin)
        lat2, lon2 = map(math.radians, destination)
        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1
        value = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(delta_lon / 2) ** 2
        )
        return radius_km * 2 * math.asin(math.sqrt(value))

    def _emission(
        self, distance_km: float, mode: str, vehicle_type: str | None
    ) -> EmissionBreakdown:
        if mode == "bike":
            return EmissionBreakdown(
                mode=mode,
                distance_km=round(distance_km, 1),
                factor_gco2e_km_passenger=0.0,
                emissions_gco2e=0.0,
            )
        factor = self.matcher.get_emission_factor(mode, vehicle_type)
        value = float(factor["factor"])
        emissions_gco2e = round(distance_km * value, 1)
        return EmissionBreakdown(
            mode=mode,
            distance_km=round(distance_km, 1),
            factor_gco2e_km_passenger=value,
            ademe_id=factor.get("ademe_id"),
            emissions_gco2e=emissions_gco2e,
        )

    def _station_coordinate(self, uic: str) -> tuple[float, float]:
        column = self.matcher._uic_column
        if column is None:
            raise RailRoutingError("Station dataset has no UIC column.")
        rows = self.matcher.stations[
            self.matcher.stations[column].astype(str).str.strip() == uic
        ]
        if rows.empty:
            raise RailRoutingError(f"Station {uic} is absent from the station dataset.")
        point = self.matcher.stations.to_crs(self.matcher.WGS84_CRS).loc[
            rows.index[0]
        ].geometry
        return float(point.y), float(point.x)

    def _station_name(self, uic: str) -> str | None:
        column = self.matcher._uic_column
        if column is None:
            return None
        rows = self.matcher.stations[
            self.matcher.stations[column].astype(str).str.strip() == uic
        ]
        if rows.empty:
            return None
        return str(rows.iloc[0][self.matcher._station_name_column])

    def _rail_coordinates(self, path: Sequence[object]) -> list[tuple[float, float]]:
        coordinates: list[tuple[float, float]] = []
        for node in path:
            data = self.rail_graph.nodes[node]
            lat = data.get("lat", data.get("latitude", data.get("y")))
            lon = data.get("lon", data.get("longitude", data.get("lng", data.get("x"))))
            if lat is None or lon is None:
                return []
            try:
                latitude, longitude = float(lat), float(lon)
            except (TypeError, ValueError):
                return []
            if not (math.isfinite(latitude) and math.isfinite(longitude)):
                return []
            coordinates.append((longitude, latitude))
        return coordinates

    def _rail_geometry(self, path: Sequence[object]) -> list[list[float]]:
        coordinates: list[list[float]] = []
        for source, target in itertools.pairwise(path):
            edge_data = self.rail_graph.get_edge_data(source, target)
            if not isinstance(edge_data, Mapping):
                continue
            if self.rail_graph.is_multigraph():
                edge_data = min(
                    edge_data.values(),
                    key=lambda datum: self._edge_duration_seconds(datum),
                )
            geometry = edge_data.get("geometry") if isinstance(edge_data, Mapping) else None
            if not isinstance(geometry, Mapping):
                continue
            segment = geometry.get("coordinates")
            if not isinstance(segment, list) or not segment:
                continue
            if not coordinates:
                coordinates.extend(segment)
                continue
            first = segment[0]
            if len(first) >= 2 and len(coordinates) >= 2:
                last = coordinates[-1]
                if abs(first[0] - last[0]) < 1e-9 and abs(first[1] - last[1]) < 1e-9:
                    coordinates.extend(segment[1:])
                    continue
            coordinates.extend(segment)
        if coordinates and len(coordinates) >= 2:
            return coordinates
        fallback = self._rail_coordinates(path)
        return [[lon, lat] for lon, lat in fallback]

    def _rail_duration_minutes(self, path: Sequence[object]) -> float:
        duration_seconds = 0.0
        for source, target in itertools.pairwise(path):
            edge_data = self.rail_graph.get_edge_data(source, target)
            if not isinstance(edge_data, Mapping):
                raise RailRoutingError("Rail graph edge data is invalid.")
            if self.rail_graph.is_multigraph():
                edge_data = min(
                    edge_data.values(),
                    key=lambda data: self._edge_duration_seconds(data),
                )
            duration_seconds += self._edge_duration_seconds(edge_data)
        return duration_seconds / 60.0

    @staticmethod
    def _edge_duration_seconds(data: Mapping[str, Any]) -> float:
        for key in ("duration_seconds", "duration_s"):
            if key in data:
                value = float(data[key])
                if math.isfinite(value) and value >= 0:
                    return value
        for key in ("duration_minutes", "duration_min"):
            if key in data:
                value = float(data[key]) * 60.0
                if math.isfinite(value) and value >= 0:
                    return value
        raise RailRoutingError(
            "Each rail graph edge must define duration_seconds or duration_minutes."
        )

    def _edge_weight(
        self, source: object, target: object, data: Mapping[str, Any]
    ) -> float:
        del source, target
        for key in ("distance_km", "distance", "length_km"):
            if key in data:
                value = float(data[key])
                if math.isfinite(value) and value >= 0:
                    return value
        if "length_m" in data:
            value = float(data["length_m"]) / 1000.0
            if math.isfinite(value) and value >= 0:
                return value
        raise RailRoutingError(
            "Each rail graph edge must define distance_km, distance, length_km or length_m."
        )

    @staticmethod
    def _required_uic(station: Mapping[str, Any]) -> str:
        uic = station.get("code_uic")
        if uic is None or not str(uic).strip():
            raise RailRoutingError("Nearest station has no UIC code.")
        return str(uic).strip()

    @staticmethod
    def _validate_coordinate_pair(
        coordinates: Sequence[float], label: str
    ) -> None:
        if len(coordinates) != 2:
            raise ItineraryInputError(f"{label} must contain (latitude, longitude).")
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinates):
            raise ItineraryInputError(f"{label} must contain finite numeric coordinates.")
