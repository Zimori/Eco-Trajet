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
    EmissionBreakdown,
    ItineraryInputError,
    ItineraryResult,
    MultimodalRoutingEngine,
    RailRoutingError,
    RailSegment,
    RailUnavailableReason,
    RoadRoutingError,
    RoadSegment,
)


class ItineraryRequest(BaseModel):
    """Coordinates of a multimodal itinerary."""

    model_config = ConfigDict(strict=True, extra="forbid", json_schema_extra={
        "example": {
            "origin": {"lat": 48.8566, "lon": 2.3522},
            "destination": {"lat": 45.764, "lon": 4.8357},
        }
    })

    class Coordinate(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")

        lat: float = Field(ge=-90, le=90)
        lon: float = Field(ge=-180, le=180)

    origin: Coordinate
    destination: Coordinate


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
    rail_available: bool
    rail_unavailable_reason: RailUnavailableReason | None = None


class ItineraryResponse(BaseModel):
    """Exhaustive itinerary response."""

    segments: list[SegmentDetail]
    totals: CarbonMetrics
    metadata: ItineraryMetadata


class AgentTripRequest(BaseModel):
    """Raw addresses accepted by the OpenAI function-calling endpoint."""

    model_config = ConfigDict(strict=True, extra="forbid")

    origin: str = Field(min_length=1, description="Departure address.")
    destination: str = Field(min_length=1, description="Arrival address.")


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
        self.client = client or httpx.AsyncClient(timeout=10)
        self.base_url = base_url

    async def aclose(self) -> None:
        await self.client.aclose()

    async def geocode(self, address: str) -> tuple[float, float]:
        try:
            response = await self.client.get(
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


def create_routing_router(
    engine: MultimodalRoutingEngine,
    geocoder: Geocoder,
) -> APIRouter:
    """Create an isolated router with explicit engine and geocoder dependencies."""
    router = APIRouter()
    ademe_database_version = engine.matcher.database_version

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
            422: {"description": "Invalid coordinates."},
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
            result = await routing_engine.resolve_full_multimodal_itinerary(origin, destination)
            return _to_response(
                result, ademe_database_version, (time.perf_counter() - started_at) * 1000
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
            origin, destination = await asyncio.gather(
                address_geocoder.geocode(request.origin),
                address_geocoder.geocode(request.destination),
            )
            result = await routing_engine.resolve_full_multimodal_itinerary(origin, destination)
        except (ValueError, ItineraryInputError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except (RoadRoutingError, RailRoutingError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        response = _to_response(
            result, ademe_database_version, (time.perf_counter() - started_at) * 1000
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


def _segment(
    leg: RoadSegment | RailSegment, mode: str, emission: EmissionBreakdown
) -> SegmentDetail:
    return SegmentDetail(
        mode=mode,
        distance_m=leg.distance_km * 1000,
        duration_s=leg.duration_minutes * 60,
        co2_grams=emission.emissions_gco2e,
        geometry=leg.geometry,
    )


def _to_response(
    result: ItineraryResult, ademe_database_version: str, execution_time_ms: float
) -> ItineraryResponse:
    access_co2 = result.emissions[0]
    segments = [_segment(result.access, result.access.mode, access_co2)]
    reliability = 0.0
    if result.rail is not None and result.egress is not None:
        _, rail_co2, egress_co2 = result.emissions
        segments += [
            _segment(result.rail, "train", rail_co2),
            _segment(result.egress, result.egress.mode, egress_co2),
        ]
        station_km = result.origin_station_distance_km + result.destination_station_distance_km
        reliability = max(0.0, 1.0 - station_km / 60.0)
    reliability = round(reliability, 3)
    return ItineraryResponse(
        segments=segments,
        totals=CarbonMetrics(
            distance_totale=sum(item.distance_m for item in segments),
            temps_total=sum(item.duration_s for item in segments),
            co2_total=sum(item.co2_grams for item in segments),
        ),
        metadata=ItineraryMetadata(
            timestamp=datetime.now(UTC),
            matching_reliability_score=reliability,
            confidence_score=reliability,
            ademe_database_version=ademe_database_version,
            execution_time_ms=round(execution_time_ms, 3),
            rail_available=result.rail is not None,
            rail_unavailable_reason=result.rail_unavailable_reason,
        ),
    )
