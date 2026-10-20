"""Repository port (interface) for the issues domain."""

from __future__ import annotations

from typing import Any, Protocol

from src.domains.issues.models.issue import Issue, IssueStatus


class IssueRepositoryPort(Protocol):
    async def get(self, issue_id: int) -> Issue | None: ...

    async def create(self, issue: Issue) -> Issue: ...

    async def update_status(self, issue_id: int, status: IssueStatus) -> Issue | None: ...

    async def list_by_ward(self, ward_id: int, skip: int = 0, limit: int = 20) -> list[Issue]: ...

    async def list_by_status(self, status: IssueStatus, skip: int = 0, limit: int = 20) -> list[Issue]: ...

    async def list_all(self, skip: int = 0, limit: int = 20) -> list[Issue]: ...

    async def list_filtered(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
        status: str | None = None,
        issue_type: str | None = None,
        severity: int | None = None,
        ward_id: int | None = None,
        search: str = "",
    ) -> list[Issue]: ...

    async def count_filtered(
        self,
        *,
        status: str | None = None,
        issue_type: str | None = None,
        severity: int | None = None,
        ward_id: int | None = None,
        search: str = "",
    ) -> int: ...

    async def list_review_queue(
        self,
        skip: int = 0,
        limit: int = 20,
        *,
        issue_type: str | None = None,
        severity: int | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> list[Issue]: ...

    async def count(self) -> int: ...

    async def count_review_queue(self, *, issue_type: str | None = None, severity: int | None = None) -> int: ...

    async def count_by_status(self) -> dict[str, int]: ...

    async def count_by_type(self) -> dict[str, int]: ...

    async def count_by_ward(self) -> list[dict[str, Any]]: ...

    async def get_recent(self, days: int = 30) -> list[Issue]: ...

    async def get_heatmap_points(self) -> list[dict[str, Any]]: ...

    async def commit(self) -> None: ...
