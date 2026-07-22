from __future__ import annotations

from src.agents.routing import DEPARTMENT_MAP


def test_road_department() -> None:
    assert DEPARTMENT_MAP.get("pothole") == "Roads & Infrastructure"
    assert DEPARTMENT_MAP.get("road_damage") == "Roads & Infrastructure"
    assert DEPARTMENT_MAP.get("debris") == "Town Planning & Enforcement"


def test_sanitation_department() -> None:
    assert DEPARTMENT_MAP.get("garbage") == "Solid Waste Management"
    assert DEPARTMENT_MAP.get("sewage") == "Sewage & Sanitation"


def test_infrastructure_department() -> None:
    assert DEPARTMENT_MAP.get("broken_streetlight") == "Electrical & Lighting"
    assert DEPARTMENT_MAP.get("waterlogging") == "Drainage & Flood Control"


def test_general_department() -> None:
    assert DEPARTMENT_MAP.get("unknown_category") is None
