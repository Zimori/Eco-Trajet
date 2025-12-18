/**
 * Service pour le calcul d'itinéraire et d'émissions de CO2
 */

import axios from 'axios';


export async function calculateRoute(departureCoords, destinationCoords, mode) {
  // Convertir mode transport pr OSRM 
  const profile = convertTransportMode(mode);
  
  try {
    // API OSRM 
    const url = `https://router.project-osrm.org/route/v1/${profile}/` +
      `${departureCoords.lng},${departureCoords.lat};` +
      `${destinationCoords.lng},${destinationCoords.lat}` +
      `?overview=full&geometries=geojson&steps=true`;
    
    const response = await axios.get(url);
    
    if (response.data.code !== 'Ok' || !response.data.routes || response.data.routes.length === 0) {
      throw new Error('Aucun itinéraire trouvé');
    }
    
    const route = response.data.routes[0];
    // Calcul des émissions de CO2 pour cet itinéraire
    const co2Emissions = calculateCO2Emissions(route.distance, mode);
    return {
      distance: route.distance, // en mètres
      duration: route.duration, // en secondes
      geometry: route.geometry, // format GeoJSON pour l'affichage sur la carte
      co2Emissions, // en gCO2
      steps: (route.legs && route.legs[0] && route.legs[0].steps) ? route.legs[0].steps : [] // étapes trajet
    };
    
  } catch (error) {
    console.error("Erreur lors du calcul de l'itinéraire:", error);
    throw error;
  }
}

/**
 * Convertit le mode de transport de notre application au format compris par l'API OSRMxx
 */
function convertTransportMode(mode) {
  switch (mode.toLowerCase()) {
    case 'car':
      return 'car';
    case 'bike':
    case 'bicycle':
      return 'bike';
    case 'walk':
    case 'foot':
      return 'foot';
    case 'bus':
    case 'train':
      // Nativement, transports en commun existent pas pour OSRM
      // on approxime avec 'car'
      return 'car';
    default:
      return 'car';
  }
}

export function calculateCO2Emissions(distanceMeters, mode) {
  // Convertir la distance en kilomètres
  const distanceKm = distanceMeters / 1000;
  const m = mode.toLowerCase();
  if (m.includes('walk') || m.includes('foot') || m.includes('bike') || m.includes('bicycle')) {
    return 0;
  }
  // en g CO2/km (ADEME)
  const emissionFactors = {
    car: 193,
    bus: 113, // (bus thermique)
    train: 8.9, // (TGV)
    plane: 285
  };
  const emissionFactor = emissionFactors[m] || emissionFactors.car;
  // calcul émissions totales (g CO2)
  return Math.round(distanceKm * emissionFactor);
}


export async function geocodeLocation(locationName) {
  try {
    const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(locationName)}`;
    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'EcoTrajet-App/1.0'  // Nominatim exige un User-Agent
      }
    });
    
    if (!response.data || response.data.length === 0) {
      throw new Error(`Aucun résultat trouvé pour "${locationName}"`);
    }
    
    // Utiliser le premier résultat
    const location = response.data[0];
    return {
      lat: parseFloat(location.lat),
      lng: parseFloat(location.lon)
    };
  } catch (error) {
    console.error('Erreur lors du géocodage:', error);
    throw error;
  }
}

/**
 * Calcule des itinéraires multimodaux simulés (marche, voiture, train, avion, bus)
 * Retourne trois options : plus rapide, moins polluante, compromis
 * @param {Object} departureCoords - {lat, lng}
 * @param {Object} destinationCoords - {lat, lng}
 * @returns {Promise<Array>} Liste d'itinéraires multimodaux
 */
export async function calculateMultimodalRoutes(departureCoords, destinationCoords) {
  // Hypothèses :
  // - On simule 3 scénarios : tout voiture, tout train, mix bus+avion+bus
  // - On utilise OSRM pour voiture et marche, on simule train/avion
  // - On retourne : fastest, lowestCO2, compromise

  // Pour la simulation, on définit des points intermédiaires fictifs pour la gare et l'aéroport
  // On prend un point à 1% du trajet pour la gare/aéroport de départ, et à 99% pour l'arrivée
  function interpolate(from, to, ratio) {
    return [
      from.lat + (to.lat - from.lat) * ratio,
      from.lng + (to.lng - from.lng) * ratio
    ];
  }
  const trainStationStart = interpolate(departureCoords, destinationCoords, 0.01);
  const trainStationEnd = interpolate(departureCoords, destinationCoords, 0.99);
  const airportStart = interpolate(departureCoords, destinationCoords, 0.02);
  const airportEnd = interpolate(departureCoords, destinationCoords, 0.98);

  // Helper pour obtenir la géométrie réelle entre deux points (mode car/bus/bike/walk)
  async function getStepGeometryAndDistance(from, to, mode) {
    if (!from || !to) return { geometry: null, distance: null };
    // Avion et train utilisent toujours Haversine
    if (mode === 'plane' || mode === 'train') {
      return { geometry: null, distance: getHaversineDistance({ lat: from[0], lng: from[1] }, { lat: to[0], lng: to[1] }) * 1000 };
    }
    // OSRM pour car, bus, bike, walk
    let osrmMode = 'car';
    if (mode === 'walk' || mode === 'foot') osrmMode = 'foot';
    else if (mode === 'bike' || mode === 'bicycle') osrmMode = 'bike';
    try {
      const url = `https://router.project-osrm.org/route/v1/${osrmMode}/` +
        `${from[1]},${from[0]};${to[1]},${to[0]}?overview=full&geometries=geojson`;
      const response = await axios.get(url);
      if (response.data.code === 'Ok' && response.data.routes && response.data.routes[0]) {
        return {
          geometry: response.data.routes[0].geometry,
          distance: response.data.routes[0].distance
        };
      }
    } catch {
      // ignore erreur, fallback Haversine
    }
    return { geometry: null, distance: getHaversineDistance({ lat: from[0], lng: from[1] }, { lat: to[0], lng: to[1] }) * 1000 };
  }

  // 1. Tout voiture (OSRM)
  const carRoute = await calculateRoute(departureCoords, destinationCoords, 'car');
  let carTotalDuration = 0;
  let carTotalCO2 = 0;
  let carTotalDistance = 0;
  if (carRoute.steps && Array.isArray(carRoute.steps)) {
    carRoute.steps.forEach(step => {
      carTotalDuration += step.duration || 0;
      carTotalCO2 += calculateCO2Emissions(step.distance || 0, 'car');
      carTotalDistance += step.distance || 0;
    });
  }
  const carRouteObj = {
    ...carRoute,
    label: 'Car only',
    scenario: 'car',
    modes: ['car'],
    duration: carTotalDuration || carRoute.duration,
    co2Emissions: carTotalCO2 || carRoute.co2Emissions,
    distance: carTotalDistance || carRoute.distance,
    steps: carRoute.steps ? JSON.parse(JSON.stringify(carRoute.steps)) : []
  };

  // 2. Tout train (toujours Haversine)
  const distanceTrain = getHaversineDistance(departureCoords, destinationCoords);
  const durationTrain = (distanceTrain / 200) * 3600;
  const co2Train = calculateCO2Emissions(distanceTrain * 1000, 'train');
  const trainSteps = [
    {
      mode: 'walk',
      description: 'Walk to the train station',
      duration: 900,
      co2: calculateCO2Emissions(1*1000, 'walk'),
      from: [departureCoords.lat, departureCoords.lng],
      to: trainStationStart
    },
    {
      mode: 'train',
      description: `Train ride (${distanceTrain.toFixed(1)} km)`,
      duration: durationTrain,
      co2: co2Train,
      from: trainStationStart,
      to: trainStationEnd
    },
    {
      mode: 'walk',
      description: 'Walk from the train station to your destination',
      duration: 900,
      co2: calculateCO2Emissions(1*1000, 'walk'),
      from: trainStationEnd,
      to: [destinationCoords.lat, destinationCoords.lng]
    }
  ];
  for (let s of trainSteps) {
    if (s.mode === 'train') {
      const { geometry, distance } = await getStepGeometryAndDistance(s.from, s.to, 'train');
      s.geometry = geometry;
      s.distance = distance;
    } else {
      const { geometry, distance } = await getStepGeometryAndDistance(s.from, s.to, s.mode);
      s.geometry = geometry;
      s.distance = distance;
    }
  }
  const trainRouteObj = {
    label: 'Train only',
    scenario: 'train',
    modes: ['walk', 'train', 'walk'],
    distance: distanceTrain * 1000,
    duration: durationTrain + 2*900,
    geometry: null,
    co2Emissions: co2Train,
    steps: JSON.parse(JSON.stringify(trainSteps))
  };

  // 3. Tout bus (OSRM si possible, sinon Haversine)
  const { geometry: busGeometry, distance: busDistance } = await getStepGeometryAndDistance(
    [departureCoords.lat, departureCoords.lng],
    [destinationCoords.lat, destinationCoords.lng],
    'bus'
  );
  const usedBusDistance = busDistance || distanceTrain * 1000;
  const durationBus = (usedBusDistance / 60000) * 3600; // 60km/h
  const co2Bus = calculateCO2Emissions(usedBusDistance, 'bus');
  const busSteps = [
    {
      mode: 'bus',
      description: `Bus ride (${(usedBusDistance/1000).toFixed(1)} km)`,
      duration: durationBus,
      co2: co2Bus,
      from: [departureCoords.lat, departureCoords.lng],
      to: [destinationCoords.lat, destinationCoords.lng],
      geometry: busGeometry,
      distance: usedBusDistance
    }
  ];
  const busRouteObj = {
    label: 'Bus only',
    scenario: 'bus',
    modes: ['bus'],
    distance: usedBusDistance,
    duration: durationBus,
    geometry: null,
    co2Emissions: co2Bus,
    steps: JSON.parse(JSON.stringify(busSteps))
  };

  // 4. Tout vélo (OSRM si possible, sinon Haversine)
  const { geometry: bikeGeometry, distance: bikeDistance } = await getStepGeometryAndDistance(
    [departureCoords.lat, departureCoords.lng],
    [destinationCoords.lat, destinationCoords.lng],
    'bike'
  );
  const usedBikeDistance = bikeDistance || distanceTrain * 1000;
  const durationBike = (usedBikeDistance / 20000) * 3600; // 20km/h
  const co2Bike = calculateCO2Emissions(usedBikeDistance, 'bike');
  const bikeSteps = [
    {
      mode: 'bike',
      description: `Bike ride (${(usedBikeDistance/1000).toFixed(1)} km)`,
      duration: durationBike,
      co2: co2Bike,
      from: [departureCoords.lat, departureCoords.lng],
      to: [destinationCoords.lat, destinationCoords.lng],
      geometry: bikeGeometry,
      distance: usedBikeDistance
    }
  ];
  const bikeRouteObj = {
    label: 'Bike only',
    scenario: 'bike',
    modes: ['bike'],
    distance: usedBikeDistance,
    duration: durationBike,
    geometry: null,
    co2Emissions: co2Bike,
    steps: JSON.parse(JSON.stringify(bikeSteps))
  };

  // 5. Tout à pied (OSRM si possible, sinon Haversine)
  const { geometry: walkGeometry, distance: walkDistance } = await getStepGeometryAndDistance(
    [departureCoords.lat, departureCoords.lng],
    [destinationCoords.lat, destinationCoords.lng],
    'walk'
  );
  const usedWalkDistance = walkDistance || distanceTrain * 1000;
  const durationWalk = (usedWalkDistance / 5000) * 3600; // 5km/h
  const co2Walk = calculateCO2Emissions(usedWalkDistance, 'walk');
  const walkSteps = [
    {
      mode: 'walk',
      description: `Walk (${(usedWalkDistance/1000).toFixed(1)} km)`,
      duration: durationWalk,
      co2: co2Walk,
      from: [departureCoords.lat, departureCoords.lng],
      to: [destinationCoords.lat, destinationCoords.lng],
      geometry: walkGeometry,
      distance: usedWalkDistance
    }
  ];
  const walkRouteObj = {
    label: 'Walk only',
    scenario: 'walk',
    modes: ['walk'],
    distance: usedWalkDistance,
    duration: durationWalk,
    geometry: null,
    co2Emissions: co2Walk,
    steps: JSON.parse(JSON.stringify(walkSteps))
  };

  // 6. Bus + Avion + Bus (bus = OSRM si possible, avion = Haversine)
  // Bus départ
  const { geometry: bus1Geometry, distance: bus1Distance } = await getStepGeometryAndDistance(
    [departureCoords.lat, departureCoords.lng],
    airportStart,
    'bus'
  );
  const usedBus1Distance = bus1Distance || getHaversineDistance({ lat: departureCoords.lat, lng: departureCoords.lng }, { lat: airportStart[0], lng: airportStart[1] }) * 1000;
  // Avion (toujours Haversine)
  const distanceAvion = getHaversineDistance({ lat: airportStart[0], lng: airportStart[1] }, { lat: airportEnd[0], lng: airportEnd[1] });
  const durationAvion = (distanceAvion / 700) * 3600;
  const co2Avion = calculateCO2Emissions(distanceAvion * 1000, 'plane');
  // Bus arrivée
  const { geometry: bus2Geometry, distance: bus2Distance } = await getStepGeometryAndDistance(
    airportEnd,
    [destinationCoords.lat, destinationCoords.lng],
    'bus'
  );
  const usedBus2Distance = bus2Distance || getHaversineDistance({ lat: airportEnd[0], lng: airportEnd[1] }, { lat: destinationCoords.lat, lng: destinationCoords.lng }) * 1000;
  const co2BusAvion1 = calculateCO2Emissions(usedBus1Distance, 'bus');
  const co2BusAvion2 = calculateCO2Emissions(usedBus2Distance, 'bus');
  const busAvionSteps = [
    {
      mode: 'bus',
      description: 'Bus to the airport',
      duration: 1800,
      co2: co2BusAvion1,
      from: [departureCoords.lat, departureCoords.lng],
      to: airportStart,
      geometry: bus1Geometry,
      distance: usedBus1Distance
    },
    {
      mode: 'wait',
      description: 'Waiting at the airport',
      duration: 1800,
      co2: 0
    },
    {
      mode: 'plane',
      description: `Flight (${distanceAvion.toFixed(1)} km)`,
      duration: durationAvion,
      co2: co2Avion,
      from: airportStart,
      to: airportEnd,
      geometry: null,
      distance: distanceAvion * 1000
    },
    {
      mode: 'wait',
      description: 'Waiting at arrival airport',
      duration: 1800,
      co2: 0
    },
    {
      mode: 'bus',
      description: 'Bus from the airport to your destination',
      duration: 1800,
      co2: co2BusAvion2,
      from: airportEnd,
      to: [destinationCoords.lat, destinationCoords.lng],
      geometry: bus2Geometry,
      distance: usedBus2Distance
    }
  ];
  const busAvionRouteObj = {
    label: 'Bus + Plane + Bus',
    scenario: 'bus+plane+bus',
    modes: ['bus', 'plane', 'bus'],
    distance: usedBus1Distance + distanceAvion * 1000 + usedBus2Distance,
    duration: 1800 + durationAvion + 1800 + 2*1800,
    geometry: null,
    co2Emissions: co2Avion + co2BusAvion1 + co2BusAvion2,
    steps: JSON.parse(JSON.stringify(busAvionSteps))
  };

  // Sélection des options
  const allRoutes = [carRouteObj, trainRouteObj, busRouteObj, bikeRouteObj, walkRouteObj, busAvionRouteObj];
  const fastest = allRoutes.reduce((a, b) => a.duration < b.duration ? a : b);
  const lowestCO2 = allRoutes.reduce((a, b) => a.co2Emissions < b.co2Emissions ? a : b);
  const maxTime = Math.max(...allRoutes.map(r => r.duration));
  const maxCO2 = Math.max(...allRoutes.map(r => r.co2Emissions));
  const compromise = allRoutes.reduce((best, route) => {
    const score = (route.duration / maxTime) + (route.co2Emissions / maxCO2);
    if (!best || score < best.score) return { ...route, score };
    return best;
  }, null);
  const seen = new Set();
  const uniqueRoutes = [];
  for (const route of [fastest, lowestCO2, compromise, ...allRoutes]) {
    const key = `${route.label}|${route.distance}|${route.duration}|${route.co2Emissions}`;
    if (!seen.has(key)) {
      seen.add(key);
      uniqueRoutes.push(route);
    }
  }
  return uniqueRoutes;
}

// Haversine distance en km 
// Haversine en bref c'est une formule pour calculer la distance entre deux points sur la surface d'une sphère
// en utilisant leurs latitudes et longitudes
// https://fr.wikipedia.org/wiki/Formule_de_Haversine
function getHaversineDistance(coord1, coord2) {
  const R = 6371; // km
  const dLat = (coord2.lat - coord1.lat) * Math.PI / 180;
  const dLon = (coord2.lng - coord1.lng) * Math.PI / 180;
  const lat1 = coord1.lat * Math.PI / 180;
  const lat2 = coord2.lat * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.sin(dLon/2) * Math.sin(dLon/2) * Math.cos(lat1) * Math.cos(lat2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}