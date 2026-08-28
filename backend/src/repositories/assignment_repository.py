from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.assignment import Assignment, AssignmentStatus


class AssignmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, assignment_id: int) -> Assignment | None:
        result = await self.db.execute(select(Assignment).where(Assignment.id == assignment_id))
        return result.scalar_one_or_none()

    async def get_by_issue(self, issue_id: int) -> Assignment | None:
        result = await self.db.execute(select(Assignment).where(Assignment.issue_id == issue_id))
        return result.scalar_one_or_none()

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
