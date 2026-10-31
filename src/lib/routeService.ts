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

export interface BackendScenario {
  id: string;
  name: string;
  mode: string;
  distance_km: number;
  duration_min: number;
  co2_kg: number;
  is_recommended: boolean;
  geometry?: GeoJsonLineString | null;
  steps?: BackendSegment[] | null;
  segments: BackendSegment[] | null;
}

export interface BackendSavings {
  carbon_saved_kg: number;
  carbon_saved_pct: number;
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
  scenarios?: BackendScenario[];
  savings?: BackendSavings;
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
  isBaseline?: boolean;
  isRecommended?: boolean;
}

const EMPTY_GEOMETRY: GeoJsonLineString = {
  type: "LineString",
  coordinates: [],
};

const BACKEND_URL =
  process.env.NEXT_PUBLIC_ROUTING_API_URL ??
  "http://localhost:8000/api/v1/routing/multimodal";

function toSentenceCase(value: string): string {
  if (!value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

const MODE_LABELS: Record<string, string> = {
  car: "Voiture",
  carpool: "Covoiturage",
  train: "Train",
  bus: "Autocar",
  flight: "Vol",
  walk: "Marche",
  foot: "Marche",
  bike: "Vélo",
};

export function formatSegmentTitle(
  segment: Pick<BackendSegment, "mode">,
  index: number,
  totalSegments: number,
): string {
  const mode = segment.mode.toLowerCase();

  if (mode === "car") {
    if (totalSegments === 1) return "Trajet complet en voiture";
    if (index === 0) return "Accès en voiture";
    if (index === totalSegments - 1) return "Desserte finale en voiture";
    return "Trajet en voiture";
  }

  if (mode === "train") return "Trajet en train (TGV / Intercités)";
  if (mode === "flight") return "Vol direct";
  if (mode === "walk" || mode === "foot") return "Marche à pied";
  if (mode === "bike") return "Trajet à vélo";
  if (mode === "carpool") return "Trajet en covoiturage";
  if (mode === "bus") return "Trajet en bus";

  return MODE_LABELS[mode] ?? toSentenceCase(mode);
}

function normalizeGeometry(
  geometry: BackendScenario["geometry"],
): GeoJsonLineString {
  if (
    geometry &&
    geometry.type === "LineString" &&
    Array.isArray(geometry.coordinates)
  ) {
    return {
      type: "LineString",
      coordinates: geometry.coordinates.filter(
        (coordinate): coordinate is [number, number] =>
          Array.isArray(coordinate) &&
          coordinate.length >= 2 &&
          Number.isFinite(coordinate[0]) &&
          Number.isFinite(coordinate[1]),
      ),
    };
  }
  return EMPTY_GEOMETRY;
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

  return (await response.json()) as BackendItinerary;
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

  if (Array.isArray(itinerary.scenarios) && itinerary.scenarios.length > 0) {
    return itinerary.scenarios.map((scenario) => {
      const scenarioSegments = scenario.segments ?? [];
      const steps = scenarioSegments.map((segment, index) => ({
            mode: segment.mode,
            description: formatSegmentTitle(segment, index, scenarioSegments.length),
            duration: segment.duration_s,
            co2: segment.co2_grams,
            ...(segment.geometry ? { geometry: segment.geometry } : {}),
          }));

      return {
        distance: Math.round(scenario.distance_km * 1000),
        duration: Math.round(scenario.duration_min * 60),
        co2Emissions: Math.round(scenario.co2_kg * 1000),
        geometry: normalizeGeometry(scenario.geometry),
        steps,
        label: scenario.name,
        isBaseline: scenario.id === "car_thermal",
        isRecommended: scenario.is_recommended,
      };
    });
  }

  const steps = itinerary.segments.map((segment, index) => ({
    mode: segment.mode,
    description: formatSegmentTitle(segment, index, itinerary.segments.length),
    duration: segment.duration_s,
    co2: segment.co2_grams,
    ...(segment.geometry ? { geometry: segment.geometry } : {}),
  }));
  const firstGeometry =
    itinerary.segments.find((segment) => segment.geometry)?.geometry ??
    EMPTY_GEOMETRY;

  return [{
    distance: Math.round(itinerary.totals.distance_totale),
    duration: Math.round(itinerary.totals.temps_total),
    co2Emissions: Math.round(itinerary.totals.co2_total),
    geometry: firstGeometry,
    steps,
    label: "Multimodal",
  }];
}
