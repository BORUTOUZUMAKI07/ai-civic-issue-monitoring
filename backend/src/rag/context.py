from __future__ import annotations

import logging
from typing import Any

from src.core.config import settings

logger = logging.getLogger(__name__)


def build_rag_context(
    current_issue: dict[str, Any],
    similar_issues: list[dict[str, Any]],
) -> str:
    """Build a context string from retrieved similar issues for LLM prompting.

    Consumed by the RAG-assisted classifier (``src/agents/classifier.py``) when
    ``RAG_CLASSIFY_ENABLED`` is on, and returned by the ``/issues/similar`` and
    ``/issues/search`` endpoints for display. The number of issues rendered is
    bounded by ``RAG_MAX_CONTEXT_ISSUES``.
    """
    lines = [
        "## Current Issue",
        f"Type: {current_issue.get('issue_type', 'unknown')}",
        f"Description: {current_issue.get('description', 'no description')}",
        f"Severity: {current_issue.get('severity', 'unknown')}",
        f"Ward: {current_issue.get('ward_id', 'unknown')}",
        "",
    ]

    if similar_issues:
        limit = max(1, settings.RAG_MAX_CONTEXT_ISSUES)
        shown = similar_issues[:limit]
        lines.append(f"## Similar Historical Issues ({len(shown)} found)")
        for i, issue in enumerate(shown, 1):
            sim_pct = issue.get("similarity", 0) * 100
            lines.append(
                f"{i}. [{issue.get('issue_type', '?')}] "
                f"Severity {issue.get('severity', '?')} — "
                f"Status: {issue.get('status', '?')} — "
                f"Similarity: {sim_pct:.0f}%"
            )
            if issue.get("description"):
                lines.append(f'   "{issue["description"][:120]}"')
        lines.append("")

        avg_sim = sum(i.get("similarity", 0) for i in shown) / len(shown)
        resolved = sum(1 for i in shown if i.get("status") == "resolved")
        lines.append(
            f"Historical pattern: {resolved}/{len(shown)} similar issues resolved, avg similarity: {avg_sim:.2f}"
        )
    else:
        lines.append("## Similar Historical Issues")
        lines.append("No similar historical issues found.")

    return "\n".join(lines)
