"""Unit tests for domain services against in-memory fakes.

The DDD refactor gave every service an optional constructor injection point
for its repositories (``*_repo=`` keyword args typed with the domain's
``RepositoryPort`` Protocol). These tests pin that seam down: each service
method that only orchestrates a repository is exercised with a fake, with no
database and no HTTP in the loop.

The pure mappers (:meth:`IssueResponse.from_issue`,
:meth:`EngineerResponse.from_engineer`) and the shared
:func:`require_admin` guard are covered here too — they carry behavior
(substituting a ``None`` assignment, stringifying the assignee id, refusing
roles below admin) that is easy to break while moving code around.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domains.assignments.models.assignment import Assignment, AssignmentStatus
from src.domains.engineers.models.engineer import Engineer
from src.domains.engineers.schemas import EngineerResponse
from src.domains.engineers.services.engineer_service import EngineerService
from src.domains.issues.models.issue import Issue, IssueStatus, IssueType
from src.domains.issues.repositories.issue_repository import IssueRepository
from src.domains.issues.schemas import IssueResponse
from src.domains.issues.services.issue_service import IssueService
from src.domains.users.models.user import User, UserRole
from src.domains.users.rbac import require_admin
from src.domains.users.repositories.user_repository import UserRepository
from src.domains.users.services.user_service import UserService
from src.shared.errors import BadRequestError, ForbiddenError, NotFoundError

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


# ── fixtures / helpers ────────────────────────────────────────────────────────


def _issue(**overrides: object) -> Issue:
    values: dict = {
        "id": 1,
        "issue_type": IssueType.pothole,
        "confidence": 0.91,
        "severity": 4,
        "status": IssueStatus.reported,
        "latitude": 12.34,
        "longitude": 56.78,
        "description": "broken road",
        "image_url": "https://example.test/a.jpg",
        "review_required": True,
        "ward_id": 7,
        "reporter_id": 3,
        "created_at": NOW,
    }
    values.update(overrides)
    return Issue(**values)


def _engineer(**overrides: object) -> Engineer:
    values: dict = {
        "id": 10,
        "user_id": 20,
        "ward_id": 7,
        "specialization": "roads",
        "current_workload": 2,
        "max_workload": 10,
        "is_available": True,
        "avg_resolution_hours": 5.5,
    }
    values.update(overrides)
    return Engineer(**values)


def _user(**overrides: object) -> User:
    values: dict = {
        "id": 1,
        "email": "a@example.test",
        "password_hash": "x",
        "full_name": "Ada Engineer",
        "role": UserRole.field_worker,
    }
    values.update(overrides)
    return User(**values)


def _assignment(**overrides: object) -> Assignment:
    values: dict = {
        "id": 99,
        "issue_id": 1,
        "engineer_id": 10,
        "status": AssignmentStatus.pending,
        "assigned_at": NOW,
        "sla_deadline": NOW,
    }
    values.update(overrides)
    return Assignment(**values)


class _FakeIssueRepo:
    def __init__(self, *, queue: list[Issue] | None = None, total: int = 0) -> None:
        self.queue = queue or []
        self.total = total
        self.calls: list[tuple[str, dict]] = []

    async def list_review_queue(
        self,
        skip: int = 0,
        limit: int = 20,
        *,
        issue_type: str | None = None,
        severity: int | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> list[Issue]:
        self.calls.append(
            (
                "list_review_queue",
                {"skip": skip, "limit": limit, "issue_type": issue_type, "severity": severity, "sort": sort, "order": order},
            )
        )
        return self.queue

    async def count_review_queue(
        self, *, issue_type: str | None = None, severity: int | None = None
    ) -> int:
        self.calls.append(("count_review_queue", {"issue_type": issue_type, "severity": severity}))
        return self.total


class _FakeAssignmentRepo:
    def __init__(self, *, mapping: dict[int, dict] | None = None, rows: list | None = None) -> None:
        self.mapping = mapping or {}
        self.rows = rows or []
        self.seen_ids: list[int] = []

    async def latest_by_issue_ids(self, issue_ids: list[int]) -> dict[int, dict]:
        self.seen_ids = issue_ids
        return {i: self.mapping[i] for i in issue_ids if i in self.mapping}

    async def list_by_engineer_with_issue(self, engineer_id: int) -> list:
        return self.rows


class _FakeUserRepo:
    def __init__(self, *, users: list[User] | None = None, total: int = 0) -> None:
        self.users = users or []
        self.total = total
        self.filters: dict = {}

    async def list_filtered(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: str = "",
        role: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ):
        self.filters = {
            "skip": skip,
            "limit": limit,
            "search": search,
            "role": role,
            "sort": sort,
            "order": order,
        }
        return self.users

    async def count_filtered(self, *, search: str = "", role: str | None = None) -> int:
        return self.total


class _FakeEngineerRepo:
    def __init__(self, *, by_user: dict[int, Engineer] | None = None) -> None:
        self.by_user = by_user or {}

    async def get_by_user_id(self, user_id: int) -> Engineer | None:
        return self.by_user.get(user_id)


# ── pure mappers ──────────────────────────────────────────────────────────────


def test_issue_response_from_issue_without_assignment() -> None:
    response = IssueResponse.from_issue(_issue())

    assert response.id == 1
    assert response.issue_type == "pothole"
    assert response.status == "reported"
    assert response.created_at == NOW.isoformat()
    assert response.assigned_to is None
    assert response.engineer_name is None


def test_issue_response_from_issue_with_assignment_stringifies_assignee() -> None:
    response = IssueResponse.from_issue(_issue(), {"user_id": 42, "full_name": "Bob"})

    assert response.assigned_to == "42"
    assert response.engineer_name == "Bob"


def test_engineer_response_from_engineer_copies_fields() -> None:
    response = EngineerResponse.from_engineer(_engineer())

    assert (response.id, response.user_id, response.ward_id) == (10, 20, 7)
    assert response.specialization == "roads"
    assert response.avg_resolution_hours == 5.5


# ── users.rbac.require_admin ──────────────────────────────────────────────────


def test_require_admin_allows_admin_and_super_admin() -> None:
    require_admin(_user(role=UserRole.admin))
    require_admin(_user(role=UserRole.super_admin))


def test_require_admin_rejects_below_admin() -> None:
    for role in (UserRole.engineer, UserRole.field_worker, UserRole.viewer):
        with pytest.raises(ForbiddenError):
            require_admin(_user(role=role))


# ── IssueService ──────────────────────────────────────────────────────────────


async def test_issue_service_list_review_queue_uses_injected_repo() -> None:
    repo = _FakeIssueRepo(queue=[_issue(), _issue(id=2)], total=5)
    service = IssueService(db=None, issue_repo=repo, ward_repo=object(), engineer_repo=object())

    issues, total = await service.list_review_queue(skip=10, limit=2)

    assert total == 5
    assert [i.id for i in issues] == [1, 2]
    assert (
        "list_review_queue",
        {"skip": 10, "limit": 2, "issue_type": None, "severity": None, "sort": "created_at", "order": "desc"},
    ) in repo.calls


async def test_issue_service_get_assignment_map_delegates() -> None:
    repo = _FakeAssignmentRepo(mapping={1: {"user_id": 9, "full_name": "Eve"}})
    service = IssueService(db=None, assignment_repo=repo, ward_repo=object())

    result = await service.get_assignment_map([1, 2])

    assert result == {1: {"user_id": 9, "full_name": "Eve"}}
    assert repo.seen_ids == [1, 2]


# ── UserService ───────────────────────────────────────────────────────────────


async def test_user_service_list_users_uses_injected_repo() -> None:
    repo = _FakeUserRepo(users=[_user(id=1), _user(id=2)], total=2)
    service = UserService(db=None, user_repo=repo, engineer_repo=object(), assignment_repo=object())

    users, total = await service.list_users(skip=5, limit=10, search="ada", role="admin")

    assert total == 2
    assert [u.id for u in users] == [1, 2]
    assert repo.filters == {
        "skip": 5,
        "limit": 10,
        "search": "ada",
        "role": "admin",
        "sort": "created_at",
        "order": "desc",
    }


# ── EngineerService ───────────────────────────────────────────────────────────


async def test_engineer_service_get_my_profile_returns_engineer() -> None:
    engineer = _engineer(user_id=20)
    service = EngineerService(db=None, engineer_repo=_FakeEngineerRepo(by_user={20: engineer}))

    assert await service.get_my_profile(20) is engineer


async def test_engineer_service_get_my_profile_missing_raises() -> None:
    service = EngineerService(db=None, engineer_repo=_FakeEngineerRepo())

    with pytest.raises(NotFoundError):
        await service.get_my_profile(999)


async def test_engineer_service_list_my_assignments_maps_rows() -> None:
    assignment = _assignment()
    issue = _issue(description=None)
    service = EngineerService(
        db=None,
        engineer_repo=_FakeEngineerRepo(by_user={20: _engineer()}),
        assignment_repo=_FakeAssignmentRepo(rows=[(assignment, issue)]),
    )

    rows = await service.list_my_assignments(20)

    assert rows == [
        {
            "assignment_id": 99,
            "status": "pending",
            "assigned_at": NOW.isoformat(),
            "sla_deadline": NOW.isoformat(),
            "issue_id": 1,
            "issue_type": "pothole",
            "severity": 4,
            "issue_status": "reported",
            "latitude": 12.34,
            "longitude": 56.78,
            "description": None,
            "image_url": "https://example.test/a.jpg",
            "ward_id": 7,
            "created_at": NOW.isoformat(),
        }
    ]


async def test_engineer_service_list_my_assignments_without_profile_raises() -> None:
    service = EngineerService(db=None, engineer_repo=_FakeEngineerRepo())

    with pytest.raises(BadRequestError):
        await service.list_my_assignments(999)


# ── default wiring (injection is optional) ────────────────────────────────────


def test_services_default_to_concrete_repositories_when_not_injected() -> None:
    issue_service = IssueService(db=object())
    assert isinstance(issue_service.issue_repo, IssueRepository)

    user_service = UserService(db=object())
    assert isinstance(user_service.user_repo, UserRepository)
