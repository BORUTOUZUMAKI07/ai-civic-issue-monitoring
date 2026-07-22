from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.ward_repository import WardRepository


class WardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ward_repo = WardRepository(db)

    async def list_wards(self):
        return await self.ward_repo.list_all()

    async def get_ward(self, ward_id: int):
        return await self.ward_repo.get(ward_id)
