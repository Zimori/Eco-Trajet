"""FastAPI endpoints for agent-friendly multimodal trip calculation."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Protocol

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ....services.multimodal_engine import (
    ItineraryInputError,
    ItineraryResult,
    MultimodalRoutingEngine,
    RailRoutingError,
    RoadRoutingError,
)


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


class SegmentDetail(BaseModel):
    """Serializable segment representation consumed by agents and clients."""

    mode: str
    distance_m: float = Field(ge=0)
    duration_s: float = Field(ge=0)
    co2_grams: float = Field(ge=0)
    geometry: dict | None = None


class CarbonMetrics(BaseModel):
    """Aggregate distance, time and carbon metrics."""

    distance_totale: float = Field(ge=0)
    temps_total: float = Field(ge=0)
    co2_total: float = Field(ge=0)


class ItineraryMetadata(BaseModel):
    timestamp: datetime
    matching_reliability_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    ademe_database_version: str
    execution_time_ms: float = Field(ge=0)


class ItineraryResponse(BaseModel):
    """Exhaustive itinerary response."""

    segments: list[SegmentDetail]
    totals: CarbonMetrics
    metadata: ItineraryMetadata


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
            result = await routing_engine.resolve_full_multimodal_itinerary(
                origin,
                destination,
                max_walking_distance=request.preferences.max_walking_distance,
            )
            return _to_response(
                result,
                routing_engine,
                origin,
                destination,
                ademe_database_version,
                (time.perf_counter() - started_at) * 1000,
            )
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
            distance_m=result.access.distance_km * 1000,
            duration_s=result.access.duration_minutes * 60,
            co2_grams=result.emissions[0].emissions_gco2e,
            geometry=result.access.geometry,
        ),
        SegmentDetail(
            mode="train",
            distance_m=result.rail.distance_km * 1000,
            duration_s=result.rail.duration_minutes * 60,
            co2_grams=result.emissions[1].emissions_gco2e,
            geometry=result.rail.geometry,
        ),
        SegmentDetail(
            mode=result.egress.mode,
            distance_m=result.egress.distance_km * 1000,
            duration_s=result.egress.duration_minutes * 60,
            co2_grams=result.emissions[2].emissions_gco2e,
            geometry=result.egress.geometry,
        ),
    ]
    origin_match = engine.matcher.find_nearest_station(*origin)
    destination_match = engine.matcher.find_nearest_station(*destination)
    reliability = 1.0 - min(
        1.0,
        (float(origin_match["distance_km"]) + float(destination_match["distance_km"]))
        / 60.0,
    )
    return ItineraryResponse(
        segments=segments,
        totals=CarbonMetrics(
            distance_totale=sum(item.distance_m for item in segments),
            temps_total=sum(item.duration_s for item in segments),
            co2_total=sum(item.co2_grams for item in segments),
        ),
        metadata=ItineraryMetadata(
            timestamp=datetime.now(UTC),
            matching_reliability_score=round(reliability, 3),
            confidence_score=round(reliability, 3),
            ademe_database_version=ademe_database_version,
            execution_time_ms=round(execution_time_ms, 3),
        ),
    )