import { fetchMultimodalRoute, geocodeLocation } from "./routeService";

const backendResponse = {
  segments: [
    {
      mode: "car",
      distance_m: 1000,
      duration_s: 120,
      co2_grams: 218,
      geometry: { type: "LineString", coordinates: [[2, 48], [2.01, 48.01]] },
    },
  ],
  totals: { distance_totale: 1000, temps_total: 120, co2_total: 218 },
  metadata: {
    timestamp: "2026-10-27T00:00:00Z",
    matching_reliability_score: 0.99,
    ademe_database_version: "2026.1",
  },
};

function response(body: unknown, status: number) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("fetchMultimodalRoute", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("posts typed coordinates to the FastAPI contract", async () => {
    jest.mocked(fetch).mockResolvedValue(
      response(backendResponse, 200),
    );

    await expect(
      fetchMultimodalRoute({ lat: 48, lng: 2 }, { lat: 49, lng: 3 }),
    ).resolves.toEqual(backendResponse);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/routing/multimodal"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          origin: { lat: 48, lon: 2 },
          destination: { lat: 49, lon: 3 },
        }),
      }),
    );
  });

  it("reports backend errors", async () => {
    jest.mocked(fetch).mockResolvedValue(
      response({ detail: "No station found" }, 502),
    );
    await expect(
      fetchMultimodalRoute({ lat: 48, lng: 2 }, { lat: 49, lng: 3 }),
    ).rejects.toThrow("No station found");
  });
});

describe("geocodeLocation", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("parses a Nominatim result", async () => {
    jest.mocked(fetch).mockResolvedValue(
      response([{ lat: "45.75", lon: "4.85" }], 200),
    );
    await expect(geocodeLocation("Lyon")).resolves.toEqual({ lat: 45.75, lng: 4.85 });
  });

  it("rejects an empty result", async () => {
    jest.mocked(fetch).mockResolvedValue(response([], 200));
    await expect(geocodeLocation("NowhereLand")).rejects.toThrow("Aucun résultat");
  });
});
