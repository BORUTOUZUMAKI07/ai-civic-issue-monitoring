"""Regression tests for the API hardening pass.

Seven verified defects, one file:

1. ``await file.read()`` with no bound: an authenticated uploader could push a
   gigabyte of bytes into a single handler, times concurrent requests. The
   bounded read in ``src.shared.uploads`` and the ``Content-Length`` check in
   ``RequestBodyLimitMiddleware`` are both load-bearing; the tests below
   exercise each layer separately so neither can be quietly dropped.
2. ``validate_image`` trusted the byte count alone: a 48 KB PNG declaring 400
   megapixels costs ~1.2 GB once decoded to RGB. The pixel ceiling fires on
   the header, before any decode.
3. ``float(latitude)`` on a string Form field: a non-numeric coordinate was an
   unhandled ``ValueError`` (500), and ``nan``/``inf`` sailed through to the
   database. The handler now declares a bounded ``float``, which is a 422.
4. Register/reset/change accepted an empty password over the API while the
   frontend asked for six characters, so the UI rule was cosmetic.
5. ``ALGORITHM`` came straight from the environment into
   ``jwt.decode(algorithms=[...])``: one bad variable turns every token check
   into a rubber stamp.
6. No baseline security headers on any API response — including the error
   replies, which is where sniffing and framing actually bite.
"""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from src.core.config import Settings
from src.shared.errors import ImageTooLargeError
from src.shared.uploads import (
    MAX_IMAGE_PIXELS,
    MAX_JSON_BODY_BYTES,
    MAX_UPLOAD_BODY_BYTES,
    MAX_UPLOAD_BYTES,
    read_upload_bounded,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Bounded read
# ─────────────────────────────────────────────────────────────────────────────


async def _upload(data: bytes, filename: str = "photo.jpg") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename, headers=Headers({}))


async def test_bounded_read_accepts_content_at_the_limit() -> None:
    content = b"a" * MAX_UPLOAD_BYTES
    result = await read_upload_bounded(await _upload(content))
    assert result == content


async def test_bounded_read_refuses_one_byte_over_the_limit() -> None:
    with pytest.raises(ImageTooLargeError):
        await read_upload_bounded(await _upload(b"a" * (MAX_UPLOAD_BYTES + 1)))


async def test_bounded_read_does_not_pull_the_whole_body_into_memory() -> None:
    """The read must stop at limit+1, not drain the spool.

    This is the actual memory bound. ``await file.read()`` (the old code)
    would return every byte; the bounded version must return at most
    ``limit + 1`` even when the underlying stream is far larger.
    """
    oversized = b"a" * (MAX_UPLOAD_BYTES + 1024 * 1024)
    upload = await _upload(oversized)
    with pytest.raises(ImageTooLargeError):
        await read_upload_bounded(upload)
    # The file position proves the read stopped early: it advanced by at most
    # limit+1 bytes, never to the end of the oversized payload.
    assert upload.file.tell() <= MAX_UPLOAD_BYTES + 1


async def test_bounded_read_respects_a_custom_limit() -> None:
    with pytest.raises(ImageTooLargeError):
        await read_upload_bounded(await _upload(b"1234567890"), limit=5)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pixel ceiling (decompression bomb)
# ─────────────────────────────────────────────────────────────────────────────


def _png_declaring_huge_dimensions(width: int, height: int) -> bytes:
    """A byte-cheap PNG whose header declares far more pixels than the bytes.

    A 1-bit solid-colour image compresses to a few kilobytes regardless of
    dimensions, so this passes a *byte* check while costing a multiple of
    width*height bytes the moment Pillow decodes it to RGB.
    """
    from PIL import Image

    img = Image.new("1", (width, height), 0)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_pixel_ceiling_is_below_the_decompression_bomb_threshold() -> None:
    """The configured cap must be well under Pillow's own 178 MP hard stop."""
    from PIL import Image

    pillow_ceiling = Image.MAX_IMAGE_PIXELS or 0
    assert MAX_IMAGE_PIXELS < pillow_ceiling


def test_validate_image_rejects_a_pixel_bomb() -> None:
    """64 MP is under Pillow's limit but over ours — only our ceiling catches it.

    This band matters: choosing dimensions past Pillow's 178 MP hard stop
    (as an earlier version of this test did) proves nothing about
    ``MAX_IMAGE_PIXELS``, because ``Image.open`` refuses the file first and
    the ``DecompressionBombError`` mapping answers instead. 8000x8000 opens
    cleanly, so the rejection can only come from the ceiling under test.
    """
    from src.domains.issues.services.issue_service import IssueService

    assert 8000 * 8000 > MAX_IMAGE_PIXELS  # the band this test depends on
    content = _png_declaring_huge_dimensions(8000, 8000)
    # The file is well under the byte limit — the pixel check is the only
    # thing that can catch it.
    assert len(content) < MAX_UPLOAD_BYTES

    svc = IssueService.__new__(IssueService)  # no DB needed for validate_image
    with pytest.raises(ImageTooLargeError, match="dimensions"):
        svc.validate_image("bomb.png", content)


def test_validate_image_maps_pillow_bomb_stop_to_too_large_not_corrupt() -> None:
    """Past Pillow's own hard stop the answer is still "too large", not "corrupt".

    A 400 MP image is a perfectly valid PNG; reporting it as corrupted
    would send the user chasing a file problem that does not exist.
    """
    from src.domains.issues.services.issue_service import IssueService

    content = _png_declaring_huge_dimensions(20_000, 20_000)
    assert len(content) < MAX_UPLOAD_BYTES

    svc = IssueService.__new__(IssueService)
    with pytest.raises(ImageTooLargeError, match="dimensions"):
        svc.validate_image("bomb.png", content)


def test_validate_image_still_accepts_a_normal_photo() -> None:
    from src.domains.issues.services.issue_service import IssueService

    from PIL import Image

    img = Image.new("RGB", (640, 480), (120, 200, 90))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    svc = IssueService.__new__(IssueService)
    svc.validate_image("normal.jpg", buf.getvalue())  # must not raise


def test_validate_image_rejects_oversized_bytes() -> None:
    from src.domains.issues.services.issue_service import IssueService

    svc = IssueService.__new__(IssueService)
    with pytest.raises(ImageTooLargeError):
        svc.validate_image("big.jpg", b"\x00" * (MAX_UPLOAD_BYTES + 1))


def test_validate_image_rejects_disallowed_extension() -> None:
    from src.domains.issues.services.issue_service import IssueService

    svc = IssueService.__new__(IssueService)
    with pytest.raises(Exception, match="Invalid file type"):
        svc.validate_image("payload.html", b"<script>alert(1)</script>")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Middleware: Content-Length rejection before parsing
# ─────────────────────────────────────────────────────────────────────────────


def test_json_body_limit_is_modest() -> None:
    """No endpoint here legitimately takes a megabyte of JSON."""
    assert MAX_JSON_BODY_BYTES == 1024 * 1024


def test_upload_body_limit_has_headroom_over_the_file_limit() -> None:
    """Multipart envelope + text fields must fit inside the body ceiling."""
    assert MAX_UPLOAD_BODY_BYTES > MAX_UPLOAD_BYTES
    assert MAX_UPLOAD_BODY_BYTES - MAX_UPLOAD_BYTES >= 1024 * 1024


async def test_middleware_rejects_oversized_json_body(client) -> None:
    """An actually-oversized JSON body is a 413, refused before parsing.

    The body must be real, not just a large declared ``Content-Length``:
    httpx recomputes that header from the body it is given, so a hand-set
    value would never reach the middleware.
    """
    res = await client.post(
        "/api/v1/auth/login",
        content=b"x" * (MAX_JSON_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 413
    assert res.json()["error_code"] == "PAYLOAD_TOO_LARGE"


async def test_middleware_rejects_oversized_upload_body(client, auth_headers) -> None:
    """The upload path gets the larger (file-aware) ceiling, not the JSON one."""
    res = await client.post(
        "/api/v1/issues/upload",
        content=b"x" * (MAX_UPLOAD_BODY_BYTES + 1),
        headers={
            **auth_headers,
            "Content-Type": "multipart/form-data; boundary=X",
        },
    )
    assert res.status_code == 413
    assert res.json()["error_code"] == "PAYLOAD_TOO_LARGE"


async def test_middleware_rejects_a_body_that_fits_the_upload_ceiling_not_the_json_one(client, auth_headers) -> None:
    """Between 1MB and 7MB: fine as an upload, refused as JSON.

    Proves the two ceilings are actually distinct rather than one shared
    number, which is the whole point of routing by path.
    """
    body = b"x" * (MAX_JSON_BODY_BYTES + 1024)
    assert len(body) < MAX_UPLOAD_BODY_BYTES

    as_json = await client.post(
        "/api/v1/auth/login",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert as_json.status_code == 413

    as_upload = await client.post(
        "/api/v1/issues/upload",
        content=body,
        headers={**auth_headers, "Content-Type": "multipart/form-data; boundary=X"},
    )
    assert as_upload.status_code != 413


async def test_middleware_passes_bodies_under_the_limit(client) -> None:
    """A normal small JSON body is not affected."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever123"},
    )
    # Not 413 — the middleware let it through (401/422/200 are all fine here).
    assert res.status_code != 413


async def test_middleware_ignores_get_requests(client) -> None:
    """A huge declared length on a bodyless method is not rejected."""
    res = await client.get(
        "/api/v1/auth/login",
        headers={"Content-Length": str(MAX_JSON_BODY_BYTES + 1)},
    )
    assert res.status_code != 413


# ─────────────────────────────────────────────────────────────────────────────
# 4. Coordinate validation (was: ValueError → 500)
# ─────────────────────────────────────────────────────────────────────────────


async def test_upload_rejects_non_numeric_latitude(client, auth_headers) -> None:
    """A non-numeric coordinate must be a 422, not a 500."""
    res = await client.post(
        "/api/v1/issues/upload",
        data={"latitude": "not-a-number", "longitude": "73.0"},
        files={"file": ("x.jpg", b"\xff\xd8\xff\xe0JUNK", "image/jpeg")},
        headers=auth_headers,
    )
    assert res.status_code == 422


async def test_upload_rejects_out_of_range_latitude(client, auth_headers) -> None:
    """Latitude outside [-90, 90] is a 422, not stored."""
    res = await client.post(
        "/api/v1/issues/upload",
        data={"latitude": "91.0", "longitude": "73.0"},
        files={"file": ("x.jpg", b"\xff\xd8\xff\xe0JUNK", "image/jpeg")},
        headers=auth_headers,
    )
    assert res.status_code == 422


async def test_upload_rejects_nan_coordinate(client, auth_headers) -> None:
    """`nan` parses as a float but must not survive validation."""
    res = await client.post(
        "/api/v1/issues/upload",
        data={"latitude": "nan", "longitude": "nan"},
        files={"file": ("x.jpg", b"\xff\xd8\xff\xe0JUNK", "image/jpeg")},
        headers=auth_headers,
    )
    assert res.status_code == 422


async def test_upload_rejects_oversized_description(client, auth_headers) -> None:
    """The description field is bounded, not an unbounded text sink."""
    res = await client.post(
        "/api/v1/issues/upload",
        data={"latitude": "22.3", "longitude": "73.1", "description": "x" * 5000},
        files={"file": ("x.jpg", b"\xff\xd8\xff\xe0JUNK", "image/jpeg")},
        headers=auth_headers,
    )
    assert res.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 5. JWT algorithm pinning
# ─────────────────────────────────────────────────────────────────────────────


def test_algorithm_none_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="ALGORITHM"):
        Settings(SECRET_KEY="a" * 64, ALGORITHM="none")


def test_algorithm_asymmetric_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ALGORITHM"):
        Settings(SECRET_KEY="a" * 64, ALGORITHM="RS256")


def test_algorithm_hs_familiy_is_accepted() -> None:
    for alg in ("HS256", "HS384", "HS512"):
        s = Settings(SECRET_KEY="a" * 64, ALGORITHM=alg)
        assert s.ALGORITHM == alg


# ─────────────────────────────────────────────────────────────────────────────
# 6. Password policy at the API boundary
# ─────────────────────────────────────────────────────────────────────────────
#
# The frontend already refused a 5-character password, but the API did not:
# `password: str` accepted "" and "abc", so any non-browser client could create
# an account or reset a password to something argon2 hashes in microseconds.
# These assert the boundary, which is the only one an attacker cannot skip.


async def test_register_rejects_a_short_password(client) -> None:
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "shortpw@example.com",
            "password": "abcde",
            "full_name": "Short Password",
        },
    )
    assert res.status_code == 422, res.text


async def test_register_rejects_an_empty_password(client) -> None:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": "emptypw@example.com", "password": "", "full_name": "Empty Password"},
    )
    assert res.status_code == 422, res.text


async def test_register_rejects_an_absurdly_long_password(client) -> None:
    """Upper bound too: argon2 work must not scale with attacker-chosen input."""
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "longpw@example.com",
            "password": "a" * 5000,
            "full_name": "Long Password",
        },
    )
    assert res.status_code == 422, res.text


async def test_reset_password_rejects_a_short_new_password(client) -> None:
    """Validated before the token is even looked at — no valid token needed."""
    res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "abc"},
    )
    assert res.status_code == 422, res.text


async def test_change_password_rejects_an_absurdly_long_new_password(client, auth_headers) -> None:
    res = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "OldPass123!", "new_password": "a" * 5000},
        headers=auth_headers,
    )
    assert res.status_code == 422, res.text


# ─────────────────────────────────────────────────────────────────────────────
# 7. Baseline security headers
# ─────────────────────────────────────────────────────────────────────────────
#
# `SecurityHeadersMiddleware` is outermost precisely so the *error* replies
# carry them too — an error page is exactly where sniffing and framing bite.
# Both a success and a failure are checked, since a middleware added in the
# wrong position passes the first and fails the second.

EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


async def test_security_headers_on_a_successful_response(client) -> None:
    res = await client.get("/health")
    for name, value in EXPECTED_HEADERS.items():
        assert res.headers.get(name) == value, f"{name} missing on 200"


async def test_security_headers_on_an_error_response(client) -> None:
    """The 401 path never reaches an inner middleware, so position is what's tested."""
    res = await client.get("/api/v1/issues")
    assert res.status_code == 401
    for name, value in EXPECTED_HEADERS.items():
        assert res.headers.get(name) == value, f"{name} missing on {res.status_code}"


async def test_security_headers_on_a_404(client) -> None:
    res = await client.get("/api/v1/definitely-not-a-route")
    for name, value in EXPECTED_HEADERS.items():
        assert res.headers.get(name) == value, f"{name} missing on 404"
