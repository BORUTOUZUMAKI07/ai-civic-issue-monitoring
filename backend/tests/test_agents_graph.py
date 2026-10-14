from __future__ import annotations

from src.agents.graph import AnalyticsGraph


def test_analytics_branch_reachable_when_opted_in() -> None:
    graph = AnalyticsGraph()
    state = {"severity": "1", "priority": "normal", "run_analytics": True}
    # ``route_issue`` overwrites ``action`` with the department name, so the
    # analytics branch must key off the dedicated ``run_analytics`` flag.
    assert graph._decide_next(state) == "analytics"


def test_analytics_not_chosen_by_default() -> None:
    graph = AnalyticsGraph()
    assert graph._decide_next({"severity": "1", "priority": "normal"}) == "match"


def test_urgent_still_escalates_even_with_analytics() -> None:
    graph = AnalyticsGraph()
    state = {"severity": "5", "priority": "urgent", "run_analytics": True}
    assert graph._decide_next(state) == "escalate"
