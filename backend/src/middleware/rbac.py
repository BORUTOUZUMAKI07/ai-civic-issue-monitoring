import logging

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


class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in WRITE_METHODS or not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        if request.url.path.startswith("/api/v1/auth/"):
            return await call_next(request)

        from src.core.security import decode_token

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return await call_next(request)

        try:
            payload = decode_token(auth_header[7:])
            try:
                role = UserRole(payload.get("role", ""))
            except ValueError:
                return await call_next(request)

            user_level = ROLE_HIERARCHY.get(role, 0)

            if request.url.path.startswith("/api/v1/engineers/") and role not in (
                UserRole.admin,
                UserRole.super_admin,
            ):
                if user_level < ROLE_HIERARCHY.get(UserRole.engineer, 3):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Engineer access required.", "error_code": "FORBIDDEN"},
                    )

            if user_level < ROLE_HIERARCHY.get(UserRole.field_worker, 2):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Insufficient permissions.", "error_code": "FORBIDDEN"},
                )

        except Exception as e:
            logger.warning("RBAC check failed: %s", e)

        return await call_next(request)
