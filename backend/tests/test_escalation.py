from __future__ import annotations

from src.agents.escalation import ESCALATION_MATRIX, escalate_issue
from src.agents.routing import DEPARTMENT_MAP


def test_matrix_is_keyed_by_real_departments() -> None:
    # Every department ``route_issue`` can emit must have its own escalation
    # entry; the "General" fallback covers unknown categories.
    for department in DEPARTMENT_MAP.values():
        assert department in ESCALATION_MATRIX


async def test_pothole_uses_roads_infrastructure_entry() -> None:
    result = await escalate_issue({"category": "pothole", "severity": "1", "issue_id": "1"})
    payload = result["result"]
    assert payload["department"] == "Roads & Infrastructure"
    assert payload["contact"] == "Road & Transport Dept"
    assert payload["sla_hours"] == 4


async def test_unknown_category_falls_back_to_general() -> None:
    result = await escalate_issue({"category": "mystery", "severity": "1", "issue_id": "2"})
    payload = result["result"]
    assert payload["department"] == "General"
    assert payload["contact"] == "Ward Office"
    assert payload["sla_hours"] == 24


async def test_high_severity_tightens_sla() -> None:
    critical = await escalate_issue({"category": "pothole", "severity": "5", "issue_id": "3"})
    high = await escalate_issue({"category": "pothole", "severity": "4", "issue_id": "4"})
    assert critical["result"]["sla_hours"] == 1
    assert high["result"]["sla_hours"] == 2
