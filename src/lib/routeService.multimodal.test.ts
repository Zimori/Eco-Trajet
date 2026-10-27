import { calculateMultimodalRoutes } from "./routeService";

function response(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

describe("calculateMultimodalRoutes", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue(
      response({
          segments: [
            {
              mode: "car",
              distance_m: 1000,
              duration_s: 120,
              co2_grams: 218,
              geometry: { type: "LineString", coordinates: [[2, 48], [2.01, 48.01]] },
            },
            {
              mode: "train",
              distance_m: 450000,
              duration_s: 9000,
              co2_grams: 1318.5,
              geometry: { type: "LineString", coordinates: [[2.01, 48.01], [3, 49]] },
            },
          ],
          totals: {
            distance_totale: 451000,
            temps_total: 9120,
            co2_total: 1536.5,
          },
          metadata: {
            timestamp: "2026-10-27T00:00:00Z",
            matching_reliability_score: 0.98,
            ademe_database_version: "2026.1",
          },
        }),
    );
  });

  it("maps backend segments without local scenario simulation", async () => {
    const [route] = await calculateMultimodalRoutes(
      { lat: 48, lng: 2 },
      { lat: 49, lng: 3 },
    );
    expect(route.label).toBe("Multimodal");
    expect(route.distance).toBe(451000);
    expect(route.co2Emissions).toBe(1536.5);
    expect(route.steps).toHaveLength(2);
    expect(route.steps[1].geometry?.coordinates).toHaveLength(2);
  });
});
