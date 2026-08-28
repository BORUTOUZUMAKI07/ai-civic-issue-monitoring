from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.deps import get_current_user
from src.domains.auth.schemas import LoginRequest, RegisterRequest, UserResponse
from src.domains.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


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
    if refresh_token:
        svc = AuthService(db)
        await svc.logout(refresh_token)
    _clear_auth_cookies(response)
    return {"detail": "Logged out"}


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
