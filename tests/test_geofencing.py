import pytest
from app.core.geofencing import get_ward

def test_get_ward_vadodara_center():
    # Vadodara center roughly
    lat, lon = 22.3072, 73.1812
    ward = get_ward(lat, lon)
    assert isinstance(ward, str)
    assert "Ward" in ward

def test_get_ward_out_of_bounds():
    # Somewhere far away
    lat, lon = 0.0, 0.0
    ward = get_ward(lat, lon)
    assert ward == "Unknown"
