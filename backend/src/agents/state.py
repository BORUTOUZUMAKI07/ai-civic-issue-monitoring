from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    messages: list[Any]
    issue_id: str
    category: str
    description: str
    ward_id: str
    severity: str
    priority: str
    action: str
    # Opt-in enrichment flag. ``route_issue`` overwrites ``action`` with the
    # department name, so a request for the analytics branch cannot be signalled
    # through ``action``; this dedicated field survives routing.
    run_analytics: bool
    result: dict[str, Any]
    errors: list[str]
