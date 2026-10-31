"""FastAPI endpoints for agent-friendly multimodal trip calculation."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import UTC, datetime
from typing import Protocol

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ....schemas.itinerary import (
    CarbonMetrics,
    ItineraryMetadata,
    ItineraryResponse,
    ScenarioSavings,
    SegmentDetail,
    TransportScenario,
)
from ....services.multimodal_engine import (
    ItineraryInputError,
    ItineraryResult,
    MultimodalRoutingEngine,
    RailRoutingError,
    RoadRoutingError,
)

logger = logging.getLogger(__name__)


class ItineraryRequest(BaseModel):
    """Coordinates and traveller preferences for a multimodal itinerary."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "origin": {"lat": 48.8566, "lon": 2.3522},
            "destination": {"lat": 45.764, "lon": 4.8357},
            "preferences": {"max_walking_distance": 1500},
        }
    })

    class Coordinate(BaseModel):
        lat: float = Field(ge=-90, le=90)
        lon: float = Field(ge=-180, le=180)

    class Preferences(BaseModel):
        max_walking_distance: float | None = Field(default=1500, ge=0)
        comfort: str | None = Field(default="standard", min_length=1)

    origin: Coordinate
    destination: Coordinate
    preferences: Preferences = Field(default_factory=Preferences)


class AgentTripRequest(BaseModel):
    """Raw addresses accepted by the OpenAI function-calling endpoint."""

    origin: str = Field(min_length=1, description="Departure address.")
    destination: str = Field(min_length=1, description="Arrival address.")
    preferences: ItineraryRequest.Preferences = Field(
        default_factory=ItineraryRequest.Preferences
    )


class AgentTripSummary(BaseModel):
    """Compact, deterministic summary for an LLM system prompt."""

    status: str
    origin: str
    destination: str
    summary: str
    total_distance_m: float
    total_duration_s: float
    total_co2_grams: float
    modes: list[str]
    matching_reliability_score: float


class Geocoder(Protocol):
    async def geocode(self, address: str) -> tuple[float, float]: ...


class NominatimGeocoder:
    """Minimal async geocoder; inject a different provider in production."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://nominatim.openstreetmap.org/search",
    ) -> None:
        self.client = client
        self.base_url = base_url

    async def geocode(self, address: str) -> tuple[float, float]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=10)
        try:
            response = await client.get(
                self.base_url,
                params={"q": address, "format": "jsonv2", "limit": 1},
                headers={"User-Agent": "Eco-Trajet/1.0"},
            )
            response.raise_for_status()
            results = response.json()
            if not results:
                raise ValueError(f"Address not found: {address!r}.")
            return float(results[0]["lat"]), float(results[0]["lon"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"Unable to geocode address {address!r}.") from exc
        finally:
            if owns_client:
                await client.aclose()


def create_routing_router(
    engine: MultimodalRoutingEngine,
    geocoder: Geocoder,
    *,
    ademe_database_version: str = "unknown",
) -> APIRouter:
    """Create an isolated router with explicit engine and geocoder dependencies."""
    router = APIRouter()

    def get_engine() -> MultimodalRoutingEngine:
        return engine

    def get_geocoder() -> Geocoder:
        return geocoder

    @router.post(
        "/api/v1/routing/multimodal",
        response_model=ItineraryResponse,
        summary="Calculate a multimodal itinerary",
        description=(
            "Matches nearby rail stations, calculates road access and egress "
            "with OSRM, and computes the shortest rail path with ADEME carbon metrics."
        ),
        responses={
            422: {"description": "Invalid coordinates or preferences."},
            502: {"description": "Routing provider or railway graph failure."},
        },
    )
    async def calculate_multimodal(
        request: ItineraryRequest,
        routing_engine: MultimodalRoutingEngine = Depends(get_engine),  # noqa: B008
    ) -> ItineraryResponse:
        try:
            started_at = time.perf_counter()
            origin = (request.origin.lat, request.origin.lon)
            destination = (request.destination.lat, request.destination.lon)
            direct_thermal = await routing_engine.get_road_segment(origin, destination, "car")
            direct_km = direct_thermal.distance_km
            scenarios = await _build_scenarios(
                routing_engine,
                origin,
                destination,
                direct_thermal,
                max_walking_distance=request.preferences.max_walking_distance,
            )
            recommended_id = _select_recommended_scenario(
                scenarios, direct_km
            )
            scenarios = [
                scenario.model_copy(
                    update={"is_recommended": scenario.id == recommended_id}
                )
                for scenario in scenarios
            ]
            selected = next(
                scenario for scenario in scenarios if scenario.id == recommended_id
            )
            response = _scenario_response(
                selected,
                routing_engine,
                origin,
                destination,
                ademe_database_version,
                (time.perf_counter() - started_at) * 1000,
            )
            response.scenarios = scenarios
            baseline = next(
                scenario
                for scenario in scenarios
                if scenario.id == "car_thermal"
            )
            saved = max(0.0, baseline.co2_kg - selected.co2_kg)
            response.savings = ScenarioSavings(
                carbon_saved_kg=round(saved, 2),
                carbon_saved_pct=round(
                    saved / baseline.co2_kg * 100 if baseline.co2_kg else 0.0,
                    1,
                ),
            )
            return response
        except (ItineraryInputError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except (RoadRoutingError, RailRoutingError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    @router.post(
        "/api/v1/agent-tools/calculate-trip",
        response_model=AgentTripSummary,
        summary="Calculate a trip from raw addresses",
        description=(
            "OpenAI Function Calling-compatible tool endpoint. Geocodes both raw "
            "addresses asynchronously and returns a compact agent-consumable summary."
        ),
        responses={
            422: {"description": "Address could not be geocoded."},
            502: {"description": "Routing provider or railway graph failure."},
        },
    )
    async def calculate_trip_for_agent(
        request: AgentTripRequest,
        routing_engine: MultimodalRoutingEngine = Depends(get_engine),  # noqa: B008
        address_geocoder: Geocoder = Depends(get_geocoder),  # noqa: B008
    ) -> AgentTripSummary:
        try:
            started_at = time.perf_counter()
            origin, destination = await _geocode_pair(
                address_geocoder, request.origin, request.destination
            )
            result = await routing_engine.resolve_full_multimodal_itinerary(
                origin,
                destination,
                max_walking_distance=request.preferences.max_walking_distance,
            )
            if result is None:
                raise RailRoutingError("No compatible rail hubs were found.")
        except (ValueError, ItineraryInputError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except (RoadRoutingError, RailRoutingError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        response = _to_response(
            result,
            routing_engine,
            origin,
            destination,
            ademe_database_version,
            (time.perf_counter() - started_at) * 1000,
        )
        return AgentTripSummary(
            status="ok",
            origin=request.origin,
            destination=request.destination,
            summary=(
                f"{', '.join(segment.mode for segment in response.segments)}; "
                f"{response.totals.distance_totale:.0f} m, "
                f"{response.totals.co2_total:.1f} gCO2e."
            ),
            total_distance_m=response.totals.distance_totale,
            total_duration_s=response.totals.temps_total,
            total_co2_grams=response.totals.co2_total,
            modes=[segment.mode for segment in response.segments],
            matching_reliability_score=response.metadata.matching_reliability_score,
        )

    return router


async def _geocode_pair(
    geocoder: Geocoder, origin: str, destination: str
) -> tuple[tuple[float, float], tuple[float, float]]:
    return await asyncio.gather(
        geocoder.geocode(origin), geocoder.geocode(destination)
    )


async def _build_scenarios(
    engine: MultimodalRoutingEngine,
    origin: tuple[float, float],
    destination: tuple[float, float],
    direct_thermal,
    *,
    max_walking_distance: float | None,
) -> list[TransportScenario]:
    direct_km = direct_thermal.distance_km
    scenarios = [
        _road_scenario(
            "car_thermal",
            "Voiture thermique (Direct)",
            "car",
            direct_thermal,
            0.218,
            origin,
            destination,
        ),
        _road_scenario(
            "car_electric",
            "Voiture électrique (Direct)",
            "car",
            direct_thermal,
            0.103,
            origin,
            destination,
        ),
    ]

    if direct_km < 3:
        walk = await engine.get_road_segment(origin, destination, "foot")
        bike = await engine.get_road_segment(origin, destination, "bike")
        scenarios = [
            _road_scenario("walk", "Marche à pied", "walk", walk, 0.0, origin, destination),
            _road_scenario("bike", "Vélo", "bike", bike, 0.0, origin, destination),
            *scenarios,
        ]
    elif direct_km < 20:
        if direct_km < 10:
            bike = await engine.get_road_segment(origin, destination, "bike")
            scenarios.insert(
                0, _road_scenario("bike", "Vélo", "bike", bike, 0.0, origin, destination)
            )
    else:
        car_multimodal = await _try_multimodal_scenario(
            engine,
            origin,
            destination,
            access_mode="car",
            scenario_id="multimodal",
            name="Train + Accès route",
            max_walking_distance=max_walking_distance,
            direct_km=direct_km,
        )
        if car_multimodal:
            scenarios.insert(0, car_multimodal)

    carpool = _road_scenario(
        "carpool",
        "Covoiturage (3 pers.)",
        "carpool",
        direct_thermal,
        0.218 / 3,
        origin,
        destination,
    )
    bus = _road_scenario(
        "bus",
        "Autocar longue distance",
        "bus",
        direct_thermal,
        0.030,
        origin,
        destination,
        duration_multiplier=1.25,
    )
    scenarios.extend((carpool, bus))
    if direct_km > 250:
        scenarios.append(
            _flight_scenario(direct_thermal, origin, destination)
        )

    return scenarios


async def _try_multimodal_scenario(
    engine: MultimodalRoutingEngine,
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    access_mode: str,
    scenario_id: str,
    name: str,
    max_walking_distance: float | None,
    direct_km: float,
    require_access_limit: bool = False,
) -> TransportScenario | None:
    try:
        result = await engine.resolve_full_multimodal_itinerary(
            origin,
            destination,
            max_walking_distance=max_walking_distance,
            access_mode=access_mode,
        )
    except (ItineraryInputError, RailRoutingError, RoadRoutingError):
        logger.exception(
            "Multimodal scenario failed: id=%s access_mode=%s origin=%s destination=%s",
            scenario_id,
            access_mode,
            origin,
            destination,
        )
        return None
    if result is None:
        return None

    if result.rail.station_origin_uic == result.rail.station_dest_uic:
        return None
    if require_access_limit and max_walking_distance is not None and (
        result.access.distance_km * 1000 > max_walking_distance
        or result.egress.distance_km * 1000 > max_walking_distance
    ):
        return None
    response = _to_response(result, engine, origin, destination, "unknown", 0)
    distance_km = response.totals.distance_totale / 1000
    if distance_km > direct_km * 1.8:
        return None
    return TransportScenario(
        id=scenario_id,
        name=name,
        mode="train",
        distance_km=round(distance_km, 1),
        duration_min=round(response.totals.temps_total / 60),
        co2_kg=round(response.totals.co2_total / 1000, 2),
        geometry=_ensure_geometry(
            _merge_segment_geometries(response.segments), origin, destination
        ),
        steps=[segment.model_dump() for segment in response.segments],
        segments=response.segments,
    )


def _road_scenario(
    scenario_id: str,
    name: str,
    mode: str,
    route,
    factor_kg_per_km: float,
    origin: tuple[float, float],
    destination: tuple[float, float],
    duration_multiplier: float = 1.0,
) -> TransportScenario:
    geometry = _ensure_geometry(route.geometry, origin, destination)
    segment = SegmentDetail(
        mode=route.mode,
        distance_m=round(route.distance_km * 1000),
        duration_s=round(route.duration_minutes * duration_multiplier * 60),
        co2_grams=round(route.distance_km * factor_kg_per_km * 1000, 1),
        geometry=geometry,
    )
    return TransportScenario(
        id=scenario_id,
        name=name,
        distance_km=round(route.distance_km, 1),
        duration_min=round(route.duration_minutes * duration_multiplier),
        co2_kg=round(segment.co2_grams / 1000, 2),
        mode=mode,
        geometry=geometry,
        steps=[segment.model_dump()],
        segments=[segment],
    )


def _flight_scenario(
    route,
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> TransportScenario:
    distance_km = _great_circle_distance_km(origin, destination)
    geometry = _ensure_geometry(None, origin, destination)
    segment = SegmentDetail(
        mode="flight",
        distance_m=round(distance_km * 1000),
        duration_s=9000,
        co2_grams=round(distance_km * 0.259 * 1000, 1),
        geometry=geometry,
    )
    return TransportScenario(
        id="flight",
        name="Avion (comparateur d'impact)",
        mode="flight",
        distance_km=round(distance_km, 1),
        duration_min=150,
        co2_kg=round(segment.co2_grams / 1000, 2),
        geometry=geometry,
        steps=[segment.model_dump()],
        segments=[segment],
    )


def _great_circle_distance_km(
    origin: tuple[float, float], destination: tuple[float, float]
) -> float:
    radius_km = 6371.0088
    lat1, lon1 = map(math.radians, origin)
    lat2, lon2 = map(math.radians, destination)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return radius_km * 2 * math.asin(math.sqrt(haversine))


def _merge_segment_geometries(segments: list[SegmentDetail]) -> dict:
    coordinates: list[list[float]] = []
    for segment in segments:
        geometry = segment.geometry
        if not isinstance(geometry, dict):
            continue
        segment_coordinates = geometry.get("coordinates")
        if not isinstance(segment_coordinates, list):
            continue
        for coordinate in segment_coordinates:
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
                continue
            point = [float(coordinate[0]), float(coordinate[1])]
            if coordinates and coordinates[-1] == point:
                continue
            coordinates.append(point)
    return {"type": "LineString", "coordinates": coordinates}


def _ensure_geometry(
    geometry: dict | None,
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict:
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        return {"type": "LineString", "coordinates": coordinates}
    return {
        "type": "LineString",
        "coordinates": [
            [origin[1], origin[0]],
            [destination[1], destination[0]],
        ],
    }


def _select_recommended_scenario(
    scenarios: list[TransportScenario], direct_km: float
) -> str:
    by_id = {scenario.id: scenario for scenario in scenarios}
    thermal = by_id["car_thermal"]
    if direct_km < 3:
        bike = by_id.get("bike")
        walk = by_id.get("walk")
        if bike and walk:
            return bike.id if bike.duration_min <= walk.duration_min else walk.id
    if direct_km < 10 and "bike" in by_id:
        bike = by_id["bike"]
        if bike.duration_min <= thermal.duration_min * 1.5:
            return bike.id
    multimodal = by_id.get("multimodal")
    if (
        multimodal
        and multimodal.co2_kg < thermal.co2_kg
        and multimodal.duration_min <= thermal.duration_min
    ):
        return multimodal.id
    walk_train = by_id.get("walk_train_walk")
    if (
        walk_train
        and walk_train.co2_kg < thermal.co2_kg
        and walk_train.duration_min <= thermal.duration_min * 1.5
    ):
        return walk_train.id
    electric = by_id["car_electric"]
    if electric.co2_kg < thermal.co2_kg:
        return electric.id
    return thermal.id


def _scenario_response(
    scenario: TransportScenario,
    engine: MultimodalRoutingEngine,
    origin: tuple[float, float],
    destination: tuple[float, float],
    ademe_database_version: str,
    execution_time_ms: float,
) -> ItineraryResponse:
    segments = scenario.segments or []
    totals = CarbonMetrics(
        distance_totale=round(sum(segment.distance_m for segment in segments)),
        temps_total=round(sum(segment.duration_s for segment in segments)),
        co2_total=round(sum(segment.co2_grams for segment in segments), 1),
    )
    reliability = _matching_reliability(engine, origin, destination)
    return ItineraryResponse(
        segments=segments,
        totals=totals,
        metadata=ItineraryMetadata(
            timestamp=datetime.now(UTC),
            matching_reliability_score=round(reliability, 3),
            confidence_score=round(reliability, 3),
            ademe_database_version=ademe_database_version,
            execution_time_ms=round(execution_time_ms, 3),
        ),
    )


def _to_response(
    result: ItineraryResult,
    engine: MultimodalRoutingEngine,
    origin: tuple[float, float],
    destination: tuple[float, float],
    ademe_database_version: str,
    execution_time_ms: float,
) -> ItineraryResponse:
    segments = [
        SegmentDetail(
            mode=result.access.mode,
            distance_m=round(result.access.distance_km * 1000.0, 0),
            duration_s=round(result.access.duration_minutes * 60.0, 0),
            co2_grams=round(result.emissions[0].emissions_gco2e, 1),
            geometry=result.access.geometry,
        ),
        SegmentDetail(
            mode="train",
            distance_m=round(result.rail.distance_km * 1000.0, 0),
            duration_s=round(result.rail.duration_minutes * 60.0, 0),
            co2_grams=round(result.emissions[1].emissions_gco2e, 1),
            geometry=result.rail.geometry,
        ),
        SegmentDetail(
            mode=result.egress.mode,
            distance_m=round(result.egress.distance_km * 1000.0, 0),
            duration_s=round(result.egress.duration_minutes * 60.0, 0),
            co2_grams=round(result.emissions[2].emissions_gco2e, 1),
            geometry=result.egress.geometry,
        ),
    ]
    reliability = _matching_reliability(engine, origin, destination)
    return ItineraryResponse(
        segments=segments,
        totals=CarbonMetrics(
            distance_totale=round(sum(item.distance_m for item in segments), 0),
            temps_total=round(sum(item.duration_s for item in segments), 0),
            co2_total=round(sum(item.co2_grams for item in segments), 1),
        ),
        metadata=ItineraryMetadata(
            timestamp=datetime.now(UTC),
            matching_reliability_score=round(reliability, 3),
            confidence_score=round(reliability, 3),
            ademe_database_version=ademe_database_version,
            execution_time_ms=round(execution_time_ms, 3),
        ),
    )


def _matching_reliability(
    engine: MultimodalRoutingEngine,
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> float:
    origin_match = engine.matcher.find_nearest_station(*origin)
    destination_match = engine.matcher.find_nearest_station(*destination)
    if origin_match is None or destination_match is None:
        return 0.0
    distance_km = float(origin_match["distance_km"]) + float(
        destination_match["distance_km"]
    )
    return round(1.0 - min(1.0, distance_km / 60.0), 3)