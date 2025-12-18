"use client";

import { useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import styles from "./calculate.module.css";
import { calculateMultimodalRoutes } from "@/lib/routeService";
import Image from "next/image";

// Helpers pour l'affichage
function capitalize(str: string) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}
function getModeIcon(mode: string) {
  switch (mode) {
    case 'walk': return '🚶';
    case 'car': return '🚗';
    case 'bus': return '🚌';
    case 'train': return '🚆';
    case 'plane': return '✈️';
    case 'bike': return '🚲';
    case 'wait': return '⏳';
    default: return '➡️';
  }
}

// Import dynamique de la carte
const MapComponent = dynamic(() => import("@/components/MapComponent"), { ssr: false });

export interface Suggestion {
  label: string;
  x: number;
  y: number;
  [key: string]: unknown;
}

export interface Step {
  mode: string;
  description: string;
  duration?: number;
  co2?: number;
  geometry?: { coordinates: [number, number][] };
  from?: [number, number];
  to?: [number, number];
  name?: string; //steps voiture
}

interface RouteInfo {
  distance: number;
  duration: number;
  co2Emissions: number;
  geometry: { coordinates: [number, number][] };
  steps?: Step[];
  label?: string; //accès à label
}

export default function CalculatePage() {
  const [departure, setDeparture] = useState<string>("");
  const [destination, setDestination] = useState<string>("");
  const [departureResults, setDepartureResults] = useState<Suggestion[]>([]);
  const [destinationResults, setDestinationResults] = useState<Suggestion[]>([]);
  const [showDepartureSuggestions, setShowDepartureSuggestions] = useState<boolean>(false);
  const [showDestinationSuggestions, setShowDestinationSuggestions] = useState<boolean>(false);
  const [loadingDeparture, setLoadingDeparture] = useState<boolean>(false);
  const [loadingDestination, setLoadingDestination] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedDeparture, setSelectedDeparture] = useState<Suggestion | null>(null);
  const [selectedDestination, setSelectedDestination] = useState<Suggestion | null>(null);
  const [routeSteps, setRouteSteps] = useState<Step[]>([]);
  const [routeInfo, setRouteInfo] = useState<RouteInfo | null>(null);
  const [allRoutes, setAllRoutes] = useState<RouteInfo[]>([]); // stocker itinérarires
  const [bestRouteType, setBestRouteType] = useState<string>("");
  const provider = useRef<unknown>(null);
  const clickedOnSuggestion = useRef<boolean>(false);
  const departureInputRef = useRef<HTMLDivElement | null>(null);
  const destinationInputRef = useRef<HTMLDivElement | null>(null);
  const departureSuggestionsRef = useRef<HTMLUListElement | null>(null);
  const destinationSuggestionsRef = useRef<HTMLUListElement | null>(null);

  // Initialisation du provider OpenStreetMap côté client uniquement
  useEffect(() => {
    let isMounted = true;
    async function loadProvider() {
      if (typeof window !== "undefined") {
        // Suppression de l'import CSS car il n'existe plus dans leaflet-geosearch v4+
        if (isMounted) {
          provider.current = new (await import('leaflet-geosearch')).OpenStreetMapProvider({
            params: {
              'accept-language': 'fr',
              countrycodes: 'fr,be,ch',
            }
          });
        }
      }
    }
    loadProvider();

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const clickedInDepartureInput = departureInputRef.current && departureInputRef.current.contains(target);
      const clickedInDestinationInput = destinationInputRef.current && destinationInputRef.current.contains(target);
      const clickedInDepartureSuggestions = departureSuggestionsRef.current && departureSuggestionsRef.current.contains(target);
      const clickedInDestinationSuggestions = destinationSuggestionsRef.current && destinationSuggestionsRef.current.contains(target);
      if (!clickedInDepartureInput && !clickedInDepartureSuggestions) {
        setShowDepartureSuggestions(false);
      }
      if (!clickedInDestinationInput && !clickedInDestinationSuggestions) {
        setShowDestinationSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      isMounted = false;
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Fonction de recherche dédiée avec gestion d'état de chargement
  const searchDeparture = async () => {
    if (!departure || departure.length < 2 || !provider.current) return;
    try {
      setLoadingDeparture(true);
      setShowDepartureSuggestions(false);
      // Typage explicite du provider et des résultats
      type GeoSearchResult = { label: string; x: number; y: number };
      const searchProvider = provider.current as { search: (params: { query: string }) => Promise<GeoSearchResult[]> };
      const results = await searchProvider.search({ query: departure });
      const limitedResults: Suggestion[] = results.slice(0, 5).map((r) => ({
        label: r.label,
        x: r.x,
        y: r.y
      }));
      setDepartureResults(limitedResults);
      setShowDepartureSuggestions(limitedResults.length > 0);
    } catch (error) {
      console.error("Error searching for locations:", error);
    } finally {
      setLoadingDeparture(false);
    }
  };

  const searchDestination = async () => {
    if (!destination || destination.length < 2 || !provider.current) return;
    try {
      setLoadingDestination(true);
      setShowDestinationSuggestions(false);
      // Typage explicite du provider et des résultats
      type GeoSearchResult = { label: string; x: number; y: number };
      const searchProvider = provider.current as { search: (params: { query: string }) => Promise<GeoSearchResult[]> };
      const results = await searchProvider.search({ query: destination });
      const limitedResults: Suggestion[] = results.slice(0, 5).map((r) => ({
        label: r.label,
        x: r.x,
        y: r.y
      }));
      setDestinationResults(limitedResults);
      setShowDestinationSuggestions(limitedResults.length > 0);
    } catch (error) {
      console.error("Error searching for locations:", error);
    } finally {
      setLoadingDestination(false);
    }
  };

  const handleDepartureChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDeparture(e.target.value);
  };

  const handleDestinationChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDestination(e.target.value);
  };

  const selectSuggestion = (suggestion: Suggestion, isForDeparture: boolean) => {
    clickedOnSuggestion.current = true;
    if (isForDeparture) {
      setDeparture(suggestion.label);
      setSelectedDeparture(suggestion);
      setShowDepartureSuggestions(false);
    } else {
      setDestination(suggestion.label);
      setSelectedDestination(suggestion);
      setShowDestinationSuggestions(false);
    }
  };

  const handleBlur = (isDeparture: boolean) => {
    setTimeout(() => {
      if (!clickedOnSuggestion.current) {
        if (isDeparture) {
          setShowDepartureSuggestions(false);
        } else {
          setShowDestinationSuggestions(false);
        }
      }
      clickedOnSuggestion.current = false;
    }, 200);
  };

  // Calcul itinéraire, émissions de CO2 (uniquement si les deux points sont sélectionnés)
  useEffect(() => {
    const fetchRoute = async () => {
      setRouteInfo(null);
      setRouteSteps([]);
      setAllRoutes([]);
      setBestRouteType("");
      if (!selectedDeparture || !selectedDestination) return;
      try {
        setLoading(true);
        // On utilise les coordonnées du point sélectionné
        const departureCoords = {
          lat: selectedDeparture.y,
          lng: selectedDeparture.x
        };
        const destinationCoords = {
          lat: selectedDestination.y,
          lng: selectedDestination.x
        };
        const routes = await calculateMultimodalRoutes(departureCoords, destinationCoords);
        setAllRoutes(routes);
        // On affiche le plus rapide par défaut
        setRouteInfo(routes[0]);
        setRouteSteps(routes[0]?.steps || []);
        setBestRouteType(routes[0]?.label || "");
      } catch (error) {
        console.error("Une erreur s'est produite lors du calcul de l'itinéraire :", error);
      } finally {
        setLoading(false);
      }
    };
    fetchRoute();
  }, [selectedDeparture, selectedDestination]);

  // Formatage data
  const formatDistance = (meters: number) => {
    return meters < 1000
      ? `${meters} m`
      : `${(meters / 1000).toFixed(1)} km`;
  };

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (hours > 0) {
      return `${hours}h ${minutes}min`;
    } else {
      return `${minutes} min`;
    }
  };

  return (
    <div className={styles.container}>
      {/* Images décoratives */}
      <Image
        src="/images/calculate/deco1.png"
        alt="Decoration 1"
        className={styles.deco1}
        width={500}
        height={300}
      />
      <Image
        src="/images/calculate/deco2.png"
        alt="Decoration 2"
        className={styles.deco2}
        width={500}
        height={300}
      />

      {/* Contenu principal */}
      <h1 className={styles.title}>Calculate Your Carbon Footprint</h1>
      <p className={styles.subtitle}>Compare CO₂ emissions for your trip</p>

      <div className={styles.form}>
        {/* Champ de départ avec bouton de recherche */}
        <div className={styles.inputWithButton}>
          <div className={styles.inputWrapper} ref={departureInputRef}>
            <input
              type="text"
              className={styles.inputField}
              placeholder="Departure"
              value={departure}
              onChange={handleDepartureChange}
              onBlur={() => handleBlur(true)}
            />
            {showDepartureSuggestions && departureResults.length > 0 && (
              <ul className={styles.suggestions} ref={departureSuggestionsRef}>
                {departureResults.map((result, index) => (
                  <li
                    key={index}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      selectSuggestion(result, true);
                    }}
                    className={styles.suggestionItem}
                  >
                    {result.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            className={styles.searchButton}
            onClick={searchDeparture}
            disabled={loadingDeparture}
            title="Rechercher le point de départ"
          >
            {loadingDeparture ? '...' : '🔍'} {/* bouton de recherche */}
          </button>
        </div>

        {/* Champ de destination avec bouton de recherche */}
        <div className={styles.inputWithButton}>
          <div className={styles.inputWrapper} ref={destinationInputRef}>
            <input
              type="text"
              className={styles.inputField}
              placeholder="Destination"
              value={destination}
              onChange={handleDestinationChange}
              onBlur={() => handleBlur(false)}
              autoComplete="off"
            />
            {showDestinationSuggestions && destinationResults.length > 0 && (
              <ul className={styles.suggestions} ref={destinationSuggestionsRef}>
                {destinationResults.map((result, index) => (
                  <li
                    key={index}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      selectSuggestion(result, false);
                    }}
                    className={styles.suggestionItem}
                  >
                    {result.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            className={styles.searchButton}
            onClick={searchDestination}
            disabled={loadingDestination}
            title="Rechercher la destination"
          >
            {loadingDestination ? '...' : '🔍'}
          </button>
        </div>
      </div>

      {routeInfo && (
        <div className={styles.resultsContainer}>
          <h2 className={styles.resultsTitle}>Route Information</h2>

          <div className={styles.resultsGrid}>
            <div className={styles.resultItem}>
              <span className={styles.resultLabel} data-testid="distance-label">Distance:</span>
              <span className={styles.resultValue} data-testid="distance-value">{formatDistance(routeInfo.distance)}</span>
            </div>

            <div className={styles.resultItem}>
              <span className={styles.resultLabel} data-testid="duration-label">Duration:</span>
              <span className={styles.resultValue} data-testid="duration-value">{formatDuration(routeInfo.duration)}</span>
            </div>

            <div className={styles.resultItem}>
              <span className={styles.resultLabel} data-testid="emissions-label">CO₂ Emissions:</span>
              <span className={styles.resultValue} data-testid="emissions-value">
                {routeInfo.co2Emissions} g
              </span>
            </div>
          </div>
        </div>
      )}

      {allRoutes.length > 0 && (
        <div className={styles.resultsContainer}>
          <h2 className={styles.resultsTitle}>Compare transport scenarios</h2>
          <div className={styles.resultsGrid}>
            {allRoutes.filter((route, idx, arr) => {
              // Pour la voiture, n'afficher qu'une seule case "Car only" (pas les steps)
              if (route.label === 'Car only') {
                // On ne garde que la première occurrence
                return arr.findIndex(r => r.label === 'Car only') === idx;
              }
              // Pour les autres, on garde tout
              return true;
            }).map((route, idx) => (
              <div
                key={idx}
                className={
                  styles.resultItem +
                  (route.label === bestRouteType ? ' ' + styles.bestRoute : '')
                }
              >
                <span className={styles.resultLabel}>{route.label}</span>
                <span className={styles.resultValue} data-testid="distance-value">{formatDistance(route.distance)}</span>
                <span className={styles.resultValue} data-testid="duration-value">{formatDuration(route.duration)}</span>
                <span className={styles.resultValue} data-testid="emissions-value">{route.co2Emissions} g CO₂</span>
                {route.label === bestRouteType && (
                  <span className={styles.bestBadge}>Selected mode</span>
                )}
                <button
                  className={styles.showStepsButton}
                  onClick={() => {
                    setRouteInfo(route);
                    setRouteSteps(route.steps || []);
                    setBestRouteType(route.label || "");
                  }}
                >
                  Show steps
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className={styles.mapContainer}>
        <MapComponent
          departure={selectedDeparture ? selectedDeparture.label : ""}
          destination={selectedDestination ? selectedDestination.label : ""}
          routeGeometry={routeInfo?.geometry}
          loading={loading}
          steps={routeSteps}
        />
      </div>
      {/*  timeline, with duration and CO2 for each step */}
      {routeSteps.length > 0 && (
        <div className={styles.stepsContainer}>
          <h3 className={styles.stepsTitle}>Trip steps</h3>
          <ol className={styles.stepsList}>
            {/* Cas spécial pour Car only: une seule ligne récapitulative + déroulable */}
            {routeInfo?.label === 'Car only' ? (
              <li className={styles.stepItem}>
                <details>
                  <summary>
                    <span className={styles.stepMode}>{getModeIcon('car')} Car</span>
                    <span className={styles.stepDesc}>Full car trip</span>
                    <span className={styles.stepDuration}>{formatDuration(routeInfo.duration)}</span>
                    <span className={styles.stepCO2}>{routeInfo.co2Emissions} g CO₂</span>
                  </summary>
                  <ol className={styles.stepsList}>
                    {routeSteps.map((step: Step, idx: number) => (
                      <li key={idx} className={styles.stepItem}>
                        <span className={styles.stepMode}>{getModeIcon('car')}</span>
                        <span className={styles.stepDesc}>{step.description}{step.name ? ` (${step.name})` : ''}</span>
                        {step.duration && (
                          <span className={styles.stepDuration}>{formatDuration(step.duration)}</span>
                        )}
                        {step.co2 !== undefined && (
                          <span className={styles.stepCO2}>{step.co2} g CO₂</span>
                        )}
                      </li>
                    ))}
                  </ol>
                </details>
              </li>
            ) : (
              routeSteps.map((step: Step, idx: number) => (
                <li key={idx} className={styles.stepItem}>
                  <span className={styles.stepMode}>{getModeIcon(step.mode)} {capitalize(step.mode)}</span>
                  <span className={styles.stepDesc}>{step.description}</span>
                  {step.duration && (
                    <span className={styles.stepDuration}>{formatDuration(step.duration)}</span>
                  )}
                  {step.co2 !== undefined && (
                    <span className={styles.stepCO2}>{step.co2} g CO₂</span>
                  )}
                </li>
              ))
            )}
          </ol>
        </div>
      )}
    </div>
  );
}