from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, user_id: int) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def list_users(self, skip: int = 0, limit: int = 50) -> list[User]:
        result = await self.db.execute(select(User).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self.db.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def list_filtered(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: str = "",
        role: str | None = None,
    ) -> list[User]:
        """Page of users matching an optional free-text search and role filter.

        The WHERE clauses are shared with :meth:`count_filtered` so the listed
        rows and the reported total can never drift apart.
        """
        stmt = self._filtered(select(User), search=search, role=role)
        stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(self, *, search: str = "", role: str | None = None) -> int:
        result = await self.db.execute(self._filtered(select(func.count(User.id)), search=search, role=role))
        return int(result.scalar_one())

    @staticmethod
    def _filtered(stmt: Select[Any], *, search: str = "", role: str | None = None) -> Select[Any]:
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(User.email.ilike(pattern) | User.full_name.ilike(pattern))
        if role:
            stmt = stmt.where(User.role == role)
        return stmt
