"""Seed the reproducible ADEME, SNCF and rail-network runtime datasets.

ADEME factors and SNCF stations are downloaded from the public open-data
endpoints by default. ``--offline-demo`` works without network access: it reads
a committed excerpt of the Base Carbone and uses the hub stations only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import networkx as nx
import pandas as pd

SNCF_EXPORT_URL = (
    "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/"
    "liste-des-gares/exports/geojson"
)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

HUBS = {
    "Paris Gare de Lyon": ("87686006", 48.8443, 2.3730),
    "Paris Montparnasse": ("87391003", 48.8407, 2.3210),
    "Lyon Part-Dieu": ("87723197", 45.7606, 4.8590),
    "Marseille St-Charles": ("87751008", 43.3029, 5.3800),
    "Bordeaux St-Jean": ("87581009", 44.8250, -0.5560),
    "Lille Europe": ("87223263", 50.6394, 3.0760),
    "Strasbourg": ("87212027", 48.5851, 7.7340),
    "Rennes": ("87471003", 48.1035, -1.6720),
    "Nantes": ("87481002", 47.2172, -1.5420),
}

BASE_CARBONE_DATASET_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner"
BASE_CARBONE_SAMPLE = DATA_DIR / "samples/Base_Carbone_V23.6.csv"
# (mode, vehicle_type, Base Carbone element id); all per passenger.km.
ADEME_FACTORS = (
    ("train", "TGV", "43256"),
    ("train", "Intercités", "43272"),
    ("train", "TER", "43255"),
    ("voiture", "moyenne", "43809"),
    ("voiture", "essence", "43797"),
    ("voiture", "gazole", "43800"),
)

EDGES = (
    ("87686006", "87723197", 427, 7080),
    ("87391003", "87581009", 585, 12600),
    ("87686006", "87223263", 225, 5400),
    ("87686006", "87212027", 490, 12600),
    ("87686006", "87471003", 350, 7200),
    ("87471003", "87481002", 110, 2700),
    ("87723197", "87751008", 315, 6600),
    ("87581009", "87723197", 550, 10800),
)


def build_ademe_dataset(path: Path, base_carbone_csv: Path | None = None) -> None:
    """Extract the factors listed in ADEME_FACTORS from the official Base Carbone CSV."""
    if base_carbone_csv is None:
        base_carbone_csv, version = _download_base_carbone(path.parent)
    else:
        version = base_carbone_csv.stem
    base = pd.read_csv(base_carbone_csv, sep=";", encoding="latin-1", decimal=",", dtype=str)
    elements = base[base["Type Ligne"] == "Elément"].set_index("Identifiant de l'élément")

    rows = []
    for mode, vehicle_type, ademe_id in ADEME_FACTORS:
        if ademe_id not in elements.index:
            raise RuntimeError(f"ADEME element {ademe_id} is missing from {base_carbone_csv}.")
        element = elements.loc[ademe_id]
        status, unit = element["Statut de l'élément"], element["Unité français"]
        if status != "Valide générique" or unit != "kgCO2e/passager.km":
            raise RuntimeError(f"ADEME element {ademe_id} is {status!r} in {unit!r}.")
        value = float(element["Total poste non décomposé"].replace(",", "."))
        rows.append((ademe_id, mode, vehicle_type, value, unit, element["Nom base français"]))

    frame = pd.DataFrame(
        rows, columns=["id_ademe", "mode", "vehicle_type", "emission_factor", "unit", "ademe_name"]
    )
    frame["source"] = f"ADEME {version}"
    frame.to_parquet(path, index=False)


def _download_base_carbone(directory: Path) -> tuple[Path, str]:
    with urlopen(f"{BASE_CARBONE_DATASET_URL}/data-files", timeout=30) as response:
        data_file = json.load(response)[0]
    target = directory / data_file["name"]
    with urlopen(data_file["url"], timeout=120) as response:
        target.write_bytes(response.read())
    return target, target.stem


def download_stations(path: Path, offline_demo: bool) -> None:
    if offline_demo:
        features = []
    else:
        request = Request(SNCF_EXPORT_URL, headers={"User-Agent": "Eco-Trajet/1.0"})
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.load(response)
            features = payload.get("features", [])
        except Exception as exc:
            raise RuntimeError(
                "Unable to download the SNCF station export. Re-run with "
                "--offline-demo for a deterministic local dataset."
            ) from exc

    normalized = []
    seen_uic: set[str] = set()
    for feature in features:
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") != "Point":
            continue
        name = _first_value(properties, "name", "nom", "libelle", "nom_gare")
        uic = _first_value(properties, "uic", "code_uic", "uic_code", "code")
        if name and uic and str(uic) not in seen_uic:
            normalized.append(
                {
                    "type": "Feature",
                    "properties": {"name": str(name), "code_uic": str(uic)},
                    "geometry": geometry,
                }
            )
            seen_uic.add(str(uic))

    for name, (uic, lat, lon) in HUBS.items():
        if uic not in seen_uic:
            normalized.append(
                {
                    "type": "Feature",
                    "properties": {"name": name, "code_uic": uic},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat],
                    },
                }
            )
    path.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": normalized},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def build_rail_graph(path: Path) -> None:
    graph = nx.Graph()
    for name, (uic, lat, lon) in HUBS.items():
        graph.add_node(uic, name=name, lat=lat, lon=lon)
    for origin, destination, distance_km, duration_seconds in EDGES:
        graph.add_edge(
            origin,
            destination,
            distance_km=distance_km,
            duration_seconds=duration_seconds,
        )
    path.write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _first_value(properties: dict, *names: str) -> object:
    normalized = {
        "".join(character for character in str(key).lower() if character.isalnum()): value
        for key, value in properties.items()
    }
    for name in names:
        value = normalized.get("".join(character for character in name if character.isalnum()))
        if value not in (None, ""):
            return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline-demo",
        action="store_true",
        help="Skip the SNCF download and generate a deterministic hub dataset.",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    data_dir = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    build_ademe_dataset(
        data_dir / "ademe_base_empreinte.parquet",
        BASE_CARBONE_SAMPLE if args.offline_demo else None,
    )
    download_stations(data_dir / "sncf_stations.geojson", args.offline_demo)
    build_rail_graph(data_dir / "sncf_stations_network.json")
    print(f"Seeded routing datasets in {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
