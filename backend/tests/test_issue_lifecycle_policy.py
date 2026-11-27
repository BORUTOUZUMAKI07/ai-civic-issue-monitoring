"""Issue lifecycle and object-level authorization tests.

The status graph and the "who may touch this issue" rules used to be split
between the router, the service and the frontend. These tests pin both down at
the layer that enforces them, so a new write path cannot quietly bypass either
gate.
"""

from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from src.core.database import AsyncSessionLocal
from src.domains.engineers.models.engineer import Engineer
from src.domains.issues.models.issue import Issue, IssueStatus, IssueType
from src.domains.issues.policy import assert_can_resolve, assert_can_transition_status
from src.domains.issues.services.issue_service import IssueService
from src.domains.issues.status_machine import (
    can_transition,
    engineer_may_transition,
)
from src.domains.users.models.user import User, UserRole
from src.shared.errors import ConflictError, ForbiddenError, InvalidStatusTransition

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _issue(status: IssueStatus = IssueStatus.assigned, issue_id: int = 1) -> Issue:
    return Issue(
        id=issue_id,
        issue_type=IssueType.pothole,
        confidence=0.9,
        severity=4,
        status=status,
        latitude=12.3,
        longitude=45.6,
        description="test",
        image_url="/uploads/issues/a.jpg",
        review_required=False,
        ward_id=7,
        reporter_id=99,
        created_at=NOW,
    )


def _user(user_id: int, role: UserRole) -> User:
    return User(
        id=user_id,
        email=f"lifecycle-{user_id}@example.test",
        password_hash="x",
        full_name="Lifecycle Test",
        role=role,
    )


class _AssignmentRepo:
    def __init__(self, *, user_id: int | None = None, engineer_id: int | None = None) -> None:
        self.user_id = user_id
        self.engineer_id = engineer_id

    async def latest_by_issue_ids(self, issue_ids: list[int]) -> dict[int, dict]:
        if self.user_id is None:
            return {}
        return {i: {"user_id": self.user_id, "full_name": "Engineer"} for i in issue_ids}

    async def get_by_issue(self, issue_id: int) -> object | None:
        if self.engineer_id is None:
            return None
        return SimpleNamespace(engineer_id=self.engineer_id)


class _ResolutionRepo:
    def __init__(self, *, exists: bool = False) -> None:
        self.exists = exists

    async def get_by_issue(self, issue_id: int) -> object | None:
        return object() if self.exists else None


class _Db:
    def __init__(self, issue: Issue) -> None:
        self.issue = issue

    def add(self, value: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, value: object) -> None:
        return None


class _IssueRepo:
    def __init__(self, issue: Issue) -> None:
        self.issue = issue

    async def get(self, issue_id: int) -> Issue | None:
        return self.issue if issue_id == self.issue.id else None

    async def update_status(self, issue_id: int, status: IssueStatus) -> Issue | None:
        self.issue.status = status
        return self.issue


# ── transition graph ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IssueStatus.reported, IssueStatus.assigned),
        (IssueStatus.assigned, IssueStatus.in_progress),
        (IssueStatus.assigned, IssueStatus.resolved),
        (IssueStatus.in_progress, IssueStatus.resolved),
        (IssueStatus.resolved, IssueStatus.verified),
        (IssueStatus.reported, IssueStatus.rejected),
    ],
)
def test_forward_edges_are_allowed(current: IssueStatus, target: IssueStatus) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IssueStatus.reported, IssueStatus.verified),
        (IssueStatus.in_progress, IssueStatus.assigned),
        (IssueStatus.resolved, IssueStatus.in_progress),
        (IssueStatus.verified, IssueStatus.resolved),
        (IssueStatus.rejected, IssueStatus.assigned),
    ],
)
def test_backwards_jumps_and_terminal_states_are_rejected(
    current: IssueStatus, target: IssueStatus
) -> None:
    assert not can_transition(current, target)


def test_engineer_targets_are_limited_to_work_steps() -> None:
    assert engineer_may_transition(IssueStatus.assigned, IssueStatus.in_progress)
    assert engineer_may_transition(IssueStatus.in_progress, IssueStatus.resolved)
    assert not engineer_may_transition(IssueStatus.resolved, IssueStatus.verified)
    assert not engineer_may_transition(IssueStatus.assigned, IssueStatus.rejected)


# ── object-level policy ──────────────────────────────────────────────────────


async def test_admin_can_transition_any_valid_edge() -> None:
    issue = _issue()
    await assert_can_transition_status(
        issue=issue,
        target=IssueStatus.verified,
        actor=_user(2, UserRole.admin),
        assignment_repo=_AssignmentRepo(),
    )


async def test_assigned_engineer_can_transition_their_issue() -> None:
    await assert_can_transition_status(
        issue=_issue(),
        target=IssueStatus.in_progress,
        actor=_user(10, UserRole.engineer),
        assignment_repo=_AssignmentRepo(user_id=10),
    )


async def test_unassigned_engineer_cannot_transition() -> None:
    with pytest.raises(ForbiddenError, match="not assigned"):
        await assert_can_transition_status(
            issue=_issue(),
            target=IssueStatus.in_progress,
            actor=_user(11, UserRole.engineer),
            assignment_repo=_AssignmentRepo(user_id=10),
        )


async def test_engineer_cannot_verify_or_reject() -> None:
    with pytest.raises(ForbiddenError, match="cannot verify or reject"):
        await assert_can_transition_status(
            issue=_issue(IssueStatus.resolved),
            target=IssueStatus.verified,
            actor=_user(10, UserRole.engineer),
            assignment_repo=_AssignmentRepo(user_id=10),
        )


async def test_field_worker_cannot_transition() -> None:
    with pytest.raises(ForbiddenError, match="Only the assigned engineer"):
        await assert_can_transition_status(
            issue=_issue(),
            target=IssueStatus.in_progress,
            actor=_user(3, UserRole.field_worker),
            assignment_repo=_AssignmentRepo(user_id=3),
        )


async def test_update_status_rejects_invalid_edge_even_for_admin() -> None:
    issue = _issue(IssueStatus.verified)
    service = IssueService(
        _Db(issue),
        issue_repo=_IssueRepo(issue),
        assignment_repo=_AssignmentRepo(),
    )
    with pytest.raises(InvalidStatusTransition):
        await service.update_status(issue.id, IssueStatus.in_progress.value, _user(2, UserRole.admin))


async def test_generic_status_patch_cannot_resolve_without_a_resolution() -> None:
    issue = _issue(IssueStatus.in_progress)
    service = IssueService(
        _Db(issue),
        issue_repo=_IssueRepo(issue),
        assignment_repo=_AssignmentRepo(user_id=10),
    )
    with pytest.raises(ConflictError, match="resolution endpoint"):
        await service.update_status(issue.id, IssueStatus.resolved.value, _user(10, UserRole.engineer))
    assert issue.status is IssueStatus.in_progress


async def test_only_owning_engineer_may_resolve() -> None:
    with pytest.raises(ForbiddenError, match="not assigned"):
        await assert_can_resolve(
            issue=_issue(IssueStatus.in_progress),
            engineer_id=11,
            assignment_repo=_AssignmentRepo(engineer_id=10),
            resolution_repo=_ResolutionRepo(),
        )


async def test_duplicate_resolution_is_a_conflict() -> None:
    with pytest.raises(ConflictError, match="already been resolved"):
        await assert_can_resolve(
            issue=_issue(IssueStatus.in_progress),
            engineer_id=10,
            assignment_repo=_AssignmentRepo(engineer_id=10),
            resolution_repo=_ResolutionRepo(exists=True),
        )


async def test_resolution_rejects_terminal_issue() -> None:
    with pytest.raises(InvalidStatusTransition):
        await assert_can_resolve(
            issue=_issue(IssueStatus.rejected),
            engineer_id=10,
            assignment_repo=_AssignmentRepo(engineer_id=10),
            resolution_repo=_ResolutionRepo(),
        )


async def test_resolution_write_is_single_transaction() -> None:
    issue = _issue(IssueStatus.in_progress)
    service = IssueService(
        _Db(issue),
        issue_repo=_IssueRepo(issue),
        assignment_repo=_AssignmentRepo(engineer_id=10),
        resolution_repo=_ResolutionRepo(),
    )
    committed = 0

    async def commit() -> None:
        nonlocal committed
        committed += 1

    service.db.commit = commit  # type: ignore[method-assign]
    result = await service.create_resolution(issue.id, 10, "/uploads/resolutions/a.jpg")
    assert result.issue_id == issue.id
    assert issue.status is IssueStatus.resolved
    assert issue.resolved_at is not None
    assert committed == 1


# ── HTTP boundary: PATCH /issues/{id}/status ────────────────────────────────

_ISSUE_ID = 94000


async def _seed_issue(status: IssueStatus = IssueStatus.reported) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.get(Issue, _ISSUE_ID)
        if existing is not None:
            await session.delete(existing)
            await session.commit()
        session.add(
            Issue(
                id=_ISSUE_ID,
                issue_type=IssueType.pothole,
                confidence=0.9,
                severity=4,
                status=status,
                latitude=12.3,
                longitude=45.6,
                description="boundary test",
                image_url="/uploads/issues/a.jpg",
                review_required=False,
                ward_id=7,
                reporter_id=1,
            )
        )
        await session.commit()


async def _cleanup_issue() -> None:
    async with AsyncSessionLocal() as session:
        issue = await session.get(Issue, _ISSUE_ID)
        if issue is not None:
            await session.delete(issue)
            await session.commit()


@pytest.mark.asyncio
async def test_status_patch_denies_field_worker_and_allows_admin(
    client, auth_headers, admin_headers
) -> None:
    from src.domains.users.models.user import User as UserModel

    async with AsyncSessionLocal() as session:
        reporter = await session.get(UserModel, 1)
        assert reporter is not None and reporter.role is UserRole.field_worker

    await _seed_issue()
    try:
        denied = await client.patch(
            f"/api/v1/issues/{_ISSUE_ID}/status",
            json={"status": "assigned"},
            headers=auth_headers,
        )
        assert denied.status_code == 403

        allowed = await client.patch(
            f"/api/v1/issues/{_ISSUE_ID}/status",
            json={"status": "assigned"},
            headers=admin_headers,
        )
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "assigned"

        # Even a valid assigned -> resolved edge cannot be taken through the
        # generic status route: resolution needs proof and one atomic write.
        bypass = await client.patch(
            f"/api/v1/issues/{_ISSUE_ID}/status",
            json={"status": "resolved"},
            headers=admin_headers,
        )
        assert bypass.status_code == 409
        assert "resolution endpoint" in bypass.json()["detail"]

        conflict = await client.patch(
            f"/api/v1/issues/{_ISSUE_ID}/status",
            json={"status": "verified"},
            headers=admin_headers,
        )
        assert conflict.status_code == 409
    finally:
        await _cleanup_issue()


@pytest.mark.asyncio
async def test_assign_body_is_typed(client, admin_headers) -> None:
    await _seed_issue()
    try:
        bad = await client.post(
            f"/api/v1/issues/{_ISSUE_ID}/assign",
            json={"engineer_id": 0},
            headers=admin_headers,
        )
        assert bad.status_code == 422

        malformed = await client.post(
            f"/api/v1/issues/{_ISSUE_ID}/assign",
            json={},
            headers=admin_headers,
        )
        assert malformed.status_code == 422

        missing_engineer = await client.post(
            f"/api/v1/issues/{_ISSUE_ID}/assign",
            json={"engineer_id": 987654},
            headers=admin_headers,
        )
        assert missing_engineer.status_code == 400
    finally:
        await _cleanup_issue()


@pytest.mark.asyncio
async def test_ward_id_is_derived_from_seeded_wards() -> None:
    from src.domains.wards.models.ward import Ward

    class _WardRepo:
        async def list_all(self) -> list[Ward]:
            return [
                Ward(id=12, name="Ward 12", polygon={}, center_lat=1.0, center_lon=2.0),
                Ward(id=4, name="Ward 4", polygon={}, center_lat=1.0, center_lon=2.0),
            ]

    from src.domains.users.services.user_service import UserService

    class _DbWard:
        def __init__(self) -> None:
            self.added: list[Engineer] = []

        def add(self, value: Engineer) -> None:
            self.added.append(value)

        async def commit(self) -> None:
            return None

        async def refresh(self, value: object) -> None:
            return None

    class _UserRepo:
        async def get(self, user_id: int) -> User | None:
            return _user(user_id, UserRole.field_worker)

    class _EngineerRepo:
        async def get_by_user_id(self, user_id: int) -> Engineer | None:
            return None

    db = _DbWard()
    service = UserService(
        db,  # type: ignore[arg-type]
        user_repo=_UserRepo(),  # type: ignore[arg-type]
        engineer_repo=_EngineerRepo(),  # type: ignore[arg-type]
        ward_repo=_WardRepo(),  # type: ignore[arg-type]
    )
    result = await service.change_role(_user(2, UserRole.super_admin), 50, "engineer")
    assert result.role is UserRole.engineer
    assert db.added[0].ward_id == 4
