from __future__ import annotations

from src.agents.routing import DEPARTMENT_MAP


def test_road_department() -> None:
    assert DEPARTMENT_MAP.get("pothole") == "Roads & Infrastructure"


def test_sanitation_department() -> None:
    assert DEPARTMENT_MAP.get("garbage") == "Solid Waste Management"


def test_planning_department() -> None:
    assert DEPARTMENT_MAP.get("debris") == "Town Planning & Enforcement"


def test_removed_categories_have_no_department() -> None:
    # Removed categories no longer route to a specific department.
    for removed in ("road_damage", "sewage", "broken_streetlight", "waterlogging"):
        assert DEPARTMENT_MAP.get(removed) is None


def test_general_department() -> None:
    assert DEPARTMENT_MAP.get("unknown_category") is None
