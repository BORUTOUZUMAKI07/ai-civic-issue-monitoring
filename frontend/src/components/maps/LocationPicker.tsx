"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

interface LocationPickerProps {
  lat?: number | null;
  lng?: number | null;
  onChange: (lat: number, lng: number) => void;
  height?: number;
}

const FALLBACK_CENTER: [number, number] = [22.3072, 73.1812];

export function LocationPicker({ lat, lng, onChange, height = 260 }: LocationPickerProps) {
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

  return (
    <div
      ref={mapRef}
      className="w-full rounded-lg border border-border"
      style={{ height }}
      role="button"
      aria-label="Set issue location by clicking on the map"
    />
  );
}
