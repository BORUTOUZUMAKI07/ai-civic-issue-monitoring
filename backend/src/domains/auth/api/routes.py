import logging
import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.security import create_ws_ticket
from src.core.security_store import (
    SecurityStoreUnavailableError,
    consume_one_time,
    delete_keys,
)
from src.domains.auth.email_verification import send_verification_email, verify_email_token
from src.domains.auth.oauth import (
    code_challenge,
    consume_oauth_handoff,
    consume_oauth_state,
    create_oauth_handoff,
    get_provider,
    login_with_provider,
    store_oauth_state,
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
    OauthExchangeRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TwoFactorConfirmRequest,
    TwoFactorEnableResponse,
    TwoFactorRecoveryCodesResponse,
    TwoFactorVerifyRequest,
    UserResponse,
    VerifyEmailRequest,
    WsTicketResponse,
)
from src.domains.auth.services.auth_service import AuthService
from src.domains.auth.twofa import TwoFactorService
from src.domains.users.deps import get_current_active_user, get_current_user
from src.shared.errors import OAuthError, OAuthNotConfigured, OAuthStateInvalid, RefreshTokenReuse
from src.shared.errors.base import AppError

logger = logging.getLogger("civicpulse")

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _audit_event(
    action: str,
    request: Request,
    user_id: int | str | None = None,
    details: dict | None = None,
    *,
    status: str = "success",
) -> None:
    """Thin wrapper so every auth handler shares one redaction policy."""
    from src.domains.audit.events import emit_audit_event

    await emit_audit_event(
        action,
        user_id=user_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=details,
        status=status,
    )


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
        email_verified=getattr(user, "email_verified", True),
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
    except RefreshTokenReuse:
        claims = _claims_from_token(refresh_token)
        await _audit_event(
            "refresh_reuse_detected",
            request,
            claims.get("sub"),
            {
                "outcome": "failure",
                "session_id": claims.get("sid"),
                "family_id": claims.get("fam"),
            },
        )
        _clear_auth_cookies(response)
        return JSONResponse(status_code=401, content={"detail": "Refresh token rejected"})
    except SecurityStoreUnavailableError:
        # Transient security-store outage: no replacement pair was minted. Keep
        # the existing cookies so the client can retry rather than forcing a
        # full re-login, and let the AppError handler emit the 503.
        raise
    except AppError:
        _clear_auth_cookies(response)
        return JSONResponse(status_code=401, content={"detail": "Refresh token rejected"})

    _set_auth_cookies(response, access_token, new_refresh_token)
    claims = _claims_from_token(refresh_token)
    await _audit_event(
        "refresh",
        request,
        claims.get("sub"),
        {"outcome": "success", "session_id": claims.get("sid"), "family_id": claims.get("fam")},
    )
    return {"detail": "Refresh successful"}


def _claims_from_token(token: str | None) -> dict:
    """Best-effort JWT claims for audit only; never used for authorization."""
    if not token:
        return {}
    try:
        from src.core.security import decode_token

        claims = decode_token(token)
        return claims if isinstance(claims, dict) else {}
    except Exception:  # nosec B110 - a malformed token still gets an audit row
        return {}


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
        except Exception:  # nosec B110 - best-effort user id extraction for audit
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

    state_id, code_verifier, nonce = await store_oauth_state(provider, redirect)
    redirect_uri = _oauth_callback_uri(provider)
    uri = oauth.authorize_uri(
        redirect_uri,
        state=state_id,
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
        max_age=600,
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

    bundle = await consume_oauth_state(provider, state)
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

    # The refresh token stays server-side. The browser receives only a random
    # one-time code, so no credential or OAuth state leaks through the redirect
    # URL (access logs, history, Referer). The redirect target is stored with
    # the handoff and returned later by /oauth/exchange.
    handoff = await create_oauth_handoff(refresh_token, redirect_target)
    frontend = settings.FRONTEND_URL.rstrip("/")
    target = f"{frontend}/login?code={handoff}"
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
    html_response.delete_cookie("oauth_state", path="/", httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)
    return html_response


@router.post("/oauth/exchange")
async def oauth_exchange(
    body: OauthExchangeRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Redeem the one-time callback code and establish the browser session."""
    from fastapi.responses import JSONResponse

    per_ip, per_account = login_limits()
    await enforce_auth_rate_limit(
        request, action="oauth_exchange", per_ip=per_ip, per_account=per_account, account=body.code
    )

    try:
        handoff = await consume_oauth_handoff(body.code)
        claims = _claims_from_token(handoff["refresh_token"])
        access_token, refresh_token = await AuthService(db).refresh(handoff["refresh_token"])
    except AppError:
        await _audit_event("oauth_exchange", request, None, {"outcome": "failure"}, status="failure")
        _clear_auth_cookies(response)
        return JSONResponse(status_code=401, content={"detail": "OAuth sign-in code is invalid or has expired."})

    _set_auth_cookies(response, access_token, refresh_token)
    user_id = claims.get("sub")
    await _audit_event("oauth_exchange", request, user_id, {"outcome": "success"})

    user_payload = None
    if user_id is not None:
        try:
            from src.domains.users.repositories.user_repository import UserRepository

            user = await UserRepository(db).get(int(str(user_id)))
            if user:
                user_payload = {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                    "two_factor_enabled": user.two_factor_enabled,
                    "email_verified": getattr(user, "email_verified", True),
                }
        except Exception:  # nosec B110 - session is already established
            user_payload = None

    return {
        "detail": "Login successful",
        "redirect": handoff["redirect"],
        "user": user_payload,
    }


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
        email_verified=getattr(user, "email_verified", True),
    )


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await verify_email_token(db, body.token)
    await _audit_event("email_verified", request, user.id)
    return {"detail": "Email verified. You can now sign in."}


@router.post("/resend-verification")
async def resend_verification(body: ResendVerificationRequest, request: Request, db: AsyncSession = Depends(get_db)):
    per_ip, per_account = forgot_password_limits()
    await enforce_auth_rate_limit(
        request, action="resend_verification", per_ip=per_ip, per_account=per_account, account=body.email
    )
    from src.domains.users.repositories.user_repository import UserRepository

    user = await UserRepository(db).get_by_email(body.email)
    if user and not getattr(user, "email_verified", True):
        try:
            await send_verification_email(db, user)
        except Exception:
            # Best-effort: do not leak account state or fail the request if email
            # delivery is temporarily unavailable.
            logger.warning("resend_verification: failed to send verification email")
    return {"detail": "If that email is registered and unverified, a verification link has been sent."}


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
    # consume_one_time raises SecurityStoreUnavailableError when Redis is down, so a
    # challenge cannot be exchanged twice just because the store was unreachable.
    if await consume_one_time(key, 300):
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
    # Revocation is a security write: if the store cannot record it, report the
    # outage instead of telling the caller the session is gone when it is not.
    await delete_keys(
        f"refresh:session:{sid}",
        f"refresh:family:{sid}",
    )
    try:
        await redis_client.srem(f"refresh:user:sessions:{user.id}", sid)
    except Exception:  # nosec B110 - the per-user index only powers the list view
        pass
    await _audit_event("session_revoked", request, user.id, {"session_id": sid})
    return {"detail": "Session revoked"}


@router.post("/sessions/revoke-all")
async def revoke_all_sessions(
    request: Request, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    from src.core.redis import redis_client
    from src.domains.auth.password_reset import revoke_all_refresh_sessions

    # The user-wide marker is the durable guarantee; the index walk is an
    # optimisation and stays best-effort.
    await revoke_all_refresh_sessions(user.id)
    try:
        sid_list = await redis_client.smembers(f"refresh:user:sessions:{user.id}")
        for sid in sid_list or []:
            await delete_keys(f"refresh:session:{sid}", f"refresh:family:{sid}")
        await delete_keys(f"refresh:user:sessions:{user.id}")
    except SecurityStoreUnavailableError:
        raise
    await _audit_event("sessions_revoked_all", request, user.id)
    return {"detail": "All other sessions have been signed out."}


@router.get("/account/export")
async def export_account(request: Request, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func, select

    from src.domains.issues.models.issue import Issue

    issues_count = (
        await db.execute(select(func.count()).select_from(Issue).where(Issue.reporter_id == user.id))
    ).scalar_one()
    # GDPR Art. 15 — record that a subject accessed their own data.
    await _audit_event("account_export", request, user.id)
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "email_verified": getattr(user, "email_verified", True),
            "two_factor_enabled": getattr(user, "two_factor_enabled", False),
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "issues_reported_count": int(issues_count or 0),
    }


@router.delete("/account")
async def delete_account(
    request: Request,
    response: Response,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from src.core.security import blacklist_token, decode_token
    from src.domains.auth.password_reset import revoke_all_refresh_sessions

    # Best-effort revoke sessions/refresh tokens.
    await revoke_all_refresh_sessions(user.id)
    try:
        from src.core.redis import redis_client

        sid_list = await redis_client.smembers(f"refresh:user:sessions:{user.id}")
        for sid in sid_list or []:
            await redis_client.delete(f"refresh:session:{sid}")
            await redis_client.delete(f"refresh:family:{sid}")
        await redis_client.delete(f"refresh:user:sessions:{user.id}")
    except Exception:  # nosec B110 - best-effort
        pass

    # Blacklist current access token if present.
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = decode_token(access_token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                import time

                ttl = int(exp) - int(time.time())
                if ttl > 0:
                    await blacklist_token(jti, ttl)
        except Exception:  # nosec B110 - best-effort
            pass

    # Anonymize and deactivate the account in-place to satisfy GDPR erasure while
    # preserving referential integrity for civic records (e.g. reported issues).
    anon_email = f"deleted+{user.id}+{secrets.token_hex(8)}@invalid.local"
    user.email = anon_email
    user.full_name = "Deleted User"
    user.is_active = False
    user.email_verified = False
    user.email_verified_at = None
    user.two_factor_enabled = False
    user.totp_secret = None
    user.totp_last_counter = None
    user.recovery_codes = None
    user.oauth_provider = None
    user.oauth_sub = None
    # Set an unusable password hash.
    from src.core.security import hash_password_async

    user.password_hash = await hash_password_async(secrets.token_urlsafe(32))
    await db.commit()

    await _audit_event("account_deleted", request, user.id)
    _clear_auth_cookies(response)
    return {"detail": "Account deleted."}


def _oauth_callback_uri(provider: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/api/proxy/auth/oauth/{provider}/callback"
