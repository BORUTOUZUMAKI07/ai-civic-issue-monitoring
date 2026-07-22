from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.database import AsyncSessionLocal
from src.errors import ForbiddenError
from src.models.user import UserRole

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ROLE_HIERARCHY = {
    UserRole.admin: 4,
    UserRole.engineer: 3,
    UserRole.field_worker: 2,
    UserRole.viewer: 1,
}


class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in WRITE_METHODS or not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        if not hasattr(request.state, "user_id") or not request.state.user_id:
            return await call_next(request)

        if request.url.path.startswith("/api/v1/auth/"):
            return await call_next(request)

        from src.core.security import decode_token
        from src.repositories.user_repository import UserRepository

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return await call_next(request)

        try:
            payload = decode_token(auth_header[7:])
            user_id = payload.get("sub")
            if not user_id:
                return await call_next(request)

            async with AsyncSessionLocal() as session:
                user = await UserRepository(session).get(int(user_id))
                if not user:
                    return await call_next(request)

                user_level = ROLE_HIERARCHY.get(user.role, 0)

                if request.url.path.startswith("/api/v1/engineers/") and user.role != UserRole.admin:
                    if user_level < ROLE_HIERARCHY.get(UserRole.engineer, 3):
                        raise ForbiddenError(detail="Engineer access required.")

                if user_level < ROLE_HIERARCHY.get(UserRole.field_worker, 2):
                    raise ForbiddenError(detail="Insufficient permissions.")

        except ForbiddenError:
            raise
        except Exception as e:
            import logging

            logging.getLogger("civicpulse").warning("RBAC check failed: %s", e)

        return await call_next(request)
