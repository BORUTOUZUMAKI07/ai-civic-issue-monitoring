from app.core.routing import get_engineer_for_ward

def test_routing_valid_ward():
    engineer = get_engineer_for_ward("Ward-1 (Old City/Nyay Mandir)")
    assert engineer["name"] == "Arjun Patel"
    assert "email" in engineer

def test_routing_invalid_ward():
    engineer = get_engineer_for_ward("Invalid-Ward")
    assert engineer["name"] == "General Maintenance"
