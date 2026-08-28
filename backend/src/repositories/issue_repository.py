from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.issue import Issue, IssueStatus
from src.models.ward import Ward


class IssueRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, issue_id: int) -> Issue | None:
        result = await self.db.execute(select(Issue).where(Issue.id == issue_id))
        return result.scalar_one_or_none()

    async def create(self, issue: Issue) -> Issue:
        self.db.add(issue)
        await self.db.commit()
        await self.db.refresh(issue)
        return issue

    async def update_status(self, issue_id: int, status: IssueStatus) -> Issue | None:
        issue = await self.get(issue_id)
        if not issue:
            return None
        issue.status = status
        if status == IssueStatus.resolved:
            issue.resolved_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(issue)
        return issue

    async def list_by_ward(self, ward_id: int, skip: int = 0, limit: int = 20) -> list[Issue]:
        result = await self.db.execute(
            select(Issue).where(Issue.ward_id == ward_id).order_by(Issue.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_status(self, status: IssueStatus, skip: int = 0, limit: int = 20) -> list[Issue]:
        result = await self.db.execute(
            select(Issue).where(Issue.status == status).order_by(Issue.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(self, skip: int = 0, limit: int = 20) -> list[Issue]:
        result = await self.db.execute(select(Issue).order_by(Issue.created_at.desc()).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self.db.execute(select(func.count(Issue.id)))
        return result.scalar_one()

    async def count_by_status(self) -> dict[str, int]:
        result = await self.db.execute(select(Issue.status, func.count(Issue.id)).group_by(Issue.status))
        return {str(row[0].value): row[1] for row in result.all()}

    async def count_by_type(self) -> dict[str, int]:
        result = await self.db.execute(select(Issue.issue_type, func.count(Issue.id)).group_by(Issue.issue_type))
        return {str(row[0].value): row[1] for row in result.all()}

    async def count_by_ward(self) -> list[dict]:
        result = await self.db.execute(
            select(Ward.name, func.count(Issue.id)).join(Ward, Ward.id == Issue.ward_id).group_by(Ward.name)
        )
        return [{"ward": row[0], "count": row[1]} for row in result.all()]

    async def get_recent(self, days: int = 30) -> list[Issue]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(Issue).where(Issue.created_at >= cutoff).order_by(Issue.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_heatmap_points(self) -> list[dict]:
        result = await self.db.execute(
            select(Issue.latitude, Issue.longitude, Issue.issue_type, Issue.severity, Issue.status)
        )
        return [
            {"lat": row[0], "lng": row[1], "type": str(row[2].value), "severity": row[3], "status": str(row[4].value)}
            for row in result.all()
        ]

    async def commit(self) -> None:
        await self.db.commit()
