[English](./README.md) | **Français**

# EcoTrajet

EcoTrajet est un service de calcul d'itinéraires multimodaux. Il reçoit des coordonnées, trouve les stations proches, calcule le trajet routier avec OSRM, calcule le trajet ferroviaire avec un graphe NetworkX, puis renvoie les distances, les durées et les émissions de CO2.

## Contenu du dépôt

- Frontend Next.js pour un tableau de bord et une carte
- Backend FastAPI pour le calcul d'itinéraires et les contrôles de données
- OSRM pour le calcul des trajets routiers
- NetworkX pour le graphe ferroviaire
- GeoPandas et Parquet pour les facteurs d'émission de l'ADEME et la recherche de stations

## Données d'exécution

Le backend attend la présence des fichiers suivants :

- `backend/data/ademe_base_empreinte.parquet`
- `backend/data/sncf_stations.geojson`
- `backend/data/sncf_stations_network.json`

Le script `backend/scripts/seed_data.py` produit ces fichiers.

## API

### GET /health

Renvoie un objet JSON indiquant l'état du service.

```bash
curl --noproxy "*" -sS http://127.0.0.1:8000/health | jq .
```

Réponse normale :

```json
{
  "status": "healthy",
  "datasets_loaded": true,
  "version": "1.0.0"
}
```

Si les fichiers de données sont absents, l'application renvoie une réponse 503 avec un objet JSON au lieu de s'arrêter.

### POST /api/v1/routing/multimodal

Cette route reçoit une demande de trajet et renvoie un itinéraire multimodal.

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

Le résultat contient les segments du trajet, les totaux et les métadonnées.

### GET /api/v1/agent-tools/schema

Cette route expose le schéma des outils utilisables par un agent.

```bash
curl --noproxy "*" -sS http://127.0.0.1:8000/api/v1/agent-tools/schema
```

Le schéma généré contient la fonction `calculate_multimodal_trip` avec les paramètres `origin_lat`, `origin_lon`, `dest_lat`, `dest_lon` et `preference`.

## Installation locale

### Backend

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
python backend/scripts/seed_data.py --offline-demo
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Utilisez `--noproxy "*"` lorsqu'un proxy réseau réécrit les appels vers `localhost`.

### Frontend

```bash
npm install
npm run dev
```

### Docker

```bash
make run
# ou
docker compose up --build
```

## Pipeline de données

Le projet conserve les données localement et de façon explicite :

- les facteurs ADEME sont stockés au format Parquet ;
- les données des stations sont stockées au format GeoJSON ;
- le graphe ferroviaire est stocké au format JSON de type node-link de NetworkX.

Cette organisation évite une couche de base de données plus lourde pour cette première version et garde le pipeline de calcul lisible.

## Choix techniques

Le graphe ferroviaire reste volontairement compact. Un réseau ferré national complet serait beaucoup plus grand et plus long à charger. Le graphe actuel se concentre sur les grands corridors et les principaux pôles pour maintenir un calcul rapide et prévisible.

Les données ADEME sont également locales. Le projet convertit les valeurs sources en fichier Parquet pour accélérer les recherches et éviter une dépendance à un service distant.

## Tests

Les tests du backend se trouvent dans `backend/tests`.

```bash
PYTHONPATH=backend python -m pytest backend/tests
```

Le frontend utilise Jest et nécessite Node/npm dans l'environnement.

## Limites

- Il ne s'agit pas d'un modèle complet du réseau ferroviaire national.
- Le graphe de calcul est volontairement simplifié pour réduire le temps de calcul et garantir des résultats déterministes.
- Le service calcule des itinéraires et des estimations d'émissions carbone. Il ne remplace pas un entrepôt complet de données de transport.
