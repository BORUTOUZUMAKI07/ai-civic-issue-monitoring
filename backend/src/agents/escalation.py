from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgentState

logger = logging.getLogger(__name__)

ESCALATION_MATRIX: dict[str, dict[str, Any]] = {
    # Keyed by the department strings ``route_issue`` actually produces (see
    # ``src.agents.routing.DEPARTMENT_MAP``) plus the ``"General"`` fallback.
    # The matrix previously used short slugs ("road", "sanitation", ...) that
    # never matched the department names, so every issue silently fell through
    # to the generic Ward Office entry and the per-department SLA was inert.
    "Roads & Infrastructure": {"contact": "Road & Transport Dept", "sla_hours": 4},
    "Solid Waste Management": {"contact": "Sanitation Dept", "sla_hours": 6},
    "Town Planning & Enforcement": {"contact": "Town Planning Dept", "sla_hours": 8},
    "General": {"contact": "Ward Office", "sla_hours": 24},
}


async def escalate_issue(state: AgentState) -> dict[str, Any]:
    category = state.get("category", "pothole")
    severity = int(state.get("severity", "1"))
    issue_id = state.get("issue_id", "")

    from src.agents.routing import DEPARTMENT_MAP

    department = DEPARTMENT_MAP.get(category, "General")
    escalation = ESCALATION_MATRIX.get(department, ESCALATION_MATRIX["General"])

    sla_hours = escalation["sla_hours"]
    if severity >= 5:
        sla_hours = max(1, sla_hours // 4)
    elif severity >= 4:
        sla_hours = max(2, sla_hours // 2)

    logger.warning(
        "Escalated issue %s: dept=%s, severity=%d, sla=%dh",
        issue_id,
        department,
        severity,
        sla_hours,
    )

    return {
        "result": {
            "escalated": True,
            "department": department,
            "contact": escalation["contact"],
            "sla_hours": sla_hours,
            "severity": severity,
        },
        "messages": state.get("messages", []),
    }
