jest.mock('axios');
import axios from 'axios';
import { calculateMultimodalRoutes } from './routeService';

jest.mock('./routeService', () => {
  const actual = jest.requireActual('./routeService');
  return {
    ...actual,
    calculateRoute: jest.fn()
  };
});

describe('calculateMultimodalRoutes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns multiple route options with expected structure', async () => {
    const mockCarRoute = {
      distance: 10000,
      duration: 1200,
      geometry: { type: 'LineString', coordinates: [] },
      co2Emissions: 1930,
      steps: [
        { distance: 1000, duration: 120 },
        { distance: 9000, duration: 1080 }
      ]
    };
    jest.mocked(jest.requireMock('./routeService').calculateRoute).mockResolvedValue(mockCarRoute);
    axios.get.mockResolvedValue({
      data: {
        code: 'Ok',
        routes: [{ geometry: { type: 'LineString', coordinates: [] }, distance: 10000 }]
      }
    });
    const departure = { lat: 45.75, lng: 4.85 };
    const destination = { lat: 45.76, lng: 4.86 };
    const routes = await calculateMultimodalRoutes(departure, destination);
    expect(Array.isArray(routes)).toBe(true);
    expect(routes.length).toBeGreaterThanOrEqual(3);
    for (const route of routes) {
      expect(route).toHaveProperty('label');
      expect(route).toHaveProperty('distance');
      expect(route).toHaveProperty('duration');
      expect(route).toHaveProperty('co2Emissions');
      expect(route).toHaveProperty('steps');
      expect(Array.isArray(route.steps)).toBe(true);
    }
  });

  it('handles edge case: identical departure and destination', async () => {
    jest.mocked(jest.requireMock('./routeService').calculateRoute).mockResolvedValue({
      distance: 0,
      duration: 0,
      geometry: { type: 'LineString', coordinates: [] },
      co2Emissions: 0,
      steps: []
    });
    axios.get.mockResolvedValue({
      data: {
        code: 'Ok',
        routes: [{ geometry: { type: 'LineString', coordinates: [] }, distance: 0 }]
      }
    });
    const coord = { lat: 45.75, lng: 4.85 };
    const routes = await calculateMultimodalRoutes(coord, coord);
    expect(routes.every(r => r.distance === 0)).toBe(true);
  });
});
