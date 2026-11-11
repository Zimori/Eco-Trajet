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

They are produced by `backend/scripts/seed_data.py` (`make seed`, ~10 s) from public open data:

| Source | Used for |
|---|---|
| [SNCF GTFS](https://transport.data.gouv.fr/datasets/horaires-sncf) (TGV, Intercités, TER) | rail graph and stations |
| [ADEME Base Carbone](https://data.ademe.fr/datasets/base-carboner) | emission factors |

`--offline-demo` needs no network: it uses a committed Base Carbone excerpt (`backend/data/samples/`) and a hand-made graph of 9 hubs. The tests use the same demo data.

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
    "destination": {"lat": 45.7640, "lon": 4.8357}
  }'
```

The result contains route segments, totals, and metadata.

### GET /api/v1/agent-tools/schema

This endpoint exposes the tool schema for an agent.

```bash
curl --noproxy "*" -sS http://127.0.0.1:8000/api/v1/agent-tools/schema
```

The schema describes the `calculate_multimodal_trip` function. Its parameters are generated from the `/api/v1/agent-tools/calculate-trip` request model (`origin` and `destination` addresses).

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

- ADEME factors are extracted from the official Base Carbone export (V23.6, per passenger.km; element ids in `ADEME_FACTORS`, `backend/scripts/seed_data.py`) and stored as Parquet. An element that is missing, not "Valide générique" or not per passenger.km fails the build.
- the rail graph is built from the SNCF GTFS: one edge per pair of consecutive stops of a rail trip (replacement coaches are dropped), with the median timetabled duration over all trips and the train type (TGV / Intercités / TER) that runs it most. It is stored as a NetworkX node-link JSON (~2,500 stations, ~4,000 edges).
- the stations of that graph are written as GeoJSON for the spatial index

This avoids a heavier database layer for the first version and keeps the routing pipeline readable.

## Engineering choices

Rail emissions are computed per edge with the factor of the train type that runs it, so a trip mixing TGV and TER legs is not priced as all-TGV.

The SNCF feed has no shapes, so edge distances are straight lines between consecutive stops. This underestimates rail distance by roughly 8–15% (Paris–Lyon: 391 km vs 427 km by rail).

The ADEME data is also local. The project turns the source values into a Parquet file so lookup stays cheap and does not depend on a remote service.

## Tests

The backend tests live under `backend/tests`.

```bash
PYTHONPATH=backend python -m pytest backend/tests
```

The frontend uses Jest and needs Node/npm installed in the environment.

## Limits

- This is not a full national railway model.
- Rail distances are straight lines between consecutive stops (see above).
- The rail path minimises distance, not travel time.
- The service is built for route calculation and carbon estimates rather than a full transport data warehouse.
