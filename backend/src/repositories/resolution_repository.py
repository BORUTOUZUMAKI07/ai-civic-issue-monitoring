from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.resolution import Resolution


class ResolutionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, resolution_id: int) -> Resolution | None:
        result = await self.db.execute(select(Resolution).where(Resolution.id == resolution_id))
        return result.scalar_one_or_none()

    async def get_by_issue(self, issue_id: int) -> Resolution | None:
        result = await self.db.execute(select(Resolution).where(Resolution.issue_id == issue_id))
        return result.scalar_one_or_none()

    async def create(self, resolution: Resolution) -> Resolution:
        self.db.add(resolution)
        await self.db.commit()
        await self.db.refresh(resolution)
        return resolution
