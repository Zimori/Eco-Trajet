import { calculateCO2Emissions, calculateRoute, geocodeLocation } from './routeService';

// Mock axios to avoid real HTTP requests
jest.mock('axios');
import axios from 'axios';

describe('calculateCO2Emissions', () => {
  it('returns 0 for walk/foot/bike/bicycle (any case/variant)', () => {
    expect(calculateCO2Emissions(1000, 'walk')).toBe(0);
    expect(calculateCO2Emissions(1000, 'foot')).toBe(0);
    expect(calculateCO2Emissions(1000, 'bike')).toBe(0);
    expect(calculateCO2Emissions(1000, 'bicycle')).toBe(0);
    expect(calculateCO2Emissions(1000, 'WALK')).toBe(0);
    expect(calculateCO2Emissions(1000, 'Foot')).toBe(0);
    expect(calculateCO2Emissions(1000, 'BICYCLE')).toBe(0);
    expect(calculateCO2Emissions(1000, 'eBike')).toBe(0); //  'bike' aussi
    expect(calculateCO2Emissions(1000, 'walking')).toBe(0); //  'walk' aussi
  });

  it('returns correct emissions for car, bus, train, plane', () => {
    expect(calculateCO2Emissions(10000, 'car')).toBe(1930); // 10km * 193
    expect(calculateCO2Emissions(10000, 'bus')).toBe(1130); // 10km * 113
    expect(calculateCO2Emissions(10000, 'train')).toBe(89); // 10km * 8.9
    expect(calculateCO2Emissions(10000, 'plane')).toBe(2850); // 10km * 285
  });

  it('defaults to car emissions for unknown mode', () => {
    expect(calculateCO2Emissions(10000, 'unknown')).toBe(1930);
  });
});

describe('calculateRoute', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns route data and calculates CO2', async () => {
    axios.get.mockResolvedValue({
      data: {
        code: 'Ok',
        routes: [{
          distance: 10000,
          duration: 1200,
          geometry: { type: 'LineString', coordinates: [] },
          legs: [{ steps: [{ distance: 1000, duration: 120 }] }]
        }]
      }
    });
    const result = await calculateRoute({ lat: 0, lng: 0 }, { lat: 1, lng: 1 }, 'car');
    expect(result.distance).toBe(10000);
    expect(result.duration).toBe(1200);
    expect(result.co2Emissions).toBe(1930);
    expect(result.geometry).toBeDefined();
    expect(Array.isArray(result.steps)).toBe(true);
  });

  it('throws if no route found', async () => {
    axios.get.mockResolvedValue({ data: { code: 'NoRoute', routes: [] } });
    await expect(calculateRoute({ lat: 0, lng: 0 }, { lat: 1, lng: 1 }, 'car')).rejects.toThrow('Aucun itinéraire trouvé');
  });
});

describe('geocodeLocation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns coordinates for a valid location', async () => {
    axios.get.mockResolvedValue({ data: [{ lat: '45.75', lon: '4.85' }] });
    const result = await geocodeLocation('Lyon');
    expect(result).toEqual({ lat: 45.75, lng: 4.85 });
  });

  it('throws if no result found', async () => {
    axios.get.mockResolvedValue({ data: [] });
    await expect(geocodeLocation('NowhereLand')).rejects.toThrow('Aucun résultat trouvé');
  });
});
