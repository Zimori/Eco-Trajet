"""Validated runtime configuration for the routing service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_version: str
    ademe_database_version: str
    data_dir: Path
    osrm_base_url: str
    osrm_timeout_seconds: float
    osrm_max_retries: int

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.getenv("ROUTING_DATA_DIR", "backend/data"))
        return cls(
            app_version=os.getenv("APP_VERSION", "1.0.0"),
            ademe_database_version=os.getenv(
                "ADEME_DATABASE_VERSION", "Base Carbone V23 (2024)"
            ),
            data_dir=data_dir,
            osrm_base_url=os.getenv(
                "OSRM_BASE_URL", "https://router.project-osrm.org"
            ),
            osrm_timeout_seconds=float(os.getenv("OSRM_TIMEOUT_SECONDS", "10")),
            osrm_max_retries=int(os.getenv("OSRM_MAX_RETRIES", "3")),
        )

    @property
    def ademe_path(self) -> Path:
        return self.data_dir / "ademe_base_empreinte.parquet"

    @property
    def stations_path(self) -> Path:
        return self.data_dir / "sncf_stations.geojson"

    @property
    def rail_graph_path(self) -> Path:
        return self.data_dir / "sncf_stations_network.json"
