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

describe('MapComponent', () => {
  test('renders the map and markers', () => {
    const departure = { x: 2.3522, y: 48.8566 }; // Paris
    const destination = { x: 4.8357, y: 45.764 }; // Lyon
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
  
    // The map renders
    expect(screen.getByTestId('map-container')).toBeInTheDocument();
  
    const markers = screen.getAllByTestId('marker');
    expect(markers).toHaveLength(2); // departure and destination
    expect(markers[0]).toHaveAttribute('title', 'Départ');
    expect(markers[1]).toHaveAttribute('title', 'Destination');
    // markers sit on the picked coordinates, as [lat, lng]
    expect(markers[0]).toHaveTextContent('48.8566,2.3522');
    expect(markers[1]).toHaveTextContent('45.764,4.8357');
  });

  test('places only the picked points', () => {
    render(<MapComponent departure={null} destination={{ x: 4.8357, y: 45.764 }} />);
    const markers = screen.getAllByTestId('marker');
    expect(markers).toHaveLength(1);
    expect(markers[0]).toHaveAttribute('title', 'Destination');
  });
});
