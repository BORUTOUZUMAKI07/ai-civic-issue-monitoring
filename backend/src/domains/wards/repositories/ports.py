"""Repository port (interface) for the wards domain."""

from __future__ import annotations

from typing import Protocol

from src.domains.wards.models.ward import Ward


class WardRepositoryPort(Protocol):
    async def get(self, ward_id: int) -> Ward | None: ...

    async def get_by_name(self, name: str) -> Ward | None: ...

    async def list_all(self) -> list[Ward]: ...

    async def create(self, ward: Ward) -> Ward: ...
