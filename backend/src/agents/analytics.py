from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from src.agents.state import AgentState
from src.core.database import AsyncSessionLocal
from src.models.issue import Issue, IssueStatus, IssueType

logger = logging.getLogger(__name__)


async def generate_analytics(state: AgentState) -> dict[str, Any]:
    """Generate real analytics for this issue from the database."""
    category = state.get("category", "pothole")
    ward_id = state.get("ward_id", "")
    issue_id = state.get("issue_id", "")

    logger.info(
        "Generating analytics for issue %s: category=%s, ward=%s",
        issue_id,
        category,
        ward_id,
    )

    try:
        ward_id_int = int(ward_id) if ward_id else None
    except (ValueError, TypeError):
        ward_id_int = None

    try:
        async with AsyncSessionLocal() as db:
            type_match = IssueType(category) if category in [t.value for t in IssueType] else IssueType.pothole

            count_stmt = select(func.count(Issue.id)).where(Issue.issue_type == type_match)
            if ward_id_int:
                count_stmt = count_stmt.where(Issue.ward_id == ward_id_int)
            count_result = await db.execute(count_stmt)
            similar_count = count_result.scalar() or 0

            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            recent_stmt = select(func.count(Issue.id)).where(
                Issue.issue_type == type_match,
                Issue.created_at >= thirty_days_ago,
            )
            if ward_id_int:
                recent_stmt = recent_stmt.where(Issue.ward_id == ward_id_int)
            recent_result = await db.execute(recent_stmt)
            recent_count = recent_result.scalar() or 0

            resolved_stmt = select(func.avg(func.extract("epoch", Issue.resolved_at - Issue.created_at) / 3600)).where(
                Issue.issue_type == type_match,
                Issue.status == IssueStatus.resolved,
                Issue.resolved_at.isnot(None),
            )
            if ward_id_int:
                resolved_stmt = resolved_stmt.where(Issue.ward_id == ward_id_int)
            resolved_result = await db.execute(resolved_stmt)
            avg_hours = resolved_result.scalar()

            total_stmt = select(func.count(Issue.id)).where(Issue.created_at >= thirty_days_ago)
            if ward_id_int:
                total_stmt = total_stmt.where(Issue.ward_id == ward_id_int)
            total_result = await db.execute(total_stmt)
            total_recent = total_result.scalar() or 1

            trend_ratio = recent_count / total_recent if total_recent > 0 else 0
            if trend_ratio > 0.3:
                trend = "increasing"
            elif trend_ratio < 0.1:
                trend = "decreasing"
            else:
                trend = "stable"

            analytics = {
                "similar_issues_count": similar_count,
                "recent_30d_count": recent_count,
                "avg_resolution_time_hours": round(float(avg_hours), 1) if avg_hours else None,
                "trend": trend,
                "trend_ratio": round(trend_ratio, 3),
            }

            logger.info(
                "Analytics for issue %s: similar=%d, avg_resolve=%.1fh, trend=%s",
                issue_id,
                similar_count,
                float(avg_hours or 0),
                trend,
            )

            return {
                "result": {
                    **(state.get("result") or {}),
                    "analytics_generated": True,
                    "category": category,
                    "ward_id": ward_id,
                    "metrics": analytics,
                },
                "messages": state.get("messages", []),
            }
    except Exception as e:
        logger.error("Analytics generation failed for issue %s: %s", issue_id, e)
        return {
            "result": {
                **(state.get("result") or {}),
                "analytics_generated": False,
                "error": str(e),
            },
            "messages": state.get("messages", []),
        }
