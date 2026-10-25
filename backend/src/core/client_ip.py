from __future__ import annotations

from fastapi import Request

from src.core.config import settings


def resolve_client_ip(request: Request) -> str:
    trusted = getattr(settings, "TRUSTED_PROXIES", None) or []
    if trusted and request.client and request.client.host in trusted:
        fwd = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
        real = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
        if real:
            return real.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
