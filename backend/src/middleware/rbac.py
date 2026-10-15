import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.domains.users.models.user import UserRole
from src.domains.users.rbac import role_at_least

logger = logging.getLogger("civicpulse")

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Lowest role permitted to perform a write at all. Viewers are read-only by
# definition, so they never appear here.
DEFAULT_MIN_ROLE = UserRole.field_worker

# Path prefix -> the *lowest* tier allowed to write there. Every role at or
# above the tier passes (hierarchy semantics, see src/core/rbac.py); anything
# not listed falls back to DEFAULT_MIN_ROLE. Tiers are declared as minimums
# rather than exact allowlists so that higher roles are always included by
# construction and a newly added role cannot be silently locked out.
PATH_MIN_ROLE: tuple[tuple[str, UserRole], ...] = (
    ("/api/v1/admin/", UserRole.admin),
    ("/api/v1/engineers/", UserRole.admin),  # roster maintenance is admin work
    ("/api/v1/ml/", UserRole.admin),
    ("/api/v1/resolution/", UserRole.engineer),  # resolving issues is engineering work
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


def _min_role_for(path: str) -> UserRole:
    for prefix, min_role in PATH_MIN_ROLE:
        if path.startswith(prefix):
            return min_role
    return DEFAULT_MIN_ROLE


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

        minimum = _min_role_for(path)
        if not role_at_least(role, minimum):
            logger.info("RBAC: %s denied for role %s on %s", request.method, role.value, path)
            return _deny(403, "Insufficient permissions.")

        return await call_next(request)
