from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.wards.repositories.ports import WardRepositoryPort
from src.domains.wards.repositories.ward_repository import WardRepository


class WardService:
    def __init__(self, db: AsyncSession, *, ward_repo: WardRepositoryPort | None = None):
        self.db = db
        self.ward_repo: WardRepositoryPort = ward_repo or WardRepository(db)

    async def list_wards(self):
        return await self.ward_repo.list_all()

    async def get_ward(self, ward_id: int):
        return await self.ward_repo.get(ward_id)
