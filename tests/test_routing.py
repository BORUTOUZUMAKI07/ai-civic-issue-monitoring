import pytest
from app.core.routing import get_engineer_for_ward

def test_routing_valid_ward():
    engineer = get_engineer_for_ward("Ward-1")
    assert engineer["name"] == "Engineer Alpha"
    assert "email" in engineer

def test_routing_invalid_ward():
    engineer = get_engineer_for_ward("Invalid-Ward")
    assert engineer["name"] == "General Maintenance"
