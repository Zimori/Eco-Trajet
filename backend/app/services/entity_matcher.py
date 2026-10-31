"""Matching utilities for transport stations and ADEME emission factors."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

try:
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import Point
except ImportError as exc:  # pragma: no cover - exercised in environments without extras
    raise ImportError(
        "EmissionEntityMatcher requires geopandas, pandas and shapely. "
        "Install the geospatial backend before importing this module."
    ) from exc


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


class EmissionEntityMatcher:
    """Resolve French stations and ADEME transport emission factors.

    The input files are loaded once at construction time.  The matcher uses
    Lambert-93 (EPSG:2154) for all distance operations, so ``distance_km`` is
    a metric distance and not a distance in longitude/latitude degrees.
    """

    DEFAULT_ADEME_PATH: Final[Path] = Path("data/ademe_base_empreinte.parquet")
    DEFAULT_STATIONS_PATH: Final[Path] = Path("data/sncf_stations.geojson")
    PROJECTED_CRS: Final[str] = "EPSG:2154"
    WGS84_CRS: Final[str] = "EPSG:4326"
    # Lambert-93 covers metropolitan France, not overseas departments.
    FRANCE_BOUNDS: Final[tuple[float, float, float, float]] = (
        -5.5,
        41.0,
        10.0,
        51.6,
    )

    _MODE_ALIASES: Final[Mapping[str, frozenset[str]]] = {
        "train": frozenset({"train", "ferroviaire", "rail", "ter", "tgv", "intercites"}),
        "bus": frozenset({"bus", "autocar", "car", "transport collectif routier"}),
        "voiture": frozenset({"voiture", "auto", "automobile", "carrosserie"}),
        "avion": frozenset({"avion", "aerien", "aeroplane", "air"}),
        "velo": frozenset({"velo", "bicyclette", "bicycle"}),
        "marche": frozenset({"marche", "pied", "walking"}),
    }
    _STATION_NAME_COLUMNS: Final[tuple[str, ...]] = (
        "name",
        "nom",
        "nom_gare",
        "station_name",
        "libelle",
    )
    _UIC_COLUMNS: Final[tuple[str, ...]] = (
        "uic",
        "code_uic",
        "uic_code",
        "station_uic",
        "code",
    )
    _MODE_COLUMNS: Final[tuple[str, ...]] = (
        "mode",
        "transport_mode",
        "moyen_transport",
        "type_transport",
        "nom_de_la_donnee",
        "nom_donnee",
        "categorie",
        "sous_categorie",
    )
    _VEHICLE_COLUMNS: Final[tuple[str, ...]] = (
        "vehicle_type",
        "type_vehicle",
        "type_vehicule",
        "vehicule",
        "motorisation",
    )
    _FACTOR_COLUMNS: Final[tuple[str, ...]] = (
        "factor",
        "emission_factor",
        "facteur_emission",
        "valeur",
        "valeur_numerique",
        "co2e_g_km_passenger",
        "gco2e_km_passager",
        "valeur_numerique",
    )
    _ADEME_ID_COLUMNS: Final[tuple[str, ...]] = (
        "id_ademe",
        "ademe_id",
        "identifiant_ademe",
        "identifiant_de_la_donnee",
        "id",
        "code",
    )
    _UNIT_COLUMNS: Final[tuple[str, ...]] = ("unit", "unite", "unité")

    def __init__(
        self,
        ademe_path: str | Path = DEFAULT_ADEME_PATH,
        stations_path: str | Path = DEFAULT_STATIONS_PATH,
    ) -> None:
        """Load and validate the ADEME and SNCF datasets."""
        self.ademe_path = Path(ademe_path)
        self.stations_path = Path(stations_path)
        if not self.ademe_path.is_file():
            raise FileNotFoundError(f"ADEME dataset not found: {self.ademe_path}")
        if not self.stations_path.is_file():
            raise FileNotFoundError(f"SNCF stations dataset not found: {self.stations_path}")

        self.emission_factors: pd.DataFrame = pd.read_parquet(self.ademe_path)
        stations = gpd.read_file(self.stations_path)
        if stations.empty:
            raise EntityMatcherError("The SNCF station dataset is empty.")
        if stations.crs is None:
            raise EntityMatcherError("The SNCF station dataset has no coordinate reference system.")
        self.stations: gpd.GeoDataFrame = stations.to_crs(self.PROJECTED_CRS)
        self._station_name_column = self._find_column(self.stations, self._STATION_NAME_COLUMNS)
        self._uic_column = self._find_column(self.stations, self._UIC_COLUMNS, required=False)
        self._mode_column = self._find_column(self.emission_factors, self._MODE_COLUMNS)
        self._factor_column = self._find_column(self.emission_factors, self._FACTOR_COLUMNS)
        self._ademe_id_column = self._find_column(
            self.emission_factors, self._ADEME_ID_COLUMNS, required=False
        )
        self._unit_column = self._find_column(
            self.emission_factors, self._UNIT_COLUMNS, required=False
        )
        self._vehicle_column = self._find_column(
            self.emission_factors, self._VEHICLE_COLUMNS, required=False
        )

    def find_nearest_station(
        self, lat: float, lon: float, max_distance_km: float = 30.0
    ) -> dict[str, Any] | None:
        """Return the closest station within ``max_distance_km``.

        Raises:
            InvalidCoordinatesError: for non-finite/out-of-zone coordinates.
            ``None`` if no station lies in the search buffer.
        """
        self._validate_coordinates(lat, lon)
        if not math.isfinite(max_distance_km) or max_distance_km <= 0:
            raise ValueError("max_distance_km must be a finite number greater than zero.")

        point = gpd.GeoSeries(
            [Point(float(lon), float(lat))], crs=self.WGS84_CRS
        ).to_crs(self.PROJECTED_CRS).iloc[0]
        buffer = point.buffer(max_distance_km * 1000.0)
        try:
            candidate_indices = list(
                self.stations.sindex.query(buffer, predicate="intersects")
            )
        except TypeError:  # geopandas versions before predicate support
            candidate_indices = list(self.stations.sindex.query(buffer))
        if not candidate_indices:
            return None

        candidates = self.stations.iloc[candidate_indices].copy()
        candidates["_distance_m"] = candidates.geometry.distance(point)
        nearest = candidates.loc[candidates["_distance_m"].idxmin()]
        distance_km = float(nearest["_distance_m"]) / 1000.0
        result: dict[str, Any] = {
            "name": str(nearest[self._station_name_column]),
            "code_uic": (
                None
                if self._uic_column is None or pd.isna(nearest[self._uic_column])
                else str(nearest[self._uic_column])
            ),
            "distance_km": round(distance_km, 3),
        }
        return result

    def get_emission_factor(
        self, mode: str, vehicle_type: str | None = None
    ) -> dict[str, Any]:
        """Return an ADEME factor in gCO2e/km/passenger and its identifier."""
        normalized_mode = self._normalize_mode(mode)
        matches = self.emission_factors[
            self.emission_factors[self._mode_column]
            .fillna("")
            .map(
                lambda value: self._matches_normalized_value(
                    str(value), normalized_mode
                )
            )
        ]
        if vehicle_type is not None:
            if self._vehicle_column is None:
                raise EmissionFactorNotFoundError(
                    "This ADEME dataset has no vehicle type column."
                )
            normalized_vehicle = self._normalize_text(vehicle_type)
            matches = matches[
                matches[self._vehicle_column]
                .fillna("")
                .map(
                    lambda value: self._matches_normalized_value(
                        str(value), normalized_vehicle
                    )
                )
            ]
        if matches.empty:
            raise EmissionFactorNotFoundError(
                f"No ADEME emission factor found for mode {mode!r}"
                + (f" and vehicle type {vehicle_type!r}." if vehicle_type else ".")
            )
        if len(matches) > 1:
            raise AmbiguousEmissionFactorError(
                f"Mode {mode!r} matches {len(matches)} ADEME factors; "
                "specify vehicle_type."
            )

        row = matches.iloc[0]
        factor = self._numeric_factor(
            row[self._factor_column],
            None if self._unit_column is None else row[self._unit_column],
        )
        return {
            "factor": factor,
            "emission_factor_gco2e_km_passenger": factor,
            "ademe_id": (
                None
                if self._ademe_id_column is None or pd.isna(row[self._ademe_id_column])
                else str(row[self._ademe_id_column])
            ),
        }

    @classmethod
    def _normalize_mode(cls, value: str) -> str:
        normalized = cls._normalize_text(value)
        for canonical, aliases in cls._MODE_ALIASES.items():
            if normalized == canonical or normalized in aliases:
                return canonical
        return normalized

    @staticmethod
    def _normalize_text(value: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()

    @classmethod
    def _matches_normalized_value(cls, value: str, expected: str) -> bool:
        normalized = cls._normalize_text(value)
        return normalized == expected or expected in normalized.split()

    @staticmethod
    def _find_column(
        frame: pd.DataFrame, candidates: Sequence[str], required: bool = True
    ) -> str | None:
        by_normalized_name = {
            re.sub(r"[^a-z0-9]", "", str(column).lower()): str(column)
            for column in frame.columns
        }
        for candidate in candidates:
            column = by_normalized_name.get(re.sub(r"[^a-z0-9]", "", candidate.lower()))
            if column is not None:
                return column
        if required:
            raise EntityMatcherError(
                f"Dataset is missing a required column (accepted names: {', '.join(candidates)})."
            )
        return None

    @classmethod
    def _validate_coordinates(cls, lat: float, lon: float) -> None:
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            raise InvalidCoordinatesError("Latitude and longitude must be numeric.")
        if not math.isfinite(lat) or not math.isfinite(lon):
            raise InvalidCoordinatesError("Latitude and longitude must be finite.")
        min_lon, min_lat, max_lon, max_lat = cls.FRANCE_BOUNDS
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise InvalidCoordinatesError("Latitude or longitude is outside valid bounds.")
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            raise InvalidCoordinatesError(
                "Coordinates are outside metropolitan France (Lambert-93 coverage)."
            )

    @staticmethod
    def _numeric_factor(value: Any, unit: Any = None) -> float:
        if pd.isna(value):
            raise EntityMatcherError("The selected ADEME factor is empty.")
        try:
            factor = float(str(value).replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise EntityMatcherError(f"Invalid ADEME factor value: {value!r}.") from exc
        normalized_unit = str(unit or "").lower().replace(" ", "")
        if "kgco2" in normalized_unit or "kgco2e" in normalized_unit:
            factor *= 1000.0
        if not math.isfinite(factor) or factor < 0:
            raise EntityMatcherError(f"Invalid ADEME factor value: {value!r}.")
        return factor