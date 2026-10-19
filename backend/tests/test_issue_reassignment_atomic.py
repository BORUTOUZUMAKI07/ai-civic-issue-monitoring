"""Reassignment must be a single transaction.

``IssueService.assign_issue_to_engineer`` supersedes the outgoing assignment:
it moves one engineer's workload down, the other's up, deletes the old
assignment row and inserts the new one. The old repository helpers
(``increment_workload`` / workload decrement / ``create``) each committed on
their own, so a failure part-way through left the issue unassigned while both
workload counters had already been persisted — a roster that stayed wrong
forever. This test injects a failure at the final flush and asserts nothing was
committed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import delete, or_

from src.core.database import AsyncSessionLocal

# Deliberately clear of the ids other tests pin (test_engineers_me uses 9101/9102).
_REPORTER_ID = 93000
_ENGINEER_A_ID = 93001
_ENGINEER_B_ID = 93002
_ISSUE_ID = 93000


async def _seed() -> None:
    """Reset the fixtures this test needs to a known state, then insert them.

    The suite runs against a single session-scoped DB, so each test starts by
    clearing the rows it owns rather than relying on execution order.
    """
    from src.domains.assignments.models.assignment import Assignment, AssignmentStatus
    from src.domains.engineers.models.engineer import Engineer
    from src.domains.issues.models.issue import Issue, IssueStatus, IssueType
    from src.domains.users.models.user import User, UserRole

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Assignment).where(Assignment.issue_id == _ISSUE_ID))
        await session.execute(delete(Issue).where(Issue.id == _ISSUE_ID))
        await session.execute(
            delete(Engineer).where(
                or_(
                    Engineer.id.in_([_ENGINEER_A_ID, _ENGINEER_B_ID]),
                    Engineer.user_id.in_([_ENGINEER_A_ID, _ENGINEER_B_ID]),
                )
            )
        )
        for user in (
            User(id=_REPORTER_ID, email="rep@example.test", password_hash="x", full_name="Reporter", role=UserRole.field_worker, is_active=True),
            User(id=_ENGINEER_A_ID, email="eng-a@example.test", password_hash="x", full_name="Engineer A", role=UserRole.engineer, is_active=True),
            User(id=_ENGINEER_B_ID, email="eng-b@example.test", password_hash="x", full_name="Engineer B", role=UserRole.engineer, is_active=True),
        ):
            await session.merge(user)
        await session.commit()

        session.add_all(
            [
                Engineer(id=_ENGINEER_A_ID, user_id=_ENGINEER_A_ID, ward_id=7, specialization="roads", current_workload=2, max_workload=10, is_available=True),
                Engineer(id=_ENGINEER_B_ID, user_id=_ENGINEER_B_ID, ward_id=7, specialization="roads", current_workload=1, max_workload=10, is_available=True),
                Issue(
                    id=_ISSUE_ID,
                    issue_type=IssueType.pothole,
                    confidence=0.9,
                    severity=4,
                    status=IssueStatus.assigned,
                    latitude=22.3,
                    longitude=73.1,
                    description="already assigned",
                    image_url="/uploads/issues/seed.jpg",
                    review_required=False,
                    ward_id=7,
                    reporter_id=_REPORTER_ID,
                ),
                Assignment(
                    id=_ISSUE_ID,
                    issue_id=_ISSUE_ID,
                    engineer_id=_ENGINEER_A_ID,
                    status=AssignmentStatus.pending,
                    sla_deadline=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_reassignment_rolls_back_on_failure(db_engine) -> None:
    from src.domains.assignments.repositories.assignment_repository import AssignmentRepository
    from src.domains.engineers.models.engineer import Engineer
    from src.domains.issues.models.issue import Issue
    from src.domains.issues.services.issue_service import IssueService

    await _seed()

    async with AsyncSessionLocal() as session:
        issue = await session.get(Issue, _ISSUE_ID)
        service = IssueService(session)

        # Fail at the point the new assignment would be added to the session —
        # i.e. after the outgoing assignment's delete and the workload deltas,
        # but before the single commit that would make them durable.
        with patch.object(session, "add", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                await service.assign_issue_to_engineer(issue, _ENGINEER_B_ID)
        await session.rollback()

    async with AsyncSessionLocal() as verify:
        engineer_a = await verify.get(Engineer, _ENGINEER_A_ID)
        engineer_b = await verify.get(Engineer, _ENGINEER_B_ID)
        assignment = await AssignmentRepository(verify).get_by_issue(_ISSUE_ID)

    assert engineer_a is not None and engineer_a.current_workload == 2
    assert engineer_b is not None and engineer_b.current_workload == 1
    assert assignment is not None
    assert assignment.engineer_id == _ENGINEER_A_ID


@pytest.mark.asyncio
async def test_reassignment_moves_assignment_and_workload(db_engine) -> None:
    from src.domains.assignments.repositories.assignment_repository import AssignmentRepository
    from src.domains.engineers.models.engineer import Engineer
    from src.domains.issues.models.issue import Issue
    from src.domains.issues.services.issue_service import IssueService

    await _seed()

    async with AsyncSessionLocal() as session:
        issue = await session.get(Issue, _ISSUE_ID)
        service = IssueService(session)
        await service.assign_issue_to_engineer(issue, _ENGINEER_B_ID)

    async with AsyncSessionLocal() as verify:
        engineer_a = await verify.get(Engineer, _ENGINEER_A_ID)
        engineer_b = await verify.get(Engineer, _ENGINEER_B_ID)
        assignment = await AssignmentRepository(verify).get_by_issue(_ISSUE_ID)

    assert engineer_a is not None and engineer_a.current_workload == 1
    assert engineer_b is not None and engineer_b.current_workload == 2
    assert assignment is not None
    assert assignment.engineer_id == _ENGINEER_B_ID
