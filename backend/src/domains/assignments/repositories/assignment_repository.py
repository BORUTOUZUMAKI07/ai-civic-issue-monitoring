from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.assignments.models.assignment import Assignment, AssignmentStatus


class AssignmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, assignment_id: int) -> Assignment | None:
        result = await self.db.execute(select(Assignment).where(Assignment.id == assignment_id))
        return result.scalar_one_or_none()

    async def get_by_issue(self, issue_id: int) -> Assignment | None:
        result = await self.db.execute(select(Assignment).where(Assignment.issue_id == issue_id))
        return result.scalars().first()

    async def delete_by_issue(self, issue_id: int) -> int:
        """Remove every assignment pointing at ``issue_id``.

        Returns the number of rows deleted. Assignments have no unique
        constraint on ``issue_id``, so an issue that has been reassigned can
        hold more than one — which is exactly why this takes all of them
        rather than a single row, and why :meth:`get_by_issue` reads
        ``.first()`` instead of ``scalar_one_or_none()`` (the latter raises
        ``MultipleResultsFound`` once a duplicate exists, turning every later
        read of that issue into a 500).
        """
        from sqlalchemy import delete
        from sqlalchemy.engine import CursorResult

        result = await self.db.execute(delete(Assignment).where(Assignment.issue_id == issue_id))
        # `Session.execute` is typed as returning the general `Result`, which
        # has no `rowcount`; a DML statement always comes back as a
        # `CursorResult`, which does. Narrow rather than `getattr` so a future
        # refactor that returns something else still gets flagged.
        return int(cast("CursorResult[Any]", result).rowcount or 0)

    async def get_by_engineer(self, engineer_id: int, status: AssignmentStatus | None = None) -> list[Assignment]:
        query = select(Assignment).where(Assignment.engineer_id == engineer_id)
        if status:
            query = query.where(Assignment.status == status)
        result = await self.db.execute(query.order_by(Assignment.assigned_at.desc()))
        return list(result.scalars().all())

    async def count_active_for_engineer(self, engineer_id: int) -> int:
        active_statuses = (
            AssignmentStatus.pending,
            AssignmentStatus.accepted,
            AssignmentStatus.in_progress,
        )
        result = await self.db.execute(
            select(Assignment).where(
                Assignment.engineer_id == engineer_id,
                Assignment.status.in_(active_statuses),
            )
        )
        return len(list(result.scalars().all()))

    async def create(self, assignment: Assignment) -> Assignment:
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def latest_by_issue_ids(self, issue_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Return the latest assignment per issue, joined to its engineer's user.

        Maps ``issue_id -> {"user_id": int, "full_name": str}``. Done as a single
        query (max-id subquery) rather than one-per-issue, so rendering a page of
        issues does not fan out into N+1 selects.
        """
        if not issue_ids:
            return {}
        from sqlalchemy import func

        from src.domains.engineers.models.engineer import Engineer
        from src.domains.users.models.user import User

        latest = (
            select(Assignment.issue_id, func.max(Assignment.id).label("max_id"))
            .where(Assignment.issue_id.in_(issue_ids))
            .group_by(Assignment.issue_id)
            .subquery()
        )
        stmt = (
            select(Assignment, Engineer.user_id, User.full_name)
            .join(latest, Assignment.id == latest.c.max_id)
            .join(Engineer, Assignment.engineer_id == Engineer.id)
            .join(User, Engineer.user_id == User.id)
        )
        result = await self.db.execute(stmt)
        return {row[0].issue_id: {"user_id": row[1], "full_name": row[2]} for row in result.all()}

    async def list_by_engineer_with_issue(self, engineer_id: int) -> list[tuple[Assignment, Any]]:
        """Assignments for an engineer joined to their issue, newest first."""
        from src.domains.issues.models.issue import Issue

        stmt = (
            select(Assignment, Issue)
            .join(Issue, Assignment.issue_id == Issue.id)
            .where(Assignment.engineer_id == engineer_id)
            .order_by(Assignment.assigned_at.desc())
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def update_status(self, assignment_id: int, status: AssignmentStatus) -> Assignment | None:
        assignment = await self.get(assignment_id)
        if not assignment:
            return None
        assignment.status = status
        from datetime import datetime, timezone

        if status == AssignmentStatus.accepted:
            assignment.accepted_at = datetime.now(timezone.utc)
        elif status == AssignmentStatus.completed:
            assignment.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment
