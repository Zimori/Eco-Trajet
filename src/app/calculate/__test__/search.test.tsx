/**
 * @jest-environment jsdom
 */
// Renders the real calculate page (calculate.test.tsx only tests a mocked copy).
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import CalculatePage from '../page';
import { calculateMultimodalRoutes } from '@/lib/routeService';

jest.mock('next/dynamic', () => () => function MapStub() { return <div data-testid="map-component" />; });

const search = jest.fn();
jest.mock('leaflet-geosearch', () => ({
  OpenStreetMapProvider: jest.fn().mockImplementation(() => ({ search })),
}));

jest.mock('@/lib/routeService', () => ({
  calculateMultimodalRoutes: jest.fn(),
}));

const route = {
  distance: 10000, duration: 3600, co2Emissions: 500, label: 'Multimodal',
  geometry: { type: 'LineString', coordinates: [] }, steps: [],
};

async function pick(placeholder: string, text: string, label: string) {
  search.mockResolvedValueOnce([{ label, x: 2, y: 48 }]);
  const input = screen.getByPlaceholderText(placeholder);
  fireEvent.change(input, { target: { value: text } });
  fireEvent.submit(input); // what pressing Enter does in a form
  fireEvent.mouseDown(await screen.findByText(label));
}

beforeEach(() => {
  search.mockReset();
  (calculateMultimodalRoutes as jest.Mock).mockResolvedValue([route]);
});

test('Enter in an address field searches', async () => {
  render(<CalculatePage />);
  await waitFor(() => expect(jest.requireMock('leaflet-geosearch').OpenStreetMapProvider).toHaveBeenCalled());
  search.mockResolvedValueOnce([{ label: 'Paris, France', x: 2.35, y: 48.85 }]);
  const input = screen.getByPlaceholderText('Departure');
  fireEvent.change(input, { target: { value: 'Paris' } });
  fireEvent.submit(input);
  expect(await screen.findByText('Paris, France')).toBeInTheDocument();
  expect(search).toHaveBeenCalledWith({ query: 'Paris' });
});

test('editing an address clears the previous route', async () => {
  render(<CalculatePage />);
  await waitFor(() => expect(jest.requireMock('leaflet-geosearch').OpenStreetMapProvider).toHaveBeenCalled());
  await pick('Departure', 'Paris', 'Paris, France');
  await pick('Destination', 'Lyon', 'Lyon, France');
  expect(await screen.findByText('Route Information')).toBeInTheDocument();

  fireEvent.change(screen.getByPlaceholderText('Departure'), { target: { value: 'Marseille' } });
  await waitFor(() => expect(screen.queryByText('Route Information')).not.toBeInTheDocument());
});
