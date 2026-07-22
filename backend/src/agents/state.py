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
    result: dict[str, Any]
    errors: list[str]
