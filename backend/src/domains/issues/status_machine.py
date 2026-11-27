"""The single source of truth for issue lifecycle transitions.

Every writer of ``Issue.status`` goes through :func:`assert_transition` —
manual PATCH, automatic assignment, admin reassignment and resolution alike.
Keeping the table in one module means there is no second, subtly different
notion of "valid next status" in a route, repository or frontend-only helper.

The lifecycle is forward-only:

    reported -> assigned -> in_progress -> resolved -> verified

``rejected`` is terminal and is reserved for administrative rejection. An
engineer may only move an issue they own, and only as far as ``resolved``;
verification is an administrative act.
"""

from __future__ import annotations

from src.domains.issues.models.issue import IssueStatus
from src.shared.errors import InvalidStatusTransition

ALLOWED_TRANSITIONS: dict[IssueStatus, frozenset[IssueStatus]] = {
    IssueStatus.reported: frozenset({IssueStatus.assigned, IssueStatus.rejected}),
    IssueStatus.assigned: frozenset({IssueStatus.in_progress, IssueStatus.resolved, IssueStatus.rejected}),
    IssueStatus.in_progress: frozenset({IssueStatus.resolved, IssueStatus.rejected}),
    IssueStatus.resolved: frozenset({IssueStatus.verified}),
    IssueStatus.verified: frozenset(),
    IssueStatus.rejected: frozenset(),
}

# An assigned engineer drives work forward but cannot verify or reject it.
ENGINEER_TARGETS: frozenset[IssueStatus] = frozenset({IssueStatus.in_progress, IssueStatus.resolved})


def can_transition(current: IssueStatus, target: IssueStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: IssueStatus, target: IssueStatus) -> None:
    """Raise a 409 when ``current -> target`` is not an allowed lifecycle step."""
    if not can_transition(current, target):
        raise InvalidStatusTransition(current.value, target.value)


def engineer_may_transition(current: IssueStatus, target: IssueStatus) -> bool:
    return can_transition(current, target) and target in ENGINEER_TARGETS
