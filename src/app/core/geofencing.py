import math
from app.core.wards import WARDS

def point_in_polygon(lat, lon, polygon):
    """
    Ray Casting algorithm to check if point is inside polygon
    """
    inside = False
    n = len(polygon)
    x, y = lat, lon

    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]

        if ((y1 > y) != (y2 > y)):
            intersect_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersect_x:
                inside = not inside

    return inside

def calculate_distance(lat1, lon1, lat2, lon2):
    """Simple Euclidean distance for ward center proximity"""
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)

def get_ward(lat, lon):
    # 1. Direct Check (Internal)
    for ward_name, polygon in WARDS.items():
        if point_in_polygon(lat, lon, polygon):
            return ward_name
    
    # 2. Fallback: Find Nearest Ward (Proximity Routing)
    nearest_ward = "Ward-1 (Old City/Nyay Mandir)"
    min_dist = float('inf')
    
    for ward_name, polygon in WARDS.items():
        # Calculate distance to polygon centroid (simplified as average of points)
        avg_lat = sum(p[0] for p in polygon) / len(polygon)
        avg_lon = sum(p[1] for p in polygon) / len(polygon)
        
        dist = calculate_distance(lat, lon, avg_lat, avg_lon)
        if dist < min_dist:
            min_dist = dist
            nearest_ward = ward_name
            
    return nearest_ward
