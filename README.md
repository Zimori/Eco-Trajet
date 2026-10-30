**English** | [Français](./README.fr.md)

# EcoTrajet

EcoTrajet is a small multimodal routing service. It takes coordinates, matches nearby stations, calculates the road part with OSRM, computes the rail part with a NetworkX graph, and returns distance, duration and CO2 values.

## What is in the repo

- Next.js frontend for a simple dashboard and map
- FastAPI backend for routing and data checks
- OSRM for road routing
- NetworkX for the rail graph
- GeoPandas and Parquet for ADEME emission factors and station matching

## Runtime data

The backend expects these files to be present:

- `backend/data/ademe_base_empreinte.parquet`
- `backend/data/sncf_stations.geojson`
- `backend/data/sncf_stations_network.json`

They are produced by `backend/scripts/seed_data.py`.

## API

### GET /health

Returns a JSON status object.

```bash
curl --noproxy "*" -sS http://127.0.0.1:8000/health | jq .
```

The normal response is:

```json
{
  "status": "healthy",
  "datasets_loaded": true,
  "version": "1.0.0"
}
```

If the data files are missing, the app returns a 503 response with a JSON payload instead of crashing.

### POST /api/v1/routing/multimodal

This route accepts a trip request and returns a multimodal itinerary.

```bash
curl --noproxy "*" -sS \
  -X POST http://127.0.0.1:8000/api/v1/routing/multimodal \
  -H 'Content-Type: application/json' \
  -d '{
    "origin": {"lat": 48.8566, "lon": 2.3522},
    "destination": {"lat": 45.7640, "lon": 4.8357},
    "preferences": {"max_walking_distance": 1500, "comfort": "standard"}
  }'
```

The result contains route segments, totals, and metadata.

### GET /api/v1/agent-tools/schema

This endpoint exposes the tool schema for an agent.

```bash
curl --noproxy "*" -sS http://127.0.0.1:8000/api/v1/agent-tools/schema
```

The generated schema includes the `calculate_multimodal_trip` function with `origin_lat`, `origin_lon`, `dest_lat`, `dest_lon`, and `preference`.

## Local setup

### Backend

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
python backend/scripts/seed_data.py --offline-demo
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use `--noproxy "*"` when a network proxy rewrites `localhost` calls.

### Frontend

```bash
npm install
npm run dev
```

### Docker

```bash
make run
# or
docker compose up --build
```

## Data pipeline

The project keeps data local and explicit:

- ADEME factors are stored as Parquet
- station metadata is stored as GeoJSON
- the rail graph is stored as a NetworkX node-link JSON

This avoids a heavier database layer for the first version and keeps the routing pipeline readable.

## Engineering choices

The rail graph is intentionally compact. A full national rail network would be much larger and slower to load. The current graph focuses on main corridors and major hubs so route resolution stays fast and predictable.

The ADEME data is also local. The project turns the source values into a Parquet file so lookup stays cheap and does not depend on a remote service.

## Tests

The backend tests live under `backend/tests`.

```bash
PYTHONPATH=backend python -m pytest backend/tests
```

The frontend uses Jest and needs Node/npm installed in the environment.

## Limits

- This is not a full national railway model.
- The routing graph is intentionally simplified for speed and determinism.
- The service is built for route calculation and carbon estimates rather than a full transport data warehouse.
