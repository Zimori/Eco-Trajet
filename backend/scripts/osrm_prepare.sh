#!/usr/bin/env bash
# Download the France OSM extract and build the OSRM car graph (MLD).
# Data stays outside the repo: OSRM_DATA_DIR (default ~/.cache/eco-trajet/osrm).
# Usage: osrm_prepare.sh download | build | all
set -euo pipefail

DATA_DIR="${OSRM_DATA_DIR:-$HOME/.cache/eco-trajet/osrm}"
REGION="${OSRM_REGION:-europe/france}"
URL="https://download.geofabrik.de/${REGION}-latest.osm.pbf"
PBF="$(basename "$REGION").osm.pbf"
IMAGE="ghcr.io/project-osrm/osrm-backend:v5.27.1"

mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

download() {
  curl -fL --retry 5 -C - -o "$PBF" "$URL"
  # Geofabrik publishes one md5 per file; it names the dated file, so compare hashes only.
  curl -fsSL "$URL.md5" | awk '{print $1}' > "$PBF.md5"
  echo "$(cat "$PBF.md5")  $PBF" | md5sum -c -
  printf '{"source": "%s", "downloaded_at": "%s", "md5": "%s"}\n' \
    "$URL" "$(date -u +%FT%TZ)" "$(cat "$PBF.md5")" > manifest.json
}

build() {
  local name="${PBF%.osm.pbf}"
  docker run --rm -v "$DATA_DIR:/data" "$IMAGE" osrm-extract -p /opt/car.lua "/data/$PBF"
  docker run --rm -v "$DATA_DIR:/data" "$IMAGE" osrm-partition "/data/$name.osrm"
  docker run --rm -v "$DATA_DIR:/data" "$IMAGE" osrm-customize "/data/$name.osrm"
}

case "${1:-all}" in
  download) download ;;
  build) build ;;
  all) download && build ;;
  *) echo "usage: $0 download|build|all" >&2; exit 2 ;;
esac
