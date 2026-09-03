from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.deps import get_current_user
from src.domains.auth.oauth import (
    decode_oauth_state,
    encode_oauth_state,
    get_provider,
    login_with_provider,
)
from src.domains.auth.password_reset import reset_password, send_password_reset_email
from src.domains.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from src.domains.auth.service import AuthService
from src.errors import OAuthError, OAuthNotConfigured

router = APIRouter(prefix="/auth", tags=["Auth"])


def _redirect_response(url: str):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=url, status_code=302)


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
        httponly=False,
        samesite="lax",
        secure=is_secure,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("session_active", path="/")


@router.post("/register", response_model=UserResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    from src.errors import ForbiddenError
    from src.models.user import UserRole as _UserRole

    allowed_roles = {_UserRole.field_worker, _UserRole.viewer}
    try:
        requested_role = _UserRole(body.role)
    except ValueError:
        raise ForbiddenError("Invalid role.")
    if requested_role not in allowed_roles:
        raise ForbiddenError("Cannot self-register as admin or engineer.")

    svc = AuthService(db)
    user = await svc.register(body.email, body.password, body.full_name, body.role)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
    )


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    access_token, refresh_token = await svc.login(body.email, body.password)
    _set_auth_cookies(response, access_token, refresh_token)
    return {"detail": "Login successful"}


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=401, content={"detail": "No refresh token"})

    svc = AuthService(db)
    access_token, new_refresh_token = await svc.refresh(refresh_token)
    _set_auth_cookies(response, access_token, new_refresh_token)
    return {"detail": "Refresh successful"}


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    auth_header = request.headers.get("authorization", "")
    access_token = auth_header[7:] if auth_header.startswith("Bearer ") else None
    if refresh_token or access_token:
        svc = AuthService(db)
        await svc.logout(refresh_token, access_token)
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

    state = encode_oauth_state(provider, redirect)
    redirect_uri = _oauth_callback_uri(provider)
    uri = oauth.authorize_uri(redirect_uri, state=state)
    return _redirect_response(uri)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(default=""),
    state: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    oauth = get_provider(provider)
    if not oauth.configured:
        raise OAuthNotConfigured(provider)
    if not code:
        raise OAuthError("OAuth callback missing authorization code.")

    redirect_target = decode_oauth_state(provider, state)
    profile = await oauth.fetch_user(code, _oauth_callback_uri(provider))

    _, access_token, refresh_token = await login_with_provider(db, oauth, profile)

    # Return a 200 HTML page (NOT a 302) that carries the auth cookies and then
    # navigates the browser to the redirect target. Setting cookies on a redirect
    # response served through the Next.js proxy is unreliable (the browser drops
    # them on the follow-up navigation), which caused "logged in -> bounced back to
    # login". A 200 response keeps the proxy's Set-Cookie rewrite path identical to
    # the (working) email/login flow.
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

    html_response = HTMLResponse(content=html, status_code=200)
    _set_auth_cookies(html_response, access_token, refresh_token)
    return html_response


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await send_password_reset_email(db, body.email)
    return {"detail": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password_endpoint(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await reset_password(db, body.token, body.new_password)
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
    )


def _oauth_callback_uri(provider: str) -> str:
    """Build the callback URL that the OAuth provider must redirect the browser to.

    We route the callback through the Next.js proxy (``/api/proxy/...``) on the
    frontend origin. The proxy forwards to the backend, and rewrites the auth
    ``Set-Cookie`` headers onto the frontend domain so the session works exactly
    like the normal email/login flow. This is why the URI lives under
    ``FRONTEND_URL`` and not ``BACKEND_URL``.
    """
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/api/proxy/auth/oauth/{provider}/callback"
