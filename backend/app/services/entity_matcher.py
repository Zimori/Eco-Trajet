"""Matching utilities for transport stations and ADEME emission factors."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Collection
from pathlib import Path
from typing import Any, Final

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


class EntityMatcherError(ValueError):
    """Base exception for invalid matcher inputs or unavailable data."""


class InvalidCoordinatesError(EntityMatcherError):
    """Raised when coordinates are invalid or outside metropolitan France."""


class StationNotFoundError(EntityMatcherError):
    """Raised when no station is found within the requested radius."""


class EmissionFactorNotFoundError(EntityMatcherError):
    """Raised when no ADEME factor matches the requested mode."""


class AmbiguousEmissionFactorError(EntityMatcherError):
    """Raised when a mode resolves to more than one ADEME factor."""


def _normalize(value: object) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


class EmissionEntityMatcher:
    """Resolve French stations and ADEME transport emission factors.

    Reads the datasets written by ``scripts/seed_data.py``. Distances are
    computed in Lambert-93 (EPSG:2154), so ``distance_km`` is metric.
    """

    PROJECTED_CRS: Final = "EPSG:2154"
    WGS84_CRS: Final = "EPSG:4326"
    # Lambert-93 covers metropolitan France only: (min_lon, min_lat, max_lon, max_lat).
    FRANCE_BOUNDS: Final = (-5.5, 41.0, 10.0, 51.6)
    STATION_COLUMNS: Final = ("name", "code_uic")
    FACTOR_COLUMNS: Final = ("id_ademe", "mode", "vehicle_type", "emission_factor", "unit", "source")

    _MODE_ALIASES: Final = {
        "train": {"ferroviaire", "rail", "ter", "tgv", "intercites"},
        "bus": {"autocar", "car", "transport collectif routier"},
        "voiture": {"auto", "automobile"},
        "avion": {"aerien", "air"},
        "velo": {"bicyclette", "bicycle"},
        "marche": {"pied", "walking"},
    }

    def __init__(
        self,
        ademe_path: str | Path = "data/ademe_base_empreinte.parquet",
        stations_path: str | Path = "data/sncf_stations.geojson",
    ) -> None:
        factors = pd.read_parquet(ademe_path)
        stations = gpd.read_file(stations_path)
        _require_columns(factors, self.FACTOR_COLUMNS, ademe_path)
        _require_columns(stations, self.STATION_COLUMNS, stations_path)
        if stations.empty:
            raise EntityMatcherError("The SNCF station dataset is empty.")
        if stations.crs is None:
            raise EntityMatcherError("The SNCF station dataset has no coordinate reference system.")

        stations["code_uic"] = stations["code_uic"].astype(str).str.strip()
        self.stations: gpd.GeoDataFrame = stations.to_crs(self.PROJECTED_CRS)
        factors["_mode"] = factors["mode"].map(_normalize)
        factors["_vehicle"] = factors["vehicle_type"].fillna("").map(_normalize)
        self.emission_factors: pd.DataFrame = factors
        self.database_version = str(factors["source"].iloc[0]) if len(factors) else "unknown"

    def find_nearest_station(
        self, lat: float, lon: float, max_distance_km: float = 30.0
    ) -> dict[str, Any]:
        """Return the closest station within ``max_distance_km``."""
        stations = self.find_nearest_stations(lat, lon, max_distance_km=max_distance_km, limit=1)
        if not stations:
            raise StationNotFoundError(
                f"No station found within {max_distance_km:g} km of ({lat}, {lon})."
            )
        return stations[0]

    def find_nearest_stations(
        self,
        lat: float,
        lon: float,
        *,
        max_distance_km: float = 30.0,
        limit: int | None = None,
        uics: Collection[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return stations within ``max_distance_km``, closest first.

        ``uics`` restricts the search to those UIC codes (e.g. rail graph nodes).
        """
        self._validate_coordinates(lat, lon)
        if not math.isfinite(max_distance_km) or max_distance_km <= 0:
            raise ValueError("max_distance_km must be a finite number greater than zero.")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least one.")

        point = (
            gpd.GeoSeries([Point(lon, lat)], crs=self.WGS84_CRS).to_crs(self.PROJECTED_CRS).iloc[0]
        )
        indices = self.stations.sindex.query(
            point.buffer(max_distance_km * 1000.0), predicate="intersects"
        )
        candidates = self.stations.iloc[indices]
        if uics is not None:
            # Membership per candidate: Series.isin would rehash all of ``uics`` on every call.
            candidates = candidates[candidates["code_uic"].map(uics.__contains__).astype(bool)]
        distances_m = candidates.geometry.distance(point).sort_values(kind="stable")
        if limit is not None:
            distances_m = distances_m.head(limit)
        return [
            {
                "name": str(self.stations.at[index, "name"]),
                "code_uic": self.stations.at[index, "code_uic"],
                "distance_km": round(distance_m / 1000.0, 3),
            }
            for index, distance_m in distances_m.items()
        ]

    def get_emission_factor(self, mode: str, vehicle_type: str | None = None) -> dict[str, Any]:
        """Return an ADEME factor in gCO2e/km/passenger and its identifier."""
        factors = self.emission_factors
        matches = factors[factors["_mode"] == self._canonical_mode(mode)]
        if vehicle_type is not None:
            matches = matches[matches["_vehicle"] == _normalize(vehicle_type)]
        if matches.empty:
            raise EmissionFactorNotFoundError(
                f"No ADEME emission factor found for mode {mode!r}"
                + (f" and vehicle type {vehicle_type!r}." if vehicle_type else ".")
            )
        if len(matches) > 1:
            raise AmbiguousEmissionFactorError(
                f"Mode {mode!r} matches {len(matches)} ADEME factors; specify vehicle_type."
            )

        row = matches.iloc[0]
        factor = float(row["emission_factor"])
        if "kgco2" in str(row["unit"]).lower():
            factor *= 1000.0
        if not math.isfinite(factor) or factor < 0:
            raise EntityMatcherError(f"Invalid ADEME factor value: {row['emission_factor']!r}.")
        return {
            "factor": factor,
            "ademe_id": None if pd.isna(row["id_ademe"]) else str(row["id_ademe"]),
        }

    @classmethod
    def _canonical_mode(cls, mode: str) -> str:
        normalized = _normalize(mode)
        for canonical, aliases in cls._MODE_ALIASES.items():
            if normalized in aliases:
                return canonical
        return normalized

    @classmethod
    def _validate_coordinates(cls, lat: float, lon: float) -> None:
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            raise InvalidCoordinatesError("Latitude and longitude must be numeric.")
        if not math.isfinite(lat) or not math.isfinite(lon):
            raise InvalidCoordinatesError("Latitude and longitude must be finite.")
        min_lon, min_lat, max_lon, max_lat = cls.FRANCE_BOUNDS
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            raise InvalidCoordinatesError(
                "Coordinates are outside metropolitan France (Lambert-93 coverage)."
            )


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], path: str | Path) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise EntityMatcherError(f"{path} is missing columns: {', '.join(sorted(missing))}.")
