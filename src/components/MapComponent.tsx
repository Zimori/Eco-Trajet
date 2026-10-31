"use client";

import { Fragment, useEffect, useState, useMemo } from "react";
import { MapContainer, TileLayer, Polyline, Marker, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import styles from "./MapComponent.module.css";
import L from "leaflet";
import { geocodeLocation } from "@/lib/routeService";

// URLs par défaut
delete (L.Icon.Default.prototype as { _getIconUrl?: () => string })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png",
});

function SetMapView({ bounds, center, zoom }: { bounds?: L.LatLngBounds | null; center?: [number, number] | null; zoom?: number }) {
  const map = useMap();

  // vue carte en fct des props (bounds ou center)
  useEffect(() => {
    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds);
    } else if (center) {
      map.setView(center, zoom || 6);
    }
  }, [bounds, center, map, zoom]);

  return null;
}

interface Step {
  mode: string;
  description: string;
  duration?: number;
  geometry?: { coordinates: [number, number][] };
  from?: [number, number];
  to?: [number, number];
}

interface Segment {
  polyline: [number, number][];
  color: string;
  isSimulated: boolean;
  mode: string;
  description: string;
}

interface MapComponentProps {
  departure: string;
  destination: string;
  routeGeometry?: { coordinates: [number, number][] };
  loading?: boolean;
  steps?: Step[];
}

function toLeafletPositions(
  geometry?: { coordinates?: unknown },
): [number, number][] {
  const rawCoords = geometry?.coordinates;
  return Array.isArray(rawCoords)
    ? rawCoords
        .filter(
          (coordinate): coordinate is [number, number] =>
            Array.isArray(coordinate) &&
            coordinate.length >= 2 &&
            Number.isFinite(coordinate[0]) &&
            Number.isFinite(coordinate[1]),
        )
        .map(([lon, lat]) => [lat, lon])
    : [];
}

function getModeColor(mode: string): string {
  switch (mode) {
    case 'train': return '#7c3aed';
    case 'flight': return '#94a3b8';
    case 'car':
    case 'carpool':
    case 'bus':
    case 'default':
      return '#2563eb';
    case 'walk':
    case 'bike':
      return '#2563eb';
    default: return '#2563eb';
  }
}

export default function MapComponent({
  departure,
  destination,
  routeGeometry,
  loading = false,
  steps = []
}: MapComponentProps) {
  const [markers, setMarkers] = useState<[number, number][]>([]);
  const [mapBounds, setMapBounds] = useState<L.LatLngBounds | null>(null);

  // Construction des segments colorés pour chaque étape
  const segments: Segment[] = useMemo(() => {
    const segs: Segment[] = [];
    let lastPoint: [number, number] | null = null;
    if (steps && steps.length > 0) {
      for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        const color = getModeColor(step.mode);
        let polyline: [number, number][] | null = null;
        const stepPositions = toLeafletPositions(step.geometry);
        if (stepPositions.length >= 2) {
          polyline = stepPositions;
        } else if (step.from && step.to) {
          polyline = [step.from, step.to];
        } else if (step.from && !step.to && steps[i + 1] && steps[i + 1].to) {
          polyline = [step.from, steps[i + 1].to as [number, number]];
        } else if (!step.from && step.to && lastPoint) {
          polyline = [lastPoint, step.to];
        }
        if (polyline && polyline.length >= 2) {
          const isSimulated = false;
          segs.push({ polyline, color, isSimulated, mode: step.mode, description: step.description });
          lastPoint = polyline[polyline.length - 1];
        }
      }
    }

    if (segs.length === 0 && routeGeometry && routeGeometry.coordinates) {
      const path = toLeafletPositions(routeGeometry);
      if (path.length >= 2) {
        segs.push({ polyline: path, color: getModeColor('default'), isSimulated: false, mode: 'default', description: '' });
      }
    }
    return segs;
  }, [steps, routeGeometry]);

  useEffect(() => {
    const fetchCoordinates = async () => {
      try {
        const newMarkers: [number, number][] = [];

        if (departure) {
          const departureCoords = await geocodeLocation(departure);
          newMarkers.push([departureCoords.lat, departureCoords.lng]);
        }

        if (destination) {
          const destinationCoords = await geocodeLocation(destination);
          newMarkers.push([destinationCoords.lat, destinationCoords.lng]);
        }

        if (newMarkers.length > 0) {
          setMarkers(newMarkers);

          // maps limits
          if (newMarkers.length > 1) {
            setMapBounds(L.latLngBounds(newMarkers.map((marker: [number, number]) => L.latLng(marker[0], marker[1]))));
          }
        }
      } catch (error) {
        console.error("Erreur lors de la géolocalisation des adresses:", error);
      }
    };

    if (departure || destination) {
      fetchCoordinates();
    }
  }, [departure, destination]);

  useEffect(() => {
    if (segments.length > 0) {
      const allPoints: [number, number][] = segments.flatMap(seg => seg.polyline);
      const newBounds = L.latLngBounds(allPoints.map(pt => L.latLng(pt[0], pt[1])));
      // N'appelle setMapBounds que si les bounds changent vraiment
      if (!mapBounds || !mapBounds.equals(newBounds)) {
        setMapBounds(newBounds);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segments]);

  return (
    <MapContainer
      center={[47.5, 2.5]}
      zoom={6}
      className={styles.map}
    >
      <SetMapView bounds={mapBounds} />
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />
      {/* Segments multimodaux colorés */}
      {segments.map((seg, idx) => (
        <Fragment key={`segment-${idx}`}>
          <Polyline
            key={"poly-" + idx}
            positions={seg.polyline}
            color={seg.color}
            weight={seg.mode === "train" ? 4 : seg.mode === "flight" ? 3 : 5}
            opacity={seg.mode === "train" ? 0.85 : 0.95}
            dashArray={seg.mode === "flight" ? "6, 8" : seg.isSimulated ? "12 12" : undefined}
            eventHandlers={seg.isSimulated ? {
              mouseover: (e) => {
                e.target.openTooltip();
              },
              mouseout: (e) => {
                e.target.closeTooltip();
              }
            } : {}}
          >
            {seg.isSimulated && (
              <Tooltip sticky direction="top">
                ⚠️ Simulated path – not the real route
              </Tooltip>
            )}
          </Polyline>
          {/* Emoji ⚠️ au milieu du segment simulé, PROBABLMEENT A RETIRER */}
          {seg.isSimulated && seg.polyline.length >= 2 && (
            <Marker
              key={"warn-" + idx}
              position={[
                (seg.polyline[0][0] + seg.polyline[seg.polyline.length - 1][0]) / 2,
                (seg.polyline[0][1] + seg.polyline[seg.polyline.length - 1][1]) / 2
              ]}
              icon={L.divIcon({
                className: '',
                html: '<span style="font-size:2rem;">⚠️</span>',
                iconSize: [32, 32],
                iconAnchor: [16, 16],
              })}
            >
              {/* Pour afficher le message d'avertissement sur le logo en plus du segment  */}
              <Tooltip direction="top" permanent={false} sticky>
                ⚠️ Simulated path – not the real route
              </Tooltip>
            </Marker>
          )}
        </Fragment>
      ))}
      {/* Marqueurs départ/arrivée */}
      {markers.map((position, idx) => (
        <Marker
          key={`marker-${idx}`}
          position={position}
          title={idx === 0 ? "Départ" : "Destination"}
        />
      ))}
      {/* Overlay de chargement */}
      {loading && (
        <div className={styles.loadingOverlay}>
          <div className={styles.spinner}></div>
        </div>
      )}
      <SetMapView
        bounds={mapBounds}
        center={markers.length === 1 ? markers[0] : null}
        zoom={markers.length === 1 ? 13 : 6}
      />
    </MapContainer>
  );
}
