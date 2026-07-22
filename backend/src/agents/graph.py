from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.agents.state import AgentState

logger = logging.getLogger(__name__)


class AnalyticsGraph:
    """LangGraph agent for CivicPulse issue processing.

    Workflow:
      classify -> route -> (match | escalate | analytics) -> END

    Each node enriches the state with real data:
      - classify: OpenAI/keyword classification with confidence
      - route: department assignment + priority
      - match: real DB engineer lookup
      - escalate: SLA calculation + escalation path
      - analytics: real historical data from DB
    """

    def __init__(self) -> None:
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        workflow.add_node("classify", self._classify_node)
        workflow.add_node("route", self._route_node)
        workflow.add_node("match", self._match_node)
        workflow.add_node("escalate", self._escalate_node)
        workflow.add_node("analytics", self._analytics_node)

        workflow.set_entry_point("classify")
        workflow.add_edge("classify", "route")
        workflow.add_conditional_edges(
            "route",
            self._decide_next,
            {"match": "match", "escalate": "escalate", "analytics": "analytics"},
        )
        workflow.add_edge("match", END)
        workflow.add_edge("escalate", END)
        workflow.add_edge("analytics", END)

        return workflow.compile()

    async def _classify_node(self, state: AgentState) -> dict[str, Any]:
        from src.agents.classifier import classify_issue

        return await classify_issue(state)

    async def _route_node(self, state: AgentState) -> dict[str, Any]:
        from src.agents.routing import route_issue

        return await route_issue(state)

    async def _match_node(self, state: AgentState) -> dict[str, Any]:
        from src.agents.matching import match_engineer

        return await match_engineer(state)

    async def _escalate_node(self, state: AgentState) -> dict[str, Any]:
        from src.agents.escalation import escalate_issue

        return await escalate_issue(state)

    async def _analytics_node(self, state: AgentState) -> dict[str, Any]:
        from src.agents.analytics import generate_analytics

        return await generate_analytics(state)

    def _decide_next(self, state: AgentState) -> Literal["match", "escalate", "analytics"]:
        severity_str = state.get("severity", "1")
        priority = state.get("priority", "normal")

        try:
            severity = int(severity_str)
        except (ValueError, TypeError):
            severity = 1

        if severity >= 4 or priority == "urgent":
            return "escalate"
        if state.get("action") == "analytics":
            return "analytics"
        return "match"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run the full agent pipeline and return the final enriched state."""
        initial_state: AgentState = {
            "messages": [],
            "issue_id": str(input_data.get("issue_id", "")),
            "category": input_data.get("category", ""),
            "description": input_data.get("description", ""),
            "ward_id": str(input_data.get("ward_id", "")),
            "severity": str(input_data.get("severity", "1")),
            "priority": "normal",
            "action": "",
            "result": {},
            "errors": [],
        }
        final_state = await self.graph.ainvoke(initial_state)
        return dict(final_state)
