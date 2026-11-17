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
    rail_available: boolean;
    rail_unavailable_reason: RailUnavailableReason | null;
  };
}

export type RailUnavailableReason = "short_trip" | "outside_rail_coverage" | "no_rail_route";

const RAIL_UNAVAILABLE_NOTES: Record<RailUnavailableReason, string> = {
  short_trip: "Trip too short for rail: car only.",
  outside_rail_coverage: "Outside French rail coverage: car only.",
  no_rail_route: "No sensible rail route for this trip: car only.",
};

export interface RouteStep {
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
  steps: RouteStep[];
  label: string;
  railNote?: string;
}

const BACKEND_URL =
  process.env.NEXT_PUBLIC_ROUTING_API_URL ??
  "http://localhost:8000/api/v1/routing/multimodal";

function assertBackendResponse(value: unknown): asserts value is BackendItinerary {
  if (!value || typeof value !== "object") {
    throw new Error("Invalid response from the routing backend.");
  }
  const response = value as Partial<BackendItinerary>;
  if (
    !Array.isArray(response.segments) ||
    !response.totals ||
    typeof response.totals.distance_totale !== "number" ||
    typeof response.totals.temps_total !== "number" ||
    typeof response.totals.co2_total !== "number"
  ) {
    throw new Error("Incomplete or malformed routing backend response.");
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
    let detail = `The routing backend answered ${response.status}.`;
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

// Single-mode options are estimated in the browser from one road route.
// Car uses the backend's ADEME factor (id 43809) so both car figures agree.
// Bus and plane are not in the ADEME dataset yet: these factors are estimates.
const OSRM_URL = "https://router.project-osrm.org/route/v1/driving";
const G_CO2_PER_KM = { car: 160, bus: 113, plane: 285 };
const KMH = { fallbackCar: 80, bus: 60, bike: 20, walk: 5, plane: 700 };
const AIRPORT_TRANSFER_S = 1800;
const AIRPORT_WAIT_S = 1800;

interface RoadRoute {
  distance: number;
  duration: number;
  geometry: GeoJsonLineString;
}

function haversineKm(a: Coordinates, b: Coordinates): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function straightLine(a: Coordinates, b: Coordinates): GeoJsonLineString {
  return { type: "LineString", coordinates: [[a.lng, a.lat], [b.lng, b.lat]] };
}

function along(a: Coordinates, b: Coordinates, ratio: number): Coordinates {
  return { lat: a.lat + (b.lat - a.lat) * ratio, lng: a.lng + (b.lng - a.lng) * ratio };
}

const hours = (km: number, kmh: number) => (km / kmh) * 3600;
const grams = (km: number, factor: number) => Math.round(km * factor);

async function fetchRoadRoute(origin: Coordinates, destination: Coordinates): Promise<RoadRoute> {
  try {
    const response = await fetch(
      `${OSRM_URL}/${origin.lng},${origin.lat};${destination.lng},${destination.lat}?overview=full&geometries=geojson`,
    );
    const body = (await response.json()) as { code?: string; routes?: RoadRoute[] };
    if (response.ok && body.code === "Ok" && body.routes?.[0]) return body.routes[0];
  } catch {
    // Fall through to the straight-line estimate below.
  }
  const km = haversineKm(origin, destination);
  return { distance: km * 1000, duration: hours(km, KMH.fallbackCar), geometry: straightLine(origin, destination) };
}

function backendRoute(itinerary: BackendItinerary): RouteSummary {
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
  const { rail_available, rail_unavailable_reason } = itinerary.metadata;
  return {
    distance: itinerary.totals.distance_totale,
    duration: itinerary.totals.temps_total,
    co2Emissions: itinerary.totals.co2_total,
    geometry: firstGeometry,
    steps,
    label: rail_available ? "Train + car" : "Car only",
    ...(rail_unavailable_reason
      ? { railNote: RAIL_UNAVAILABLE_NOTES[rail_unavailable_reason] }
      : {}),
  };
}

function roadOnly(label: string, mode: string, road: RoadRoute, duration: number, co2: number): RouteSummary {
  const km = road.distance / 1000;
  return {
    label,
    distance: Math.round(road.distance),
    duration: Math.round(duration),
    co2Emissions: co2,
    geometry: road.geometry,
    steps: [{ mode, description: `${label} (${km.toFixed(1)} km)`, duration: Math.round(duration), co2, geometry: road.geometry }],
  };
}

function busPlaneBus(origin: Coordinates, destination: Coordinates): RouteSummary {
  // No airport data: airports are placed at 2% and 98% of the straight line.
  const airportA = along(origin, destination, 0.02);
  const airportB = along(origin, destination, 0.98);
  const busInKm = haversineKm(origin, airportA);
  const flightKm = haversineKm(airportA, airportB);
  const busOutKm = haversineKm(airportB, destination);
  const flightDuration = Math.round(hours(flightKm, KMH.plane));
  const steps: RouteStep[] = [
    { mode: "bus", description: "Bus to the airport", duration: AIRPORT_TRANSFER_S, co2: grams(busInKm, G_CO2_PER_KM.bus), geometry: straightLine(origin, airportA) },
    { mode: "wait", description: "Waiting at the airport", duration: AIRPORT_WAIT_S, co2: 0 },
    { mode: "plane", description: `Flight (${flightKm.toFixed(1)} km)`, duration: flightDuration, co2: grams(flightKm, G_CO2_PER_KM.plane), geometry: straightLine(airportA, airportB) },
    { mode: "wait", description: "Waiting at arrival airport", duration: AIRPORT_WAIT_S, co2: 0 },
    { mode: "bus", description: "Bus from the airport to your destination", duration: AIRPORT_TRANSFER_S, co2: grams(busOutKm, G_CO2_PER_KM.bus), geometry: straightLine(airportB, destination) },
  ];
  return {
    label: "Bus + Plane + Bus",
    distance: Math.round((busInKm + flightKm + busOutKm) * 1000),
    duration: steps.reduce((sum, step) => sum + step.duration, 0),
    co2Emissions: steps.reduce((sum, step) => sum + step.co2, 0),
    geometry: straightLine(origin, destination),
    steps,
  };
}

export async function calculateMultimodalRoutes(
  origin: Coordinates,
  destination: Coordinates,
): Promise<RouteSummary[]> {
  const [itinerary, road] = await Promise.all([
    fetchMultimodalRoute(origin, destination),
    fetchRoadRoute(origin, destination),
  ]);
  const km = road.distance / 1000;
  const backend = backendRoute(itinerary);
  // Without rail the backend's answer is itself the car trip, so it replaces the browser estimate.
  const car = itinerary.metadata.rail_available
    ? roadOnly("Car only", "car", road, road.duration, grams(km, G_CO2_PER_KM.car))
    : backend;
  const routes = [
    car,
    ...(itinerary.metadata.rail_available ? [backend] : []),
    // A bus on the same roads is never faster than the car.
    roadOnly("Bus only", "bus", road, Math.max(car.duration, hours(km, KMH.bus)), grams(km, G_CO2_PER_KM.bus)),
    roadOnly("Bike only", "bike", road, hours(km, KMH.bike), 0),
    roadOnly("Walk only", "walk", road, hours(km, KMH.walk), 0),
    busPlaneBus(origin, destination),
  ];

  // Fastest first (selected by default), then lowest CO2, then the best time/CO2 compromise.
  const fastest = routes.reduce((a, b) => (a.duration <= b.duration ? a : b));
  const lowestCo2 = routes.reduce((a, b) => (a.co2Emissions <= b.co2Emissions ? a : b));
  const maxTime = Math.max(...routes.map((r) => r.duration));
  const maxCo2 = Math.max(...routes.map((r) => r.co2Emissions)) || 1;
  const score = (r: RouteSummary) => r.duration / maxTime + r.co2Emissions / maxCo2;
  const compromise = routes.reduce((a, b) => (score(a) <= score(b) ? a : b));
  return [...new Set([fastest, lowestCo2, compromise, ...routes])];
}
