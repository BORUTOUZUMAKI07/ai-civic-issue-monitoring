from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ward import Ward


class WardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, ward_id: int) -> Ward | None:
        result = await self.db.execute(select(Ward).where(Ward.id == ward_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Ward | None:
        result = await self.db.execute(select(Ward).where(Ward.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Ward]:
        result = await self.db.execute(select(Ward).order_by(Ward.id))
        return list(result.scalars().all())

    async def create(self, ward: Ward) -> Ward:
        self.db.add(ward)
        await self.db.commit()
        await self.db.refresh(ward)
        return ward
