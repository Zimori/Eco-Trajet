import { render, screen } from '@testing-library/react';
import MapComponent from '../MapComponent';
import '@testing-library/jest-dom';

// Mock react-leaflet components
jest.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  Polyline: () => <div data-testid="polyline" />,
  Marker: ({ position, title }: { position: [number, number]; title: string }) => (
    <div data-testid="marker" title={title}>
      {position.toString()}
    </div>
  ),
  useMap: () => ({
    setView: jest.fn(),
    fitBounds: jest.fn(),
  }),
}));

jest.mock('@/lib/routeService', () => ({
  geocodeLocation: jest.fn((location: string) => {
    if (location === 'Paris') {
      return Promise.resolve({ lat: 48.8566, lng: 2.3522 });
    }
    if (location === 'Lyon') {
      return Promise.resolve({ lat: 45.764, lng: 4.8357 });
    }
    return Promise.reject('Location not found');
  }),
}));


describe('MapComponent', () => {
  test('renders the map and markers', async () => {
    const departure = 'Paris';
    const destination = 'Lyon';
    const routeGeometry = {
      coordinates: [
        [2.3522, 48.8566] as [number, number], // Paris
        [4.8357, 45.764] as [number, number],  // Lyon
      ]
    };
  
    render(
      <MapComponent
        departure={departure}
        destination={destination}
        routeGeometry={routeGeometry}
        loading={false}
      />
    );
  
    // Vérifie si la carte est rendue
    expect(screen.getByTestId('map-container')).toBeInTheDocument();
  
    // Attendre que les marqueurs soient rendus
    const markers = await screen.findAllByTestId('marker');
    expect(markers).toHaveLength(2); // Deux marqueurs : départ et destination
    expect(markers[0]).toHaveAttribute('title', 'Départ');
    expect(markers[1]).toHaveAttribute('title', 'Destination');
  });
});