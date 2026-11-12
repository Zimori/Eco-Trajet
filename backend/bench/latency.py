"""End-to-end latency of /api/v1/routing/multimodal on the audit probe trips.

Run against a live stack (`docker compose up osrm backend`):
    python backend/bench/latency.py --runs 50 [--url http://localhost:8000]
"""

import argparse
import json
import statistics
import time

import httpx

TRIPS = {
    "Paris-Lyon": ((48.8566, 2.3522), (45.7640, 4.8357)),
    "Paris-Bordeaux": ((48.8566, 2.3522), (44.8378, -0.5792)),
    "Paris-Marseille": ((48.8566, 2.3522), (43.2965, 5.3698)),
    "Lille-Nantes": ((50.6292, 3.0573), (47.2184, -1.5536)),
    "Grenoble-Lyon": ((45.1885, 5.7245), (45.7640, 4.8357)),
    "Toulouse-Paris": ((43.6047, 1.4442), (48.8566, 2.3522)),
}


def summarize(timings_ms):
    cuts = statistics.quantiles(timings_ms, n=100, method="inclusive")
    return {"n": len(timings_ms), "p50": round(cuts[49], 1), "p95": round(cuts[94], 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=50)
    args = parser.parse_args()

    endpoint = f"{args.url}/api/v1/routing/multimodal"
    bodies = [
        {"origin": {"lat": o[0], "lon": o[1]}, "destination": {"lat": d[0], "lon": d[1]}}
        for o, d in TRIPS.values()
    ]
    timings = []
    with httpx.Client(timeout=30) as client:
        for body in bodies:  # warm-up: first call pays OSRM page-in
            client.post(endpoint, json=body).raise_for_status()
        for _ in range(args.runs):
            for body in bodies:
                started = time.perf_counter()
                response = client.post(endpoint, json=body)
                timings.append((time.perf_counter() - started) * 1000)
                response.raise_for_status()
    print(json.dumps(summarize(timings)))


if __name__ == "__main__":
    main()
