from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgentState

logger = logging.getLogger(__name__)

DEPARTMENT_MAP: dict[str, str] = {
    "pothole": "Roads & Infrastructure",
    "garbage": "Solid Waste Management",
    "debris": "Town Planning & Enforcement",
}


async def route_issue(state: AgentState) -> dict[str, Any]:
    """Route issue to appropriate department and assign priority."""
    category = state.get("category", "pothole")
    severity_str = state.get("severity", "1")

    try:
        severity = int(severity_str)
    except (ValueError, TypeError):
        severity = 1

    department = DEPARTMENT_MAP.get(category, "General")

    if severity >= 5:
        priority = "urgent"
    elif severity >= 4:
        priority = "high"
    elif severity >= 3:
        priority = "medium"
    else:
        priority = "normal"

    logger.info(
        "Routed issue %s: department=%s, priority=%s (severity=%d)",
        state.get("issue_id"),
        department,
        priority,
        severity,
    )

    return {
        "action": department,
        "priority": priority,
        "result": {
            **(state.get("result") or {}),
            "department": department,
            "priority": priority,
        },
        "messages": state.get("messages", []),
    }
