# Latency results

End-to-end latency of `POST /api/v1/routing/multimodal`, measured with `backend/bench/latency.py`.
Client and stack on the same machine, requests sent sequentially, one warm-up pass over the 6 trips before timing.

## 2026-11-12: self-hosted OSRM, all of France

| Run | Requests | p50 | p95 |
|---|---|---|---|
| 1 | 300 | 37.9 ms | 68.3 ms |
| 2 | 300 | 36.1 ms | 48.3 ms |

- Trips: Paris→Lyon, Paris→Bordeaux, Paris→Marseille, Lille→Nantes, Grenoble→Lyon, Toulouse→Paris (50 rounds each).
- Stack: `docker compose up osrm backend`; OSRM `v5.27.1`, MLD, car profile.
- Map: Geofabrik `europe/france-latest.osm.pbf`, downloaded 2026-11-12, md5 `d09846a94fd8963c3f567d0334c47a36`.
- Rail data: SNCF GTFS + ADEME Base Carbone V23.6 from `make seed`.
- Machine: AMD Ryzen 3 4300G (8 threads), 10 GB RAM, WSL2 (kernel 6.18).

Not measured: concurrent load, network latency to a real client.

Reproduce:

```sh
make osrm-download && make osrm-data   # ~1 h, ~14 GB in ~/.cache/eco-trajet/osrm
docker compose up -d --build osrm backend
python backend/bench/latency.py --runs 50
```
