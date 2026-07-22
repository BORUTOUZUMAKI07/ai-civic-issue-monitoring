from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_rag_context(
    current_issue: dict[str, Any],
    similar_issues: list[dict[str, Any]],
) -> str:
    """Build a context string from retrieved similar issues for LLM prompting.

    This context is injected into the classification/routing prompts so the
    LLM can leverage historical patterns when making decisions.
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
        lines.append(f"## Similar Historical Issues ({len(similar_issues)} found)")
        for i, issue in enumerate(similar_issues[:5], 1):
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

        avg_sim = sum(i.get("similarity", 0) for i in similar_issues) / len(similar_issues)
        resolved = sum(1 for i in similar_issues if i.get("status") == "resolved")
        lines.append(
            f"Historical pattern: {resolved}/{len(similar_issues)} similar issues resolved, "
            f"avg similarity: {avg_sim:.2f}"
        )
    else:
        lines.append("## Similar Historical Issues")
        lines.append("No similar historical issues found.")

    return "\n".join(lines)
