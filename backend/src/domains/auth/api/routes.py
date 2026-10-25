import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.security import create_ws_ticket
from src.domains.auth.oauth import (
    code_challenge,
    decode_oauth_bundle,
    encode_oauth_state,
    get_provider,
    login_with_provider,
)
from src.domains.auth.password_reset import reset_password, send_password_reset_email
from src.domains.auth.rate_limit import (
    enforce_auth_rate_limit,
    forgot_password_limits,
    login_limits,
    refresh_limits,
)
from src.domains.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TwoFactorConfirmRequest,
    TwoFactorEnableResponse,
    TwoFactorRecoveryCodesResponse,
    TwoFactorVerifyRequest,
    UserResponse,
    WsTicketResponse,
)
from src.domains.auth.services.auth_service import AuthService
from src.domains.auth.twofa import TwoFactorService
from src.domains.users.deps import get_current_active_user, get_current_user
from src.shared.errors import OAuthError, OAuthNotConfigured, OAuthStateInvalid
from src.shared.errors.base import AppError

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _audit_event(
    action: str, request: Request, user_id: int | str | None = None, details: dict | None = None
) -> None:
    try:
        import json

        from src.core.redis import redis_client

        event = {
            "action": action,
            "user_id": user_id,
            "ip": request.client.host if request.client else "unknown",
            "ua": request.headers.get("user-agent"),
            "details": details or {},
        }
        await redis_client.lpush("auth:audit", json.dumps(event))
        await redis_client.ltrim("auth:audit", 0, 999)
    except Exception:
        pass


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    is_secure = settings.COOKIE_SECURE

    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )
    response.set_cookie(
        "session_active",
        "1",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/", httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)
    response.delete_cookie("refresh_token", path="/", httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)
    response.delete_cookie("session_active", path="/", httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)


@router.post("/register", response_model=UserResponse)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from src.domains.users.models.user import UserRole as _UserRole
    from src.shared.errors import ForbiddenError

    per_ip, per_account = login_limits()
    await enforce_auth_rate_limit(
        request, action="register", per_ip=per_ip, per_account=per_account, account=body.email
    )

    allowed_roles = {_UserRole.field_worker, _UserRole.viewer}
    try:
        requested_role = _UserRole(body.role)
    except ValueError:
        raise ForbiddenError("Invalid role.")
    if requested_role not in allowed_roles:
        raise ForbiddenError("Cannot self-register as admin or engineer.")

    svc = AuthService(db)
    user = await svc.register(body.email, body.password, body.full_name, body.role)
    await _audit_event("register", request, user.id)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        two_factor_enabled=user.two_factor_enabled,
    )


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    per_ip, per_account = login_limits()
    await enforce_auth_rate_limit(request, action="login", per_ip=per_ip, per_account=per_account, account=body.email)

    svc = TwoFactorService(db)
    result = await svc.verify_or_challenge(body.email, body.password)

    if isinstance(result, tuple):
        access_token, refresh_token = result
        _set_auth_cookies(response, access_token, refresh_token)
        try:
            from src.core.security import decode_token

            sub = decode_token(access_token).get("sub")
            await _audit_event("login", request, sub)
        except Exception:
            await _audit_event("login", request)
        return {"detail": "Login successful"}

    await _audit_event("login_2fa_challenge", request)
    return {"detail": "Two-factor authentication required", "challenge": result}


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import JSONResponse

    per_ip, per_account = refresh_limits()
    account = None
    presented = request.cookies.get("refresh_token")
    if presented:
        try:
            from src.core.security import decode_token

            account = decode_token(presented).get("sub")
        except Exception:
            account = None
    await enforce_auth_rate_limit(request, action="refresh", per_ip=per_ip, per_account=per_account, account=account)

    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        _clear_auth_cookies(response)
        return JSONResponse(status_code=401, content={"detail": "No refresh token"})

    svc = AuthService(db)
    try:
        access_token, new_refresh_token = await svc.refresh(refresh_token)
    except AppError:
        _clear_auth_cookies(response)
        return JSONResponse(status_code=401, content={"detail": "Refresh token rejected"})

    _set_auth_cookies(response, access_token, new_refresh_token)
    return {"detail": "Refresh successful"}


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        access_token: str | None = auth_header[7:]
    else:
        access_token = request.cookies.get("access_token")
    user_id = None
    if access_token:
        try:
            from src.core.security import decode_token

            user_id = decode_token(access_token).get("sub")
        except Exception:
            pass
    if refresh_token or access_token:
        svc = AuthService(db)
        await svc.logout(refresh_token, access_token)
    await _audit_event("logout", request, user_id)
    _clear_auth_cookies(response)
    return {"detail": "Logged out"}


@router.get("/oauth/providers")
async def oauth_providers():
    from src.domains.auth.oauth import get_provider

    result = {}
    for name in ("google", "github"):
        try:
            result[name] = get_provider(name).configured
        except Exception:
            result[name] = False
    return result


@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: str,
    redirect: str = Query(default="/dashboard"),
):
    oauth = get_provider(provider)
    if not oauth.configured:
        raise OAuthNotConfigured(provider)

    state, code_verifier, nonce = encode_oauth_state(provider, redirect)
    redirect_uri = _oauth_callback_uri(provider)
    uri = oauth.authorize_uri(
        redirect_uri,
        state=state,
        code_challenge=code_challenge(code_verifier),
    )

    html_uri = uri.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    js_uri = uri.replace("\\", "\\\\").replace('"', '\\"')
    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url={0}">'
        '<script>window.location.replace("{1}");</script></head>'
        '<body><script>window.location.replace("{1}");</script>'
        "</body></html>"
    ).format(html_uri, js_uri)

    from fastapi.responses import HTMLResponse

    html_response = HTMLResponse(content=html, status_code=200, headers={"Cache-Control": "no-store"})
    html_response.set_cookie(
        "oauth_state",
        nonce,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    return html_response


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    oauth = get_provider(provider)
    if not oauth.configured:
        raise OAuthNotConfigured(provider)
    if not code:
        raise OAuthError("OAuth callback missing authorization code.")

    bundle = decode_oauth_bundle(provider, state)
    redirect_target = bundle["redirect"]

    cookie_nonce = request.cookies.get("oauth_state")
    if not cookie_nonce or not secrets.compare_digest(cookie_nonce, bundle["nonce"]):
        raise OAuthStateInvalid()

    profile = await oauth.fetch_user(
        code,
        _oauth_callback_uri(provider),
        code_verifier=bundle["code_verifier"],
    )

    _, access_token, refresh_token = await login_with_provider(db, oauth, profile)
    try:
        from src.core.security import decode_token

        await _audit_event("oauth_login", request, decode_token(access_token).get("sub"), {"provider": provider})
    except Exception:
        await _audit_event("oauth_login", request, None, {"provider": provider})

    frontend = settings.FRONTEND_URL.rstrip("/")
    target = f"{frontend}{redirect_target}"
    escaped = target.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url={0}">'
        '<script>window.location.replace("{0}");</script></head>'
        '<body><script>window.location.replace("{0}");</script>'
        "</body></html>"
    ).format(escaped)

    from fastapi.responses import HTMLResponse

    html_response = HTMLResponse(content=html, status_code=200, headers={"Cache-Control": "no-store"})
    _set_auth_cookies(html_response, access_token, refresh_token)
    html_response.delete_cookie("oauth_state", path="/", httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)
    return html_response


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    per_ip, per_account = forgot_password_limits()
    await enforce_auth_rate_limit(request, action="forgot", per_ip=per_ip, per_account=per_account, account=body.email)
    await send_password_reset_email(db, body.email)
    return {"detail": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password_endpoint(body: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await reset_password(db, body.token, body.new_password)
    await _audit_event("password_reset", request)
    return {"detail": "Password has been reset. You can now sign in."}


@router.get("/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        two_factor_enabled=user.two_factor_enabled,
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).change_password(user, body.current_password, body.new_password)
    await _audit_event("password_change", request, user.id)
    return {"detail": "Password changed. Other sessions have been signed out."}


@router.get("/ws-ticket", response_model=WsTicketResponse)
async def ws_ticket(user=Depends(get_current_active_user)):
    return WsTicketResponse(ticket=create_ws_ticket(user.id))


@router.post("/2fa/enable", response_model=TwoFactorEnableResponse)
async def enable_2fa(request: Request, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    svc = TwoFactorService(db)
    secret, uri = await svc.enable(user.id)
    await _audit_event("2fa_enable_start", request, user.id)
    return TwoFactorEnableResponse(secret=secret, provisioning_uri=uri)


@router.post("/2fa/confirm", response_model=TwoFactorRecoveryCodesResponse)
async def confirm_2fa(
    body: TwoFactorConfirmRequest,
    request: Request,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TwoFactorService(db)
    codes = await svc.confirm(user.id, body.code)
    await _audit_event("2fa_enabled", request, user.id)
    return TwoFactorRecoveryCodesResponse(recovery_codes=codes)


@router.post("/2fa/disable")
async def disable_2fa(
    body: TwoFactorConfirmRequest,
    request: Request,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TwoFactorService(db)
    await svc.disable(user.id, body.code)
    await _audit_event("2fa_disabled", request, user.id)
    return {"detail": "Two-factor authentication disabled"}


@router.post("/2fa/verify")
async def verify_2fa(
    body: TwoFactorVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    from src.core.security import decode_token as _decode_token

    payload = _decode_token(body.challenge)
    if payload.get("type") != "2fa_challenge":
        from src.shared.errors import InvalidToken

        raise InvalidToken()

    per_ip, per_account = login_limits()
    await enforce_auth_rate_limit(
        request, action="2fa", per_ip=per_ip, per_account=per_account, account=payload.get("sub")
    )

    user_id = int(payload["sub"])
    svc = TwoFactorService(db)

    access_token, refresh_token = await svc.verify_challenge(user_id, body.code)

    if payload.get("jti"):
        await _consume_2fa_challenge(payload["jti"])

    _set_auth_cookies(response, access_token, refresh_token)
    await _audit_event("2fa_verified", request, user_id)
    return {"detail": "Login successful"}


async def _consume_2fa_challenge(jti: str) -> None:
    from src.shared.errors import InvalidToken

    key = f"2fa:used:{jti}"
    try:
        from src.core.redis import redis_client

        was_new = await redis_client.set(key, "1", ex=300, nx=True)
    except Exception:
        return
    if not bool(was_new):
        raise InvalidToken()


@router.post("/2fa/recovery-codes", response_model=TwoFactorRecoveryCodesResponse)
async def regenerate_recovery_codes(
    body: TwoFactorConfirmRequest,
    request: Request,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TwoFactorService(db)
    codes = await svc.regenerate_recovery_codes(user.id, body.code)
    await _audit_event("2fa_recovery_regenerate", request, user.id)
    return TwoFactorRecoveryCodesResponse(recovery_codes=codes)


@router.get("/sessions")
async def list_sessions(request: Request, user=Depends(get_current_active_user)):
    from src.core.redis import redis_client

    sessions = []
    try:
        sid_list = await redis_client.smembers(f"refresh:user:sessions:{user.id}")
        for sid in sid_list or []:
            rec = await redis_client.get(f"refresh:session:{sid}")
            sessions.append({"id": sid, "active": rec is not None})
    except Exception:
        return []
    return sessions


@router.post("/sessions/revoke")
async def revoke_session(body: dict, request: Request, user=Depends(get_current_active_user)):
    from src.core.redis import redis_client

    sid = body.get("session_id") if isinstance(body, dict) else None
    if not sid:
        from src.shared.errors import BadRequestError

        raise BadRequestError("session_id required")
    try:
        await redis_client.delete(f"refresh:session:{sid}")
        await redis_client.delete(f"refresh:family:{sid}")
        await redis_client.srem(f"refresh:user:sessions:{user.id}", sid)
    except Exception:
        pass
    await _audit_event("session_revoked", request, user.id, {"session_id": sid})
    return {"detail": "Session revoked"}


@router.post("/sessions/revoke-all")
async def revoke_all_sessions(
    request: Request, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    from src.core.redis import redis_client
    from src.domains.auth.password_reset import revoke_all_refresh_sessions

    await revoke_all_refresh_sessions(user.id)
    try:
        sid_list = await redis_client.smembers(f"refresh:user:sessions:{user.id}")
        for sid in sid_list or []:
            await redis_client.delete(f"refresh:session:{sid}")
            await redis_client.delete(f"refresh:family:{sid}")
        await redis_client.delete(f"refresh:user:sessions:{user.id}")
    except Exception:
        pass
    await _audit_event("sessions_revoked_all", request, user.id)
    return {"detail": "All other sessions have been signed out."}


def _oauth_callback_uri(provider: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/api/proxy/auth/oauth/{provider}/callback"
