import subprocess
import sys
from pathlib import Path

import pytest

from app.services.entity_matcher import EmissionEntityMatcher

SEED_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/seed_data.py"


def test_seeded_matcher_resolves_station_and_kg_to_grams(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, SEED_SCRIPT, "--offline-demo", "--data-dir", tmp_path],
        check=True,
    )
    matcher = EmissionEntityMatcher(
        tmp_path / "ademe_base_empreinte.parquet",
        tmp_path / "sncf_stations.geojson",
    )
    assert matcher.find_nearest_station(45.7606, 4.859)["code_uic"] == "87723197"
    assert matcher.get_emission_factor("train", "TGV")["factor"] == pytest.approx(2.93)
