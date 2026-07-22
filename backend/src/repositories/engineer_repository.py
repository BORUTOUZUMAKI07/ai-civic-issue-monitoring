from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.engineer import Engineer


class EngineerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, engineer_id: int) -> Engineer | None:
        result = await self.db.execute(select(Engineer).where(Engineer.id == engineer_id))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> Engineer | None:
        result = await self.db.execute(select(Engineer).where(Engineer.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_ward(self, ward_id: int) -> list[Engineer]:
        result = await self.db.execute(
            select(Engineer).where(Engineer.ward_id == ward_id, Engineer.is_available.is_(True))
        )
        return list(result.scalars().all())

    async def get_least_loaded(self, ward_id: int) -> Engineer | None:
        result = await self.db.execute(
            select(Engineer)
            .where(Engineer.ward_id == ward_id, Engineer.is_available.is_(True))
            .order_by(Engineer.current_workload.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Engineer]:
        result = await self.db.execute(select(Engineer).order_by(Engineer.id))
        return list(result.scalars().all())

    async def create(self, engineer: Engineer) -> Engineer:
        self.db.add(engineer)
        await self.db.commit()
        await self.db.refresh(engineer)
        return engineer

    async def increment_workload(self, engineer_id: int) -> None:
        engineer = await self.get(engineer_id)
        if engineer:
            engineer.current_workload += 1
            await self.db.commit()

    async def decrement_workload(self, engineer_id: int) -> None:
        engineer = await self.get(engineer_id)
        if engineer and engineer.current_workload > 0:
            engineer.current_workload -= 1
            await self.db.commit()
