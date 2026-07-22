from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from src.agents.state import AgentState
from src.core.database import AsyncSessionLocal
from src.models.engineer import Engineer
from src.models.user import User

logger = logging.getLogger(__name__)


async def match_engineer(state: AgentState) -> dict[str, Any]:
    """Find the best available engineer for this issue based on ward + workload."""
    category = state.get("category", "pothole")
    ward_id = state.get("ward_id", "")
    issue_id = state.get("issue_id", "")

    logger.info(
        "Matching engineer for issue %s: category=%s, ward=%s",
        issue_id,
        category,
        ward_id,
    )

    try:
        ward_id_int = int(ward_id) if ward_id else None
    except (ValueError, TypeError):
        ward_id_int = None

    if not ward_id_int:
        return {
            "result": {
                **(state.get("result") or {}),
                "matched": False,
                "reason": "No ward_id provided",
            },
            "messages": state.get("messages", []),
        }

    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(Engineer, User.full_name, User.email)
                .join(User, Engineer.user_id == User.id)
                .where(
                    Engineer.ward_id == ward_id_int,
                    Engineer.is_available.is_(True),
                    Engineer.current_workload < Engineer.max_workload,
                )
                .order_by(Engineer.current_workload.asc())
                .limit(1)
            )
            result = await db.execute(stmt)
            row = result.first()

            if row:
                engineer, name, email = row
                logger.info(
                    "Matched engineer %s (workload=%d/%d) for issue %s",
                    name,
                    engineer.current_workload,
                    engineer.max_workload,
                    issue_id,
                )
                return {
                    "result": {
                        **(state.get("result") or {}),
                        "matched": True,
                        "engineer_id": engineer.id,
                        "engineer_name": name,
                        "engineer_email": email,
                        "workload": f"{engineer.current_workload}/{engineer.max_workload}",
                    },
                    "messages": state.get("messages", []),
                }
            else:
                logger.warning("No available engineer in ward %s for issue %s", ward_id, issue_id)
                return {
                    "result": {
                        **(state.get("result") or {}),
                        "matched": False,
                        "reason": f"No available engineers in ward {ward_id}",
                    },
                    "messages": state.get("messages", []),
                }
    except Exception as e:
        logger.error("Engineer matching failed for issue %s: %s", issue_id, e)
        return {
            "result": {
                **(state.get("result") or {}),
                "matched": False,
                "reason": f"Matching error: {e}",
            },
            "messages": state.get("messages", []),
        }
