from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.core.config import settings
from src.core.redis import check_rate_limit


def _too_many_requests(retry_after: str | None = None) -> JSONResponse:
    """A 429 built as a response rather than raised as an exception.

    Raising ``HTTPException`` from inside ``BaseHTTPMiddleware.dispatch`` puts
    the raise *outside* Starlette's ``ExceptionMiddleware``, which is what
    normally converts ``HTTPException`` into a status code. Nothing catches it
    there, so a rate-limited caller received a 500 — indistinguishable from a
    crash, wrong for the client's retry logic, and alarming in every dashboard.
    Returning the response directly is the correct shape for middleware.

    The body matches the ``AppError`` handler's ``{detail, error_code}`` shape
    so clients parse it like any other error, and carries ``Retry-After`` so an
    automated caller knows when to come back instead of hammering.
    """
    headers = {"Retry-After": retry_after} if retry_after else None
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Try again later.",
            "error_code": "RATE_LIMITED",
        },
        headers=headers,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/favicon.ico"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        ip_key = f"rl:ip:{client_ip}"
        limited = await check_rate_limit(ip_key, settings.RATE_LIMIT_IP_CAPACITY, settings.RATE_LIMIT_IP_REFILL)
        if limited:
            return _too_many_requests()

        user_id = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from src.core.security import decode_token

                payload = decode_token(auth_header[7:])
                user_id = payload.get("sub")
            except Exception:  # bad bearer token -> anonymous bucket  # nosec B110
                pass

        if not user_id:
            token_cookie = request.cookies.get("access_token")
            if token_cookie:
                try:
                    from src.core.security import decode_token

                    payload = decode_token(token_cookie)
                    user_id = payload.get("sub")
                except Exception:  # bad cookie token -> anonymous bucket  # nosec B110
                    pass

        if user_id:
            user_key = f"rl:user:{user_id}"
            user_limited = await check_rate_limit(
                user_key, settings.RATE_LIMIT_USER_CAPACITY, settings.RATE_LIMIT_USER_REFILL
            )
            if user_limited:
                return _too_many_requests()

        try:
            request.state.user_id = int(user_id) if user_id else None
        except (ValueError, TypeError):
            request.state.user_id = None

        response = await call_next(request)
        return response
