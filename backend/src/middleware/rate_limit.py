from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings
from src.core.redis import check_rate_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/metrics", "/favicon.ico"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        ip_key = f"rl:ip:{client_ip}"
        limited = await check_rate_limit(ip_key, settings.RATE_LIMIT_IP_CAPACITY, settings.RATE_LIMIT_IP_REFILL)
        if limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded. Try again later."
            )

        user_id = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from src.core.security import decode_token

                payload = decode_token(auth_header[7:])
                user_id = payload.get("sub")
            except Exception:
                pass

        if not user_id:
            token_cookie = request.cookies.get("access_token")
            if token_cookie:
                try:
                    from src.core.security import decode_token

                    payload = decode_token(token_cookie)
                    user_id = payload.get("sub")
                except Exception:
                    pass

        if user_id:
            user_key = f"rl:user:{user_id}"
            user_limited = await check_rate_limit(
                user_key, settings.RATE_LIMIT_USER_CAPACITY, settings.RATE_LIMIT_USER_REFILL
            )
            if user_limited:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded. Try again later."
                )

        request.state.user_id = int(user_id) if user_id else None

        response = await call_next(request)
        return response
