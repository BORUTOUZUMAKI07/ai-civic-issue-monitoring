import math
from typing import Optional

from src.models.ward import Ward


def _extract_coords(polygon: dict | list) -> list[tuple[float, float]]:
    """Extract (lat, lon) coordinate pairs from any polygon format.

    Supports:
    - GeoJSON: {"type": "Polygon", "coordinates": [[ [lon, lat], ... ]]}
    - Legacy: [{"lat": ..., "lon": ...}, ...]
    - Raw list: [[lat, lon], ...] or [[lon, lat], ...]
    """
    if isinstance(polygon, dict):
        coords = polygon.get("coordinates", [])
        if coords and isinstance(coords[0], list) and isinstance(coords[0][0], list):
            ring = coords[0]
            return [(pt[1], pt[0]) for pt in ring]
        return []

    if isinstance(polygon, list) and len(polygon) > 0:
        first = polygon[0]
        if isinstance(first, dict) and "lat" in first and "lon" in first:
            return [(p["lat"], p["lon"]) for p in polygon]
        if isinstance(first, (list, tuple)) and len(first) == 2:
            if isinstance(first[0], (int, float)) and isinstance(first[1], (int, float)):
                return [(p[0], p[1]) for p in polygon]

    return []


def point_in_polygon(lat: float, lon: float, polygon: dict | list) -> bool:
    """Ray Casting algorithm to check if point is inside polygon."""
    coords = _extract_coords(polygon)
    if len(coords) < 3:
        return False

    inside = False
    n = len(coords)
    for i in range(n):
        y1, x1 = coords[i]
        y2, x2 = coords[(i + 1) % n]

        if (y1 > lat) != (y2 > lat):
            intersect_x = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < intersect_x:
                inside = not inside

    return inside


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers."""
    earth_radius_km = 6371.0
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


def get_ward_from_coords(lat: float, lon: float, wards: list[Ward]) -> Optional[Ward]:
    """Find ward for given coordinates. Falls back to nearest ward centroid."""
    for ward in wards:
        if point_in_polygon(lat, lon, ward.polygon):
            return ward

    nearest_ward = None
    min_dist = float("inf")
    for ward in wards:
        dist = calculate_distance(lat, lon, ward.center_lat, ward.center_lon)
        if dist < min_dist:
            min_dist = dist
            nearest_ward = ward

    return nearest_ward
