export interface Coordinates {
  lat: number;
  lng: number;
}

export interface GeoJsonLineString {
  type: "LineString";
  coordinates: [number, number][];
}

export interface BackendSegment {
  mode: string;
  distance_m: number;
  duration_s: number;
  co2_grams: number;
  geometry: GeoJsonLineString | null;
}

export interface BackendItinerary {
  segments: BackendSegment[];
  totals: {
    distance_totale: number;
    temps_total: number;
    co2_total: number;
  };
  metadata: {
    timestamp: string;
    matching_reliability_score: number;
    ademe_database_version: string;
  };
}

export interface LegacyRouteStep {
  mode: string;
  description: string;
  duration: number;
  co2: number;
  geometry?: GeoJsonLineString;
}

export interface RouteSummary {
  distance: number;
  duration: number;
  co2Emissions: number;
  geometry: GeoJsonLineString;
  steps: LegacyRouteStep[];
  label: string;
}

const BACKEND_URL =
  process.env.NEXT_PUBLIC_ROUTING_API_URL ??
  "http://localhost:8000/api/v1/routing/multimodal";

function assertBackendResponse(value: unknown): asserts value is BackendItinerary {
  if (!value || typeof value !== "object") {
    throw new Error("Réponse invalide du backend de routage.");
  }
  const response = value as Partial<BackendItinerary>;
  if (
    !Array.isArray(response.segments) ||
    !response.totals ||
    typeof response.totals.distance_totale !== "number" ||
    typeof response.totals.temps_total !== "number" ||
    typeof response.totals.co2_total !== "number"
  ) {
    throw new Error("Réponse backend incomplète ou mal formée.");
  }
}

export async function fetchMultimodalRoute(
  origin: Coordinates,
  destination: Coordinates,
  signal?: AbortSignal,
): Promise<BackendItinerary> {
  const response = await fetch(BACKEND_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin: { lat: origin.lat, lon: origin.lng },
      destination: { lat: destination.lat, lon: destination.lng },
    }),
    signal,
  });

  if (!response.ok) {
    let detail = `Le backend de routage a répondu ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Preserve the HTTP error when the backend did not return JSON.
    }
    throw new Error(detail);
  }

  const payload: unknown = await response.json();
  assertBackendResponse(payload);
  return payload;
}

export async function geocodeLocation(locationName: string): Promise<Coordinates> {
  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=${encodeURIComponent(locationName)}`;
  const response = await fetch(url, {
    headers: { "User-Agent": "EcoTrajet-App/1.0" },
  });
  if (!response.ok) throw new Error("Le service de géocodage est indisponible.");
  const results: unknown = await response.json();
  if (!Array.isArray(results) || results.length === 0) {
    throw new Error(`Aucun résultat trouvé pour "${locationName}".`);
  }
  const result = results[0] as { lat?: string; lon?: string };
  const lat = Number(result.lat);
  const lng = Number(result.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    throw new Error("Le géocodage a renvoyé des coordonnées invalides.");
  }
  return { lat, lng };
}

export async function calculateMultimodalRoutes(
  origin: Coordinates,
  destination: Coordinates,
): Promise<RouteSummary[]> {
  const itinerary = await fetchMultimodalRoute(origin, destination);
  const steps = itinerary.segments.map((segment) => ({
    mode: segment.mode,
    description: segment.mode === "train" ? "Rail journey" : `${segment.mode} segment`,
    duration: segment.duration_s,
    co2: segment.co2_grams,
    ...(segment.geometry ? { geometry: segment.geometry } : {}),
  }));
  const firstGeometry =
    itinerary.segments.find((segment) => segment.geometry)?.geometry ??
    { type: "LineString", coordinates: [] };
  return [{
    distance: itinerary.totals.distance_totale,
    duration: itinerary.totals.temps_total,
    co2Emissions: itinerary.totals.co2_total,
    geometry: firstGeometry,
    steps,
    label: "Multimodal",
  }];
}
