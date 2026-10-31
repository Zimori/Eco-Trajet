"""Public itinerary response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SegmentDetail(BaseModel):
    mode: str
    distance_m: float = Field(ge=0)
    duration_s: float = Field(ge=0)
    co2_grams: float = Field(ge=0)
    geometry: dict[str, Any] | None = None


class CarbonMetrics(BaseModel):
    distance_totale: float = Field(ge=0)
    temps_total: float = Field(ge=0)
    co2_total: float = Field(ge=0)


class ItineraryMetadata(BaseModel):
    timestamp: datetime
    matching_reliability_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    ademe_database_version: str
    execution_time_ms: float = Field(ge=0)


class TransportScenario(BaseModel):
    id: str
    name: str
    mode: str
    distance_km: float = Field(ge=0)
    duration_min: int = Field(ge=0)
    co2_kg: float = Field(ge=0)
    is_recommended: bool = False
    geometry: dict[str, Any]
    steps: list[dict[str, Any]] | None = None
    segments: list[SegmentDetail] | None = None


class ScenarioSavings(BaseModel):
    carbon_saved_kg: float = Field(ge=0)
    carbon_saved_pct: float = Field(ge=0)


class ItineraryResponse(BaseModel):
    segments: list[SegmentDetail]
    totals: CarbonMetrics
    metadata: ItineraryMetadata
    scenarios: list[TransportScenario] = Field(default_factory=list)
    savings: ScenarioSavings | None = None

__all__ = [
    "CarbonMetrics",
    "ItineraryMetadata",
    "ItineraryResponse",
    "ScenarioSavings",
    "SegmentDetail",
    "TransportScenario",
]
