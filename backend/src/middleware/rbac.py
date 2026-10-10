import logging
from typing import Iterable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.models.user import UserRole

logger = logging.getLogger("civicpulse")

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ROLE_HIERARCHY = {
    UserRole.super_admin: 5,
    UserRole.admin: 4,
    UserRole.engineer: 3,
    UserRole.field_worker: 2,
    UserRole.viewer: 1,
}

# Lowest role permitted to perform a write at all. Viewers are read-only by
# definition, so they never appear here.
DEFAULT_MIN_ROLE = UserRole.field_worker

# Path prefix -> the set of roles allowed to write there. Anything not listed
# falls back to DEFAULT_MIN_ROLE. Each entry is an explicit allowlist rather
# than a blacklist so a newly added route fails closed to the most conservative
# rule until somebody reasons about it.
PATH_ROLE_RULES: tuple[tuple[str, frozenset[UserRole]], ...] = (
    ("/api/v1/admin/", frozenset({UserRole.super_admin, UserRole.admin})),
    ("/api/v1/engineers/", frozenset({UserRole.super_admin, UserRole.admin})),
    ("/api/v1/ml/", frozenset({UserRole.super_admin, UserRole.admin})),
)

# Paths that legitimately accept unauthenticated writes. Everything under
# /auth/ (login, register, refresh, logout, password reset, 2FA bootstrap) plus
# the health probe. Matches by prefix so /api/v1/auth/2fa/verify is included.
UNAUTHENTICATED_PREFIXES = ("/api/v1/auth/",)


def _extract_token(request: Request) -> str | None:
    """Pull the access token from either transport.

    The API accepts the same JWT as a ``Bearer`` header *and* as the
    ``access_token`` cookie (see ``core/deps.py``), so this middleware has to
    consider both. Reading only the header — as an earlier version did — meant
    every cookie-authenticated request skipped authorization entirely: the two
    transports were guarded by different code paths and the cookie path won by
    doing nothing.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    return None


def _deny(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "error_code": _code(status_code)})


def _code(status_code: int) -> str:
    return "UNAUTHENTICATED" if status_code == 401 else "FORBIDDEN"


def _allowed_roles_for(path: str) -> frozenset[UserRole]:
    for prefix, roles in PATH_ROLE_RULES:
        if path.startswith(prefix):
            return roles
    return frozenset({DEFAULT_MIN_ROLE})


class RBACMiddleware(BaseHTTPMiddleware):
    """Authorization for write requests under ``/api/v1/``.

    Fails **closed**: a missing, malformed, expired or unparseable credential
    is a 401, and an unreadable role claim is a 401. An earlier version
    returned early when no ``Bearer`` header was present (so cookie sessions
    bypassed every check) and swallowed all exceptions before falling through
    to ``call_next`` (so a bad token was treated as authorization), which made
    the middleware advisory rather than enforcing.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in WRITE_METHODS or not path.startswith("/api/v1/"):
            return await call_next(request)

        # Unauthenticated auth flows must still work, and so must everything
        # we have not explicitly decided needs a role.
        if path.startswith(UNAUTHENTICATED_PREFIXES):
            return await call_next(request)

        token = _extract_token(request)
        if not token:
            return _deny(401, "Not authenticated.")

        # Imported lazily so the middleware module stays importable without
        # dragging in the whole auth stack at process start.
        from src.core.security import decode_token

        try:
            payload = decode_token(token)
        except Exception as exc:
            # An expired or tampered token is a 401, not a pass-through.
            logger.info("RBAC: rejecting unusable token (%s)", type(exc).__name__)
            return _deny(401, "Invalid or expired credentials.")

        if payload.get("type") != "access":
            return _deny(401, "Invalid or expired credentials.")

        try:
            role = UserRole(payload.get("role", ""))
        except ValueError:
            # An unknown role claim is not a role we can authorize.
            logger.warning("RBAC: token carried an unknown role %r", payload.get("role"))
            return _deny(401, "Invalid or expired credentials.")

        allowed = _allowed_roles_for(path)
        if role not in allowed:
            logger.info("RBAC: %s denied for role %s on %s", request.method, role.value, path)
            return _deny(403, "Insufficient permissions.")

        return await call_next(request)


def roles_allowed(*roles: UserRole) -> Iterable[UserRole]:
    """Small helper for route handlers that need an extra role check inline."""
    return frozenset(roles)
