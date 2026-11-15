import { calculateMultimodalRoutes } from "./routeService";

function response(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

const road = {
  code: "Ok",
  routes: [{ distance: 465000, duration: 15000, geometry: { type: "LineString", coordinates: [[2, 48], [3, 49]] } }],
};

function backend(railAvailable: boolean) {
  return {
    segments: railAvailable
      ? [
          { mode: "car", distance_m: 1000, duration_s: 120, co2_grams: 160, geometry: { type: "LineString", coordinates: [[2, 48], [2.01, 48.01]] } },
          { mode: "train", distance_m: 450000, duration_s: 9000, co2_grams: 1319, geometry: { type: "LineString", coordinates: [[2.01, 48.01], [3, 49]] } },
        ]
      : [{ mode: "car", distance_m: 1000, duration_s: 120, co2_grams: 160, geometry: null }],
    totals: railAvailable
      ? { distance_totale: 451000, temps_total: 9120, co2_total: 1479 }
      : { distance_totale: 1000, temps_total: 120, co2_total: 160 },
    metadata: {
      timestamp: "2026-10-27T00:00:00Z",
      matching_reliability_score: 0.98,
      ademe_database_version: "2026.1",
      rail_available: railAvailable,
      rail_unavailable_reason: railAvailable ? null : "outside_rail_coverage",
    },
  };
}

function mockFetch(railAvailable: boolean, osrm: () => Promise<Response> = async () => response(road)) {
  global.fetch = jest.fn((url: RequestInfo | URL) =>
    String(url).includes("project-osrm") ? osrm() : Promise.resolve(response(backend(railAvailable))),
  ) as jest.Mock;
}

describe("calculateMultimodalRoutes", () => {
  it("offers the backend train trip next to the single-mode options", async () => {
    mockFetch(true);
    const routes = await calculateMultimodalRoutes({ lat: 48, lng: 2 }, { lat: 49, lng: 3 });
    const labels = routes.map((r) => r.label);
    expect(labels).toEqual(expect.arrayContaining(["Car only", "Train + car", "Bus only", "Bike only", "Walk only", "Bus + Plane + Bus"]));
    expect(new Set(labels).size).toBe(labels.length);

    const train = routes.find((r) => r.label === "Train + car")!;
    expect(train.co2Emissions).toBe(1479);
    expect(train.steps).toHaveLength(2);

    const car = routes.find((r) => r.label === "Car only")!;
    expect(car.co2Emissions).toBe(Math.round(465 * 160)); // ADEME factor shared with the backend
    // fastest option first: it is the one selected by default
    expect(routes[0].duration).toBe(Math.min(...routes.map((r) => r.duration)));
  });

  it("uses the backend car trip, with its note, when rail is unavailable", async () => {
    mockFetch(false);
    const routes = await calculateMultimodalRoutes({ lat: 48, lng: 2 }, { lat: 52, lng: 13 });
    const cars = routes.filter((r) => r.label === "Car only");
    expect(cars).toHaveLength(1);
    expect(cars[0].railNote).toBe("Outside French rail coverage: car only.");
    expect(routes.some((r) => r.label === "Train + car")).toBe(false);
  });

  it("never makes the bus faster than the car", async () => {
    // Bellecour → Villeurbanne: 5.3 km of city roads, 13 min by car; 60 km/h would give the bus 5 min
    const cityRoad = { code: "Ok", routes: [{ ...road.routes[0], distance: 5300, duration: 780 }] };
    mockFetch(true, async () => response(cityRoad));
    const routes = await calculateMultimodalRoutes({ lat: 45.757, lng: 4.832 }, { lat: 45.771, lng: 4.88 });
    const car = routes.find((r) => r.label === "Car only")!;
    const bus = routes.find((r) => r.label === "Bus only")!;
    expect(bus.duration).toBe(car.duration);
  });

  it("falls back to a straight line when the road router is down", async () => {
    mockFetch(true, () => Promise.reject(new Error("offline")));
    const routes = await calculateMultimodalRoutes({ lat: 48, lng: 2 }, { lat: 49, lng: 3 });
    const bus = routes.find((r) => r.label === "Bus only")!;
    expect(bus.geometry.coordinates).toEqual([[2, 48], [3, 49]]);
    expect(bus.distance).toBeGreaterThan(130000); // ~134 km as the crow flies
  });
});
