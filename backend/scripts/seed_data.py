#!/usr/bin/env python3
"""Seed the reproducible ADEME, SNCF and rail-network runtime datasets.

The SNCF export is downloaded from the public data endpoint by default. Use
``--offline-demo`` only for local demos without network access; that mode
creates the same normalized schema with the documented hub stations.
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

EDGES = (
    (
        "87686006",
        "87723197",
        427,
        7080,
        [
            [2.3730, 48.8443],
            [2.9500, 48.3800],
            [4.2600, 47.7100],
            [4.4900, 46.7000],
            [4.7900, 46.2700],
            [4.8590, 45.7606],
        ],
    ),
    (
        "87391003",
        "87581009",
        585,
        12600,
        [
            [2.3210, 48.8407],
            [2.8000, 48.2000],
            [0.6600, 47.3900],
            [0.7050, 47.3500],
            [0.5500, 45.1800],
            [-0.5560, 44.8250],
        ],
    ),
    (
        "87686006",
        "87223263",
        225,
        5400,
        [
            [2.3730, 48.8443],
            [2.9500, 49.3200],
            [3.0000, 49.9000],
            [2.8500, 50.2800],
            [3.0760, 50.6394],
        ],
    ),
    (
        "87686006",
        "87212027",
        490,
        12600,
        [
            [2.3730, 48.8443],
            [3.1800, 48.8600],
            [4.3800, 49.0000],
            [7.7340, 48.5851],
        ],
    ),
    (
        "87686006",
        "87471003",
        350,
        7200,
        [
            [2.3730, 48.8443],
            [2.2000, 48.0000],
            [-1.6720, 48.1035],
        ],
    ),
    (
        "87471003",
        "87481002",
        110,
        2700,
        [
            [-1.6720, 48.1035],
            [-1.5420, 47.2172],
        ],
    ),
    (
        "87723197",
        "87751008",
        315,
        6600,
        [
            [4.8590, 45.7606],
            [5.0000, 45.5000],
            [4.9100, 45.0000],
            [4.9000, 44.0000],
            [5.3800, 43.3029],
        ],
    ),
    (
        "87581009",
        "87723197",
        550,
        10800,
        [
            [-0.5560, 44.8250],
            [0.1500, 46.0000],
            [4.8590, 45.7606],
        ],
    ),
)


def build_ademe_dataset(path: Path) -> None:
    rows = [
        ("ademe-tgv-v23", "train", "TGV", 0.00293),
        ("ademe-intercites-v23", "train", "Intercités", 0.00860),
        ("ademe-ter-v23", "train", "TER", 0.02480),
        ("ademe-car-thermal-v23", "voiture", "thermique", 0.218),
        ("ademe-car-electric-v23", "voiture", "electrique", 0.103),
        ("ademe-bus-v23", "bus", "thermique", 0.113),
        ("ademe-walk-v23", "marche", "marche", 0.0),
    ]
    frame = pd.DataFrame(
        rows,
        columns=["id_ademe", "mode", "sub_mode", "emission_factor"],
    )
    frame["vehicle_type"] = frame["sub_mode"]
    frame["unit"] = "kgCO2e/p.km"
    frame["source"] = "ADEME Base Carbone V23 (2024)"
    frame.to_parquet(path, index=False)


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
    for origin, destination, distance_km, duration_seconds, geometry in EDGES:
        graph.add_edge(
            origin,
            destination,
            distance_km=distance_km,
            duration_seconds=duration_seconds,
            geometry={"type": "LineString", "coordinates": geometry},
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
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    build_ademe_dataset(DATA_DIR / "ademe_base_empreinte.parquet")
    download_stations(DATA_DIR / "sncf_stations.geojson", args.offline_demo)
    build_rail_graph(DATA_DIR / "sncf_stations_network.json")
    print(f"Seeded routing datasets in {DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
