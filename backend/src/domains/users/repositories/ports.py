"""Repository port (interface) for the users domain.

Services depend on this Protocol, not on ``UserRepository`` directly, so a
caller can supply any implementation (the SQLAlchemy one in production, an
in-memory fake in tests) without the service importing the concrete class.
"""

from __future__ import annotations

from typing import Protocol

from src.domains.users.models.user import User


class UserRepositoryPort(Protocol):
    async def get(self, user_id: int) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def create(self, user: User) -> User: ...

    async def list_users(self, skip: int = 0, limit: int = 50) -> list[User]: ...

    async def count(self) -> int: ...

    async def list_filtered(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: str = "",
        role: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> list[User]: ...

    async def count_filtered(self, *, search: str = "", role: str | None = None) -> int: ...
