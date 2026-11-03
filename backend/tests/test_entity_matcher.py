from pathlib import Path

import pytest

from app.services.entity_matcher import EmissionEntityMatcher


def test_seeded_matcher_resolves_station_and_kg_to_grams(tmp_path: Path) -> None:
    import subprocess
    import sys

    repository_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "backend/scripts/seed_data.py", "--offline-demo"],
        check=True,
        cwd=repository_root,
    )
    matcher = EmissionEntityMatcher(
        repository_root / "backend/data/ademe_base_empreinte.parquet",
        repository_root / "backend/data/sncf_stations.geojson",
    )
    assert matcher.find_nearest_station(45.7606, 4.859)["code_uic"] == "87723197"
    assert matcher.get_emission_factor("train", "TGV")["factor"] == pytest.approx(2.93)
