"""Repository port (interface) for the engineers domain."""

from __future__ import annotations

from typing import Protocol

from src.domains.engineers.models.engineer import Engineer


class EngineerRepositoryPort(Protocol):
    async def get(self, engineer_id: int) -> Engineer | None: ...

    async def get_by_user_id(self, user_id: int) -> Engineer | None: ...

    async def get_by_ward(self, ward_id: int) -> list[Engineer]: ...

    async def get_least_loaded(self, ward_id: int) -> Engineer | None: ...

    async def list_all(self) -> list[Engineer]: ...

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
    ) -> list[Engineer]: ...

    async def count_filtered(
        self, *, specialization: str | None = None, ward_id: int | None = None, available: bool | None = None
    ) -> int: ...

    async def create(self, engineer: Engineer) -> Engineer: ...

    async def increment_workload(self, engineer_id: int) -> None: ...
