from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.engineer_repository import EngineerRepository


class EngineerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.engineer_repo = EngineerRepository(db)

    async def list_engineers(self):
        return await self.engineer_repo.list_all()

    async def get_engineer(self, engineer_id: int):
        return await self.engineer_repo.get(engineer_id)
