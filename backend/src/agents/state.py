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
    # Retrieved historical context (rendered by ``build_rag_context``) injected
    # into the LLM classification prompt when RAG_CLASSIFY_ENABLED is on.
    rag_context: str
    # Confidence the intake gate assigned to ``category`` before the agent ran.
    # The classifier only re-consults the LLM (with the Rag context) when this is
    # below RAG_CLASSIFY_MIN_CONFIDENCE.
    category_confidence: float
    result: dict[str, Any]
    errors: list[str]
