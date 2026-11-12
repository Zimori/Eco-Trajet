🇬🇧 **English** | 🇫🇷 [**Français**](./README.md)

# EcoTrajet - Carbon Footprint Calculator for Travel Routes

## Description

EcoTrajet is a web application that allows users to calculate and compare the carbon footprint of their travels depending on the transport mode chosen. The application offers an intuitive interface with address autocomplete, route calculation, and cartographic visualization.

## Technologies Used

### Frontend
- **Next.js** : React framework for server-side rendering and routing
- **React** : JavaScript library for building user interfaces
- **TypeScript** : Superset of JavaScript adding static typing
- **CSS Modules** : For styling with style isolation

### Cartography
- **Leaflet** : Open-source JavaScript library for interactive maps
- **React Leaflet** : React components for Leaflet
- **Leaflet-GeoSearch** : Component for address autocomplete in Leaflet

### External APIs
- **OpenStreetMap** : Provides base cartographic data
- **Nominatim** : Geocoding service to convert addresses into geographic coordinates
- **OSRM** (Open Source Routing Machine) : API for calculating routes between two points

## Main Dependencies

```json
{
  "dependencies": {
    "axios": "^x.x.x",               // HTTP client for API requests
    "leaflet": "^1.x.x",             // Cartography library
    "leaflet-geosearch": "^3.x.x",   // Address autocomplete
    "next": "^14.x.x",               // Next.js framework
    "react": "^18.x.x",              // React library
    "react-dom": "^18.x.x",          // React rendering in the DOM
    "react-leaflet": "^4.x.x"        // React components for Leaflet
  }
}
```

## Application Structure

- `/src/app` : Application pages and components
  - `/calculate` : Page for calculating route and carbon footprint
- `/src/components` : Reusable components
  - `MapComponent.tsx` : Map component for displaying routes
  - `Header.tsx` : Application header
- `/src/lib` : Services and utilities
  - `routeService.js` : Service for calculating routes and CO2 emissions
  - `db.js` : Service for database connection
- `/public` : Static resources, images

## APIs Used

### 1. Nominatim API
- **Provider** : OpenStreetMap
- **Usage** : Converts place names to geographic coordinates (latitude/longitude)
- **Endpoint** : `https://nominatim.openstreetmap.org/search`
- **Limits** : Max 1 request per second, requires a custom User-Agent

### 2. OSRM API
- **Provider** : Project OSRM
- **Usage** : Calculates routes between two points with distance and duration
- **Endpoint** : `https://router.project-osrm.org/route/v1/{profile}/{coordinates}`
- **Supported Formats** : GeoJSON formats for route geometry

## CO2 Emission Calculation

Factors come from the official [ADEME Base Carbone](https://data.ademe.fr/datasets/base-carboner) (V23.6), in gCO2e per passenger.km. `backend/scripts/seed_data.py` downloads the export and extracts these elements (`ADEME_FACTORS`):

| Mode | Base Carbone element | gCO2e/passenger.km |
|---|---|---|
| Train, TGV (2022) | 43256 | 2.93 |
| Train, Intercités (2022) | 43272 | 7.5 |
| Train, TER (2022) | 43255 | 27.7 |
| Car, average, mixed use (2023) | 43809 | 160 |

## Installation and Getting Started

1. **Clone the repository** :
   ```bash
   git clone <repository-url>
   cd eco-trajet
   ```

2. **Install dependencies** :
   ```bash
   npm install
   ```

3. **Launch the development server** :
   ```bash
   npm run dev
   ```

4. **Build for production** :
   ```bash
   npm run build
   npm start
   ```

## Features

- Autocomplete for departure and arrival addresses
- Route calculation between two points
- Display of distance and travel duration
- CO2 emission calculation according to transport mode
- Route visualization on an interactive map
- Responsive and intuitive interface

## Limitations

- Emission factors are averages and do not account for variables such as vehicle model or occupancy rate
- The route for buses and trains uses the same calculation as for cars (OSRM API limitation)
- Data accuracy depends on the quality of OpenStreetMap data

## Testing

Run the test suite:
```bash
npm test
```

## Build Status

The application builds successfully with no ESLint or TypeScript errors.

## Contributors

- Team MIF10-G04-2024

