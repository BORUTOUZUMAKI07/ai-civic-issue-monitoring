"""Object-level authorization for issue mutations.

Role checks in ``UserService`` answer "may this caller perform admin work at
all"; the checks here answer the harder question "may this caller change *this*
issue". Keeping both out of the HTTP handlers means a direct service call gets
the same protection as a request through the router.

Status-graph validity is a separate concern and lives in ``status_machine``;
both are always applied, in that order, by ``IssueService``.
"""

from __future__ import annotations

from src.domains.assignments.repositories.ports import AssignmentRepositoryPort
from src.domains.issues.models.issue import Issue, IssueStatus
from src.domains.issues.status_machine import ENGINEER_TARGETS
from src.domains.resolution.repositories.ports import ResolutionRepositoryPort
from src.domains.users.models.user import User, UserRole
from src.domains.users.rbac import role_at_least
from src.shared.errors import ConflictError, ForbiddenError


async def assigned_user_id(issue_id: int, assignment_repo: AssignmentRepositoryPort) -> int | None:
    """The user behind the issue's *latest* assignment, or ``None``.

    ``get_by_issue`` uses ``.first()`` and can return a superseded row, so the
    batched ``latest_by_issue_ids`` primitive is the authoritative lookup.
    """
    mapping = await assignment_repo.latest_by_issue_ids([issue_id])
    entry = mapping.get(issue_id)
    if not entry or entry.get("user_id") is None:
        return None
    return int(entry["user_id"])


async def assert_can_transition_status(
    *,
    issue: Issue,
    target: IssueStatus,
    actor: User,
    assignment_repo: AssignmentRepositoryPort,
) -> None:
    """Only admins or the currently assigned engineer may change an issue."""
    if role_at_least(actor.role, UserRole.admin):
        return

    if actor.role != UserRole.engineer:
        raise ForbiddenError("Only the assigned engineer or an admin can change issue status.")

    owner = await assigned_user_id(issue.id, assignment_repo)
    if owner is None or owner != actor.id:
        raise ForbiddenError("You are not assigned to this issue.")

    if target not in ENGINEER_TARGETS:
        # A state-machine violation is a 409 (InvalidStatusTransition); this is
        # a permission boundary: engineers drive work but never verify/reject.
        # ENGINEER_TARGETS is the same constant the status machine uses, so an
        # added transition cannot silently grant engineers a new target here.
        raise ForbiddenError("Engineers cannot verify or reject an issue.")


async def assert_can_resolve(
    *,
    issue: Issue,
    engineer_id: int,
    assignment_repo: AssignmentRepositoryPort,
    resolution_repo: ResolutionRepositoryPort,
) -> None:
    """The resolving engineer must own the assignment, and only once."""
    assignment = await assignment_repo.get_by_issue(issue.id)
    if assignment is None or assignment.engineer_id != engineer_id:
        raise ForbiddenError("You are not assigned to this issue.")

    if await resolution_repo.get_by_issue(issue.id) is not None:
        raise ConflictError("This issue has already been resolved.")

    # Enforce the lifecycle here too so a direct service call cannot resolve a
    # verified/rejected issue by reaching around the HTTP layer.
    from src.domains.issues.status_machine import assert_transition

    assert_transition(issue.status, IssueStatus.resolved)
