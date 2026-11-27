"use client";

import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { FALLBACK_CENTER, nudgeLocation } from "@/lib/location";

interface LocationPickerProps {
  lat?: number | null;
  lng?: number | null;
  onChange: (lat: number, lng: number) => void;
  height?: number;
}

export function LocationPicker({ lat, lng, onChange, height = 260 }: LocationPickerProps) {
  const helpId = useId();
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const hasCoords = typeof lat === "number" && Number.isFinite(lat) && typeof lng === "number" && Number.isFinite(lng);
    const center: [number, number] = hasCoords ? [lat as number, lng as number] : FALLBACK_CENTER;

    const map = L.map(mapRef.current).setView(center, hasCoords ? 16 : 12);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);

    const icon = L.divIcon({
      className: "location-pin",
      html: '<div style="width:26px;height:26px;background:#dc2626;border:3px solid #fff;border-radius:50% 50% 50% 0;transform:rotate(-45deg);box-shadow:0 2px 6px rgba(0,0,0,.35)"></div>',
      iconSize: [26, 26],
      iconAnchor: [13, 26],
    });

    const marker = L.marker(center, { icon, draggable: true }).addTo(map);
    markerRef.current = marker;

    const emit = (position: L.LatLng) => onChange(position.lat, position.lng);

    marker.on("dragend", () => emit(marker.getLatLng()));
    map.on("click", (e: L.LeafletMouseEvent) => {
      marker.setLatLng(e.latlng);
      emit(e.latlng);
    });

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    const marker = markerRef.current;
    if (!map || !marker || typeof lat !== "number" || !Number.isFinite(lat) || typeof lng !== "number" || !Number.isFinite(lng)) return;
    marker.setLatLng([lat, lng]);
    if (map.getZoom() < 15) map.setZoom(15);
    map.panTo([lat, lng]);
  }, [lat, lng]);

  // Leaflet handles pointer input; keyboard users need an explicit control.
  // Moving the pin emits on every arrow key so the form state stays in sync
  // with what the user sees.
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const marker = markerRef.current;
    if (!marker) return;
    const current = marker.getLatLng();

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onChange(current.lat, current.lng);
      return;
    }

    const next = nudgeLocation([current.lat, current.lng], event.key);
    if (!next) return;
    event.preventDefault();
    marker.setLatLng(next);
    onChange(next[0], next[1]);
  };

  return (
    <>
      <div
        ref={mapRef}
        className="w-full rounded-lg border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        style={{ height }}
        role="button"
        tabIndex={0}
        aria-label="Set issue location on the map"
        aria-describedby={helpId}
        onKeyDown={handleKeyDown}
      />
      <span id={helpId} className="sr-only">
        Click the map to place the pin. With the keyboard, use the arrow keys to
        move it and press Enter to confirm.
      </span>
    </>
  );
}
