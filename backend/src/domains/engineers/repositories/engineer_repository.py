from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.engineers.models.engineer import Engineer


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

    # Sort keys are an explicit allowlist -> column, so a caller cannot inject
    # an arbitrary ORDER BY expression by passing a column name.
    SORT_COLUMNS = {
        "id": Engineer.id,
        "current_workload": Engineer.current_workload,
        "max_workload": Engineer.max_workload,
        "avg_resolution_hours": Engineer.avg_resolution_hours,
    }

    @staticmethod
    def _apply_filters(
        stmt: "Select[Any]",
        *,
        specialization: str | None = None,
        ward_id: int | None = None,
        available: bool | None = None,
    ) -> "Select[Any]":
        if specialization:
            stmt = stmt.where(Engineer.specialization == specialization)
        if ward_id is not None:
            stmt = stmt.where(Engineer.ward_id == ward_id)
        if available is not None:
            stmt = stmt.where(Engineer.is_available.is_(available))
        return stmt

    async def list_filtered(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        specialization: str | None = None,
        ward_id: int | None = None,
        available: bool | None = None,
        sort: str = "id",
        order: str = "asc",
    ) -> list[Engineer]:
        column = self.SORT_COLUMNS.get(sort, Engineer.id)
        direction = column.desc() if order == "desc" else column.asc()
        stmt = self._apply_filters(
            select(Engineer), specialization=specialization, ward_id=ward_id, available=available
        )
        stmt = stmt.order_by(direction, Engineer.id.asc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self, *, specialization: str | None = None, ward_id: int | None = None, available: bool | None = None
    ) -> int:
        from sqlalchemy import func

        stmt = self._apply_filters(
            select(func.count(Engineer.id)),
            specialization=specialization,
            ward_id=ward_id,
            available=available,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

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
