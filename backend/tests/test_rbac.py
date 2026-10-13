"""Role-hierarchy authorization tests.

These exercise the RBAC middleware gate directly against Starlette
``Request`` scopes with crafted JWTs, so they need no database: the
middleware's decision is derived purely from JWT claims (see
``src/middleware/rbac.py``). The two behaviors under test are the ones a
previous reviewer flagged:

* resolving an issue (`/api/v1/resolution/`) is engineering work — an
  ``engineer`` must be able to write there (the old exact-role allowlist
  locked them out);
* every ``admin`` write path accepts any role *at or above* the declared
  minimum (the old exact-role rules locked ``admin`` out of issue writes).
"""

from __future__ import annotations

from datetime import timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.rbac import role_at_least
from src.core.security import create_access_token, create_refresh_token
from src.middleware.rbac import RBACMiddleware, _min_role_for
from src.models.user import UserRole

# ``dispatch`` never touches ``self.app``, so ``app=None`` is safe: the tests
# call ``dispatch(request, call_next)`` straight away without an ASGI stack.
_MIDDLEWARE = RBACMiddleware(app=None)


def _build_request(*, method: str, path: str, auth: str | None = None, cookie: str | None = None) -> Request:
    headers = []
    if auth is not None:
        headers.append((b"authorization", f"Bearer {auth}".encode()))
    if cookie is not None:
        headers.append((b"cookie", f"access_token={cookie}".encode()))
    scope: dict = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


async def _call_next(request: Request) -> Response:
    return JSONResponse({"ok": True})


def _token(role: str) -> str:
    return create_access_token({"sub": "1", "role": role})


async def _dispatch(method: str, path: str, *, auth: str | None = None, cookie: str | None = None) -> Response:
    request = _build_request(method=method, path=path, auth=auth, cookie=cookie)
    return await _MIDDLEWARE.dispatch(request, _call_next)


# ── role_at_least (unit) ──────────────────────────────────────────────────────


def test_role_at_least_passes_equal_and_higher() -> None:
    assert role_at_least(UserRole.super_admin, UserRole.admin)
    assert role_at_least(UserRole.admin, UserRole.admin)
    assert role_at_least(UserRole.admin, UserRole.engineer)
    assert role_at_least(UserRole.engineer, UserRole.field_worker)
    assert role_at_least(UserRole.field_worker, UserRole.viewer)
    assert role_at_least(UserRole.viewer, UserRole.viewer)


def test_role_at_least_fails_below_minimum() -> None:
    assert not role_at_least(UserRole.field_worker, UserRole.engineer)
    assert not role_at_least(UserRole.engineer, UserRole.admin)
    assert not role_at_least(UserRole.viewer, UserRole.field_worker)


def test_role_at_least_unknown_role_fails_closed() -> None:
    # A raw string that names no role at all sorts to tier 0, so it is never
    # "at least" anything — even the bottom tier. (UserRole is a str-enum, so
    # the real values like "admin" DO resolve through the dict keys.)
    assert not role_at_least("not-a-role", UserRole.viewer)  # type: ignore[arg-type]


# ── _min_role_for (unit) ──────────────────────────────────────────────────────


def test_min_role_for_declared_paths() -> None:
    assert _min_role_for("/api/v1/admin/roles") == UserRole.admin
    assert _min_role_for("/api/v1/engineers/1") == UserRole.admin
    assert _min_role_for("/api/v1/ml/predict") == UserRole.admin
    assert _min_role_for("/api/v1/resolution/42") == UserRole.engineer


def test_min_role_for_undeclared_path_defaults_to_field_worker() -> None:
    assert _min_role_for("/api/v1/issues/") == UserRole.field_worker
    assert _min_role_for("/api/v1/unknown/anything") == UserRole.field_worker


# ── dispatch passthrough (no token required) ─────────────────────────────────


async def test_read_and_unauthenticated_writes_pass_through() -> None:
    assert (await _dispatch("GET", "/api/v1/issues/")).status_code == 200
    assert (await _dispatch("POST", "/health")).status_code == 200
    assert (await _dispatch("POST", "/api/v1/auth/login")).status_code == 200
    assert (await _dispatch("POST", "/api/v1/auth/2fa/verify")).status_code == 200


# ── dispatch credential failures (fail closed) ───────────────────────────────


async def test_write_without_token_is_401() -> None:
    assert (await _dispatch("POST", "/api/v1/resolution/")).status_code == 401


async def test_garbage_token_is_401() -> None:
    assert (await _dispatch("POST", "/api/v1/resolution/", auth="not.a.token")).status_code == 401


async def test_expired_token_is_401() -> None:
    expired = create_access_token({"sub": "1", "role": "admin"}, expires_delta=timedelta(seconds=-1))
    assert (await _dispatch("POST", "/api/v1/resolution/", auth=expired)).status_code == 401


async def test_refresh_token_is_401() -> None:
    refresh = create_refresh_token({"sub": "1"})
    assert (await _dispatch("POST", "/api/v1/resolution/", auth=refresh)).status_code == 401


async def test_unknown_role_claim_is_401() -> None:
    bogus = create_access_token({"sub": "1", "role": "superuser"})
    assert (await _dispatch("POST", "/api/v1/resolution/", auth=bogus)).status_code == 401


# ── dispatch hierarchy gate: resolution writes are engineering work ──────────


async def test_field_worker_denied_resolution_write() -> None:
    assert (await _dispatch("POST", "/api/v1/resolution/", auth=_token("field_worker"))).status_code == 403


async def test_engineer_allowed_resolution_write() -> None:
    assert (await _dispatch("POST", "/api/v1/resolution/", auth=_token("engineer"))).status_code == 200


async def test_admin_allowed_resolution_write() -> None:
    assert (await _dispatch("POST", "/api/v1/resolution/", auth=_token("admin"))).status_code == 200


# ── dispatch hierarchy gate: admin-only paths include every higher tier ──────


async def test_engineer_denied_admin_write() -> None:
    assert (await _dispatch("POST", "/api/v1/admin/review-queue", auth=_token("engineer"))).status_code == 403


async def test_admin_allowed_admin_write() -> None:
    assert (await _dispatch("POST", "/api/v1/admin/review-queue", auth=_token("admin"))).status_code == 200


async def test_super_admin_allowed_admin_write() -> None:
    assert (await _dispatch("POST", "/api/v1/admin/review-queue", auth=_token("super_admin"))).status_code == 200


async def test_engineer_denied_roster_maintenance() -> None:
    assert (await _dispatch("POST", "/api/v1/engineers/", auth=_token("engineer"))).status_code == 403


async def test_admin_allowed_roster_maintenance() -> None:
    assert (await _dispatch("POST", "/api/v1/engineers/", auth=_token("admin"))).status_code == 200


async def test_engineer_denied_ml_write() -> None:
    assert (await _dispatch("POST", "/api/v1/ml/predict", auth=_token("engineer"))).status_code == 403


# ── dispatch hierarchy gate: default tier lets every writer through ──────────


async def test_issue_write_allows_field_worker() -> None:
    assert (await _dispatch("POST", "/api/v1/issues/", auth=_token("field_worker"))).status_code == 200


async def test_issue_write_allows_admin() -> None:
    assert (await _dispatch("POST", "/api/v1/issues/", auth=_token("admin"))).status_code == 200


async def test_issue_write_allows_super_admin() -> None:
    assert (await _dispatch("POST", "/api/v1/issues/", auth=_token("super_admin"))).status_code == 200


# ── dispatch cookie transport ─────────────────────────────────────────────────


async def test_cookie_token_is_honored() -> None:
    assert (await _dispatch("POST", "/api/v1/resolution/", cookie=_token("engineer"))).status_code == 200
    assert (await _dispatch("POST", "/api/v1/resolution/", cookie=_token("field_worker"))).status_code == 403
