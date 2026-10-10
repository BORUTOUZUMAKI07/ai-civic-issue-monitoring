from typing import cast

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from src.core.config import settings
from src.core.redis import RateLimitResult, consume_rate_limit

# Paths that must never be throttled: liveness/health probes and the Prometheus
# scrape endpoint. A scrape is not "traffic" from a user, and denying it on a
# busy host would blind monitoring exactly when it is needed most.
_UNTHROTTLED_PATHS = ("/health", "/favicon.ico", "/metrics")


def _rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    """The RFC-style budget headers every throttled response carries."""
    return {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_seconds),
    }


def _too_many_requests(result: RateLimitResult) -> JSONResponse:
    """A 429 built as a response rather than raised as an exception.

    Raising ``HTTPException`` from inside ``BaseHTTPMiddleware.dispatch`` puts
    the raise *outside* Starlette's ``ExceptionMiddleware``, which is what
    normally converts ``HTTPException`` into a status code. Nothing catches it
    there, so a rate-limited caller received a 500 — indistinguishable from a
    crash, wrong for the client's retry logic, and alarming in every dashboard.
    Returning the response directly is the correct shape for middleware.

    The body matches the ``AppError`` handler's ``{detail, error_code}`` shape
    so clients parse it like any other error, and carries ``Retry-After`` plus
    the ``X-RateLimit-*`` budget so an automated caller knows when to come back
    and how much headroom it has, instead of hammering blindly.
    """
    headers = {
        "Retry-After": str(result.reset_seconds),
        **_rate_limit_headers(result),
    }
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Try again later.",
            "error_code": "RATE_LIMITED",
        },
        headers=headers,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _UNTHROTTLED_PATHS:
            return cast(Response, await call_next(request))

        client_ip = request.client.host if request.client else "unknown"
        ip_key = f"rl:ip:{client_ip}"
        ip_result = await consume_rate_limit(ip_key, settings.RATE_LIMIT_IP_CAPACITY, settings.RATE_LIMIT_IP_REFILL)
        if not ip_result.allowed:
            return _too_many_requests(ip_result)

        user_id = _user_id_from_request(request)

        # The headers reflect the *tightest* bucket that applied: the per-user
        # bucket when the caller is identified, the per-IP bucket otherwise.
        effective = ip_result
        if user_id:
            user_key = f"rl:user:{user_id}"
            user_result = await consume_rate_limit(
                user_key, settings.RATE_LIMIT_USER_CAPACITY, settings.RATE_LIMIT_USER_REFILL
            )
            if not user_result.allowed:
                return _too_many_requests(user_result)
            effective = user_result

        try:
            request.state.user_id = int(user_id) if user_id else None
        except (ValueError, TypeError):
            request.state.user_id = None

        response = await call_next(request)
        for header, value in _rate_limit_headers(effective).items():
            response.headers[header] = value
        return cast(Response, response)


def _user_id_from_request(request: Request) -> str | None:
    """Best-effort subject extraction for the per-user bucket.

    A malformed or absent token simply falls back to the per-IP bucket — this
    runs before routing, so it must never raise.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get("access_token")
    if not token:
        return None
    try:
        from src.core.security import decode_token

        return decode_token(token).get("sub") or None
    except Exception:  # bad/expired token -> anonymous bucket
        return None
