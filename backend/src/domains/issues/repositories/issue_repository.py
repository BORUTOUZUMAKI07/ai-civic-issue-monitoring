from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.issues.models.issue import Issue, IssueStatus
from src.domains.wards.models.ward import Ward


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

    @staticmethod
    def _apply_filters(
        stmt,
        *,
        status: str | None = None,
        issue_type: str | None = None,
        severity: int | None = None,
        ward_id: int | None = None,
        search: str = "",
    ):
        """Shared WHERE clauses for list + count so the page and its total agree.

        Values are validated at the HTTP edge (the route constrains them to the
        enum members / column types), so here they map straight onto columns.
        """
        if status:
            stmt = stmt.where(Issue.status == status)
        if issue_type:
            stmt = stmt.where(Issue.issue_type == issue_type)
        if severity is not None:
            stmt = stmt.where(Issue.severity == severity)
        if ward_id is not None:
            stmt = stmt.where(Issue.ward_id == ward_id)
        if search:
            stmt = stmt.where(Issue.description.ilike(f"%{search}%"))
        return stmt

    # Sort keys are an explicit allowlist -> column, so a caller cannot inject
    # an arbitrary ORDER BY expression by passing a column name.
    SORT_COLUMNS = {
        "created_at": Issue.created_at,
        "severity": Issue.severity,
        "confidence": Issue.confidence,
        "status": Issue.status,
    }

    async def list_filtered(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
        **filters,
    ) -> list[Issue]:
        column = self.SORT_COLUMNS.get(sort, Issue.created_at)
        direction = column.asc() if order == "asc" else column.desc()
        stmt = self._apply_filters(select(Issue), **filters)
        # Stable tiebreak on id so pages never repeat or skip a row when the
        # sort key ties (e.g. many rows share a created_at).
        stmt = stmt.order_by(direction, Issue.id.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(self, **filters) -> int:
        stmt = self._apply_filters(select(func.count(Issue.id)), **filters)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    def _apply_review_filters(stmt, *, issue_type: str | None = None, severity: int | None = None):
        """Shared WHERE clauses for the review queue's page and its total.

        The queue is always scoped to `review_required` rows; the filters only
        narrow it further.
        """
        stmt = stmt.where(Issue.review_required == True)  # noqa: E712
        if issue_type:
            stmt = stmt.where(Issue.issue_type == issue_type)
        if severity is not None:
            stmt = stmt.where(Issue.severity == severity)
        return stmt

    # Lowest-confidence first is the useful default for a human review queue:
    # the rows the model was least sure about surface at the top.
    REVIEW_SORT_COLUMNS = {
        "created_at": Issue.created_at,
        "confidence": Issue.confidence,
        "severity": Issue.severity,
    }

    async def list_review_queue(
        self,
        skip: int = 0,
        limit: int = 20,
        *,
        issue_type: str | None = None,
        severity: int | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> list[Issue]:
        column = self.REVIEW_SORT_COLUMNS.get(sort, Issue.created_at)
        direction = column.asc() if order == "asc" else column.desc()
        stmt = self._apply_review_filters(select(Issue), issue_type=issue_type, severity=severity)
        # Stable tiebreak on id so paging never repeats or skips a row when the
        # sort key ties (a common case for confidence scores).
        stmt = stmt.order_by(direction, Issue.id.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_review_queue(self, *, issue_type: str | None = None, severity: int | None = None) -> int:
        stmt = self._apply_review_filters(select(func.count(Issue.id)), issue_type=issue_type, severity=severity)
        result = await self.db.execute(stmt)
        return result.scalar_one()

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
