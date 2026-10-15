"""Role hierarchy for CivicPulse authorization.

A single source of truth for role ordering. Roles are *ordered*, so access
rules can say "at least engineer" instead of hand-listing every equal-or-higher
role — otherwise adding a role (or checking a new endpoint) silently forgets
tiers. ``super_admin`` outranks ``admin``, which outranks ``engineer``, which
outranks ``field_worker``, which outranks the read-only ``viewer``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.users.models.user import UserRole
from src.shared.errors import ForbiddenError

if TYPE_CHECKING:
    from src.domains.users.models.user import User

ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.super_admin: 5,
    UserRole.admin: 4,
    UserRole.engineer: 3,
    UserRole.field_worker: 2,
    UserRole.viewer: 1,
}


def role_at_least(role: UserRole, minimum: UserRole) -> bool:
    """True when ``role`` sits at or above ``minimum`` in the hierarchy.

    Unknown roles sort below everything (``0``), so a new or corrupt role
    claim fails closed rather than being treated as privileged.
    """
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY.get(minimum, 0)


def require_admin(user: User) -> None:
    """Raise ``403`` unless ``user`` is at or above :data:`UserRole.admin`.

    One implementation for every admin-gated endpoint; the old duplicate
    ``_require_admin`` helpers in the admin and issues routers were the same
    five lines with the same message.
    """
    if not role_at_least(user.role, UserRole.admin):
        raise ForbiddenError("Admin access required.")
