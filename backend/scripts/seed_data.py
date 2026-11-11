"""Seed the reproducible ADEME, SNCF and rail-network runtime datasets.

ADEME factors and the SNCF GTFS timetable are downloaded from the public
open-data endpoints by default; the rail graph and its stations are built from
the timetable. ``--offline-demo``
works without network access: it reads a committed excerpt of the Base Carbone
and uses a hand-made graph of the main hubs (also used by the tests).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import networkx as nx
import numpy as np
import pandas as pd

SNCF_GTFS_URL = (
    "https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip"
)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
GTFS_RAIL_ROUTE_TYPE = "2"
# Replacement coaches and shuttles run under rail routes; their trips are dropped.
GTFS_ROAD_SERVICES = ("Car TER", "Car à réservation", "Navette")
# GTFS StopPoint prefix -> ADEME train vehicle type; anything else is regional (TER).
GTFS_SERVICES = {
    "TGV INOUI": "TGV",
    "OUIGO": "TGV",
    "ICE": "TGV",
    "Lyria": "TGV",
    "INTERCITES": "Intercités",
    "INTERCITES de nuit": "Intercités",
}

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
    target = _download(data_file["url"], directory / data_file["name"])
    return target, target.stem


def build_rail_graph(path: Path) -> nx.Graph:
    """Hand-made graph of the main hubs, for offline demos and tests."""
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
    path.write_text(json.dumps(nx.node_link_data(graph), ensure_ascii=False), encoding="utf-8")
    return graph


def write_stations(path: Path, graph: nx.Graph) -> None:
    """Write the graph stations as GeoJSON, the input of the spatial index."""
    features = [
        {
            "type": "Feature",
            "properties": {"name": node["name"], "code_uic": uic},
            "geometry": {"type": "Point", "coordinates": [node["lon"], node["lat"]]},
        }
        for uic, node in graph.nodes(data=True)
    ]
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )


def build_rail_graph_from_gtfs(path: Path, gtfs_zip: Path) -> nx.Graph:
    """Build the station graph from consecutive stops of every rail trip.

    Edge duration is the median timetabled time over all trips (both
    directions); distance is the straight line between the two stations, since
    the SNCF feed has no shapes. Edge ``service`` is the most frequent train type.
    """
    with zipfile.ZipFile(gtfs_zip) as feed:
        stops = pd.read_csv(feed.open("stops.txt"), dtype=str)
        routes = pd.read_csv(feed.open("routes.txt"), dtype=str)
        trips = pd.read_csv(feed.open("trips.txt"), dtype=str)
        stop_times = pd.read_csv(
            feed.open("stop_times.txt"),
            usecols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
            dtype={"trip_id": str, "arrival_time": str, "departure_time": str, "stop_id": str},
        )

    rail_routes = routes.loc[routes["route_type"] == GTFS_RAIL_ROUTE_TYPE, "route_id"]
    rail_trips = trips.loc[trips["route_id"].isin(rail_routes), "trip_id"]
    calls = stop_times[stop_times["trip_id"].isin(rail_trips)].sort_values(
        ["trip_id", "stop_sequence"]
    )
    stop_type = calls["stop_id"].str.extract(r"^StopPoint:OCE(.+)-\d{8}$")[0]
    road_trips = calls.loc[stop_type.isin(GTFS_ROAD_SERVICES), "trip_id"]
    calls = calls.assign(service=stop_type.map(GTFS_SERVICES).fillna("TER"))
    calls = calls[~calls["trip_id"].isin(road_trips)]
    parent_station = stops.set_index("stop_id")["parent_station"]
    calls["uic"] = calls["stop_id"].map(parent_station).str.removeprefix("StopArea:OCE")
    following = calls.groupby("trip_id")[["uic", "arrival_time"]].shift(-1)
    legs = pd.DataFrame(
        {
            "source": calls["uic"],
            "target": following["uic"],
            "duration_seconds": _gtfs_seconds(following["arrival_time"])
            - _gtfs_seconds(calls["departure_time"]),
            "service": calls["service"],
        }
    ).dropna()
    legs = legs[(legs["source"] != legs["target"]) & (legs["duration_seconds"] >= 0)]
    # Undirected graph: both travel directions share one edge.
    forward = legs["source"] < legs["target"]
    legs["a"] = legs["source"].where(forward, legs["target"])
    legs["b"] = legs["target"].where(forward, legs["source"])
    edges = legs.groupby(["a", "b"]).agg(
        duration_seconds=("duration_seconds", "median"),
        service=("service", lambda services: services.mode().iloc[0]),
    )

    areas = stops[stops["stop_id"].str.startswith("StopArea:OCE")].copy()
    areas["uic"] = areas["stop_id"].str.removeprefix("StopArea:OCE")
    areas = areas.set_index("uic")
    used = sorted(set(edges.index.get_level_values("a")) | set(edges.index.get_level_values("b")))
    missing = set(used) - set(areas.index)
    if missing:
        raise RuntimeError(f"GTFS stop areas missing for {len(missing)} stations, e.g. {min(missing)}.")

    graph = nx.Graph()
    for uic in used:
        area = areas.loc[uic]
        graph.add_node(uic, name=area["stop_name"], lat=float(area["stop_lat"]), lon=float(area["stop_lon"]))
    for (a, b), edge in edges.iterrows():
        distance_km = _haversine_km(graph.nodes[a], graph.nodes[b])
        graph.add_edge(
            a,
            b,
            distance_km=round(distance_km, 3),
            duration_seconds=float(edge["duration_seconds"]),
            service=edge["service"],
        )
    path.write_text(json.dumps(nx.node_link_data(graph), ensure_ascii=False), encoding="utf-8")
    return graph


def _gtfs_seconds(times: pd.Series) -> pd.Series:
    # GTFS times can exceed 24:00:00 for trips running past midnight.
    parts = times.str.split(":", expand=True).astype(float)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _haversine_km(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(np.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return float(2 * 6371.0088 * np.arcsin(np.sqrt(h)))


def _download(url: str, target: Path) -> Path:
    request = Request(url, headers={"User-Agent": "Eco-Trajet/1.0"})
    with urlopen(request, timeout=300) as response:
        target.write_bytes(response.read())
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline-demo",
        action="store_true",
        help="Skip downloads: Base Carbone excerpt and hand-made hub graph.",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    data_dir = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    build_ademe_dataset(
        data_dir / "ademe_base_empreinte.parquet",
        BASE_CARBONE_SAMPLE if args.offline_demo else None,
    )
    graph_path = data_dir / "sncf_stations_network.json"
    if args.offline_demo:
        graph = build_rail_graph(graph_path)
    else:
        gtfs = _download(SNCF_GTFS_URL, data_dir / "sncf_gtfs.zip")
        graph = build_rail_graph_from_gtfs(graph_path, gtfs)
    write_stations(data_dir / "sncf_stations.geojson", graph)
    print(f"Seeded routing datasets in {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
