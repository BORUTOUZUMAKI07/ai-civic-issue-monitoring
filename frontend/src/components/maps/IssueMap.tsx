"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

interface HeatmapPoint {
  lat: number;
  lng: number;
  type: string;
  severity: number;
  status: string;
}

interface IssueMapProps {
  points: HeatmapPoint[];
  center?: [number, number];
  zoom?: number;
  className?: string;
}

const TYPE_COLORS: Record<string, string> = {
  pothole: "#ef4444",
  garbage: "#f59e0b",
  debris: "#8b5cf6",
};

const SEVERITY_SIZES: Record<number, number> = {
  5: 14,
  4: 12,
  3: 10,
  2: 8,
  1: 6,
};

function createIssueIcon(type: string, severity: number): L.DivIcon {
  const color = TYPE_COLORS[type] || "#6b7280";
  const size = SEVERITY_SIZES[severity] || 8;

  return L.divIcon({
    className: "issue-marker",
    html: `<div style="
      width: ${size * 2}px;
      height: ${size * 2}px;
      background: ${color};
      border: 2px solid white;
      border-radius: 50%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    "></div>`,
    iconSize: [size * 2, size * 2],
    iconAnchor: [size, size],
  });
}

const SEVERITY_LABELS: Record<number, string> = {
  5: "Critical",
  4: "High",
  3: "Medium",
  2: "Low",
  1: "Minimal",
};

export function IssueMap({
  points,
  center = [22.3072, 73.1812],
  zoom = 12,
  className = "",
}: IssueMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.Marker[]>([]);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = L.map(mapRef.current).setView(center, zoom);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    points.forEach((point, idx) => {
      const icon = createIssueIcon(point.type, point.severity);
      const marker = L.marker([point.lat, point.lng], { icon })
        .addTo(map)
        .bindPopup(
          `<div class="p-2">
            <h3 class="font-bold text-sm">${point.type.replace(/_/g, " ")}</h3>
            <p class="text-xs text-gray-500">Severity: ${SEVERITY_LABELS[point.severity] || point.severity}</p>
            <p class="text-xs capitalize">Status: ${point.status.replace(/_/g, " ")}</p>
          </div>`
        );
      markersRef.current.push(marker);
    });

    if (points.length > 0) {
      const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lng] as [number, number]));
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }, [points]);

  return (
    <div
      ref={mapRef}
      className={`h-full w-full rounded-lg ${className}`}
      style={{ minHeight: "400px" }}
    />
  );
}
