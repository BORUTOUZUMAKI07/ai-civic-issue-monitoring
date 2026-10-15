"""Repository port (interface) for the resolution domain."""

from __future__ import annotations

from typing import Protocol

from src.domains.resolution.models.resolution import Resolution


class ResolutionRepositoryPort(Protocol):
    async def get(self, resolution_id: int) -> Resolution | None: ...

    async def get_by_issue(self, issue_id: int) -> Resolution | None: ...

    async def create(self, resolution: Resolution) -> Resolution: ...
