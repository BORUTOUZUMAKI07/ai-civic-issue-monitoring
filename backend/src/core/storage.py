"""Upload byte storage: local filesystem or an S3-compatible bucket.

Stored ``image_url`` values keep their historical ``/uploads/issues/<name>``
form in both modes. That keeps existing database rows, the frontend
``mediaUrl`` helper and the authenticated media route working unchanged —
only the bytes move.

``boto3`` is imported lazily so local/dev installs that never enable object
storage do not need it at import time.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import mimetypes
import time
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.shared.uploads import MAX_UPLOAD_BYTES

_LOCAL_ROOT = Path("uploads")

# A presigned PUT is short-lived: the browser gets a URL it can use for a few
# minutes, not a permanent write credential for the bucket.
PRESIGN_EXPIRES_IN = 15 * 60


class UploadNotFoundError(FileNotFoundError):
    """The requested object does not exist in the configured backend."""


class UploadTokenError(ValueError):
    """The direct-upload handoff token is missing, stale, or forged."""


def object_key(image_url: str) -> str:
    """Turn a stored URL into a bucket key.

    ``/uploads/issues/x.jpg`` and ``issues/x.jpg`` both become ``issues/x.jpg``.
    Segments are validated here as well as in the media route so a bad value
    can never be used as a storage key.
    """
    key = image_url.strip().lstrip("/")
    if key.startswith("uploads/"):
        key = key[len("uploads/") :]
    parts = [p for p in key.split("/") if p and p != "."]
    if not parts or any(p == ".." or "\\" in p or "\0" in p for p in parts):
        raise ValueError("Invalid upload key.")
    return "/".join(parts)


def _s3_client() -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_ENDPOINT_URL_S3,
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        # Neon Object Storage uses path-style addressing only.
        config=Config(s3={"addressing_style": "path"}),
    )


def _local_path(key: str) -> Path:
    root = _LOCAL_ROOT.resolve()
    target = (root / Path(*key.split("/"))).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Invalid upload key.")
    return target


async def put_upload(image_url: str, content: bytes, *, content_type: str | None = None) -> None:
    """Store upload bytes and leave the stored URL unchanged."""
    key = object_key(image_url)
    if settings.STORAGE_BACKEND == "s3":
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        else:
            guessed = mimetypes.guess_type(key)[0]
            if guessed and not guessed.startswith("text/"):
                extra["ContentType"] = guessed
        client = _s3_client()
        await asyncio.to_thread(
            lambda: client.put_object(
                Bucket=settings.NEON_STORAGE_BUCKET,
                Key=key,
                Body=content,
                **extra,
            )
        )
        return

    target = _local_path(key)

    def _write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    await asyncio.to_thread(_write)


async def get_upload(image_url: str) -> bytes:
    """Read upload bytes back. Raises ``UploadNotFoundError`` when absent."""
    key = object_key(image_url)
    if settings.STORAGE_BACKEND == "s3":
        client = _s3_client()
        try:
            response = await asyncio.to_thread(lambda: client.get_object(Bucket=settings.NEON_STORAGE_BUCKET, Key=key))
        except Exception as exc:
            response_meta = getattr(exc, "response", None)
            error = response_meta.get("Error", {}) if isinstance(response_meta, dict) else {}
            if str(error.get("Code", "")) in {"NoSuchKey", "404", "NotFound"}:
                raise UploadNotFoundError(key) from exc
            raise
        return await asyncio.to_thread(response["Body"].read)

    target = _local_path(key)
    if not target.is_file():
        raise UploadNotFoundError(key)
    return await asyncio.to_thread(target.read_bytes)


async def get_upload_bounded(image_url: str, *, limit: int = MAX_UPLOAD_BYTES + 1) -> bytes:
    """Read at most ``limit`` bytes from storage.

    Direct uploads are validated *after* the browser PUTs them, so the object in
    the bucket is untrusted. Reading it with ``get_upload`` pulled the whole
    object into worker memory before ``validate_image`` could reject it. Callers
    pass the cap plus one byte: an oversized object is detected by the existing
    size validation without ever being fully buffered.
    """
    key = object_key(image_url)
    if settings.STORAGE_BACKEND == "s3":
        client = _s3_client()
        try:
            response = await asyncio.to_thread(lambda: client.get_object(Bucket=settings.NEON_STORAGE_BUCKET, Key=key))
        except Exception as exc:
            response_meta = getattr(exc, "response", None)
            error = response_meta.get("Error", {}) if isinstance(response_meta, dict) else {}
            if str(error.get("Code", "")) in {"NoSuchKey", "404", "NotFound"}:
                raise UploadNotFoundError(key) from exc
            raise
        return await asyncio.to_thread(lambda: response["Body"].read(limit))

    target = _local_path(key)
    if not target.is_file():
        raise UploadNotFoundError(key)

    def _read() -> bytes:
        with target.open("rb") as handle:
            return handle.read(limit)

    return await asyncio.to_thread(_read)


async def delete_upload(image_url: str) -> None:
    """Best-effort removal of an upload that failed to be persisted."""
    key = object_key(image_url)
    if settings.STORAGE_BACKEND == "s3":
        client = _s3_client()
        await asyncio.to_thread(lambda: client.delete_object(Bucket=settings.NEON_STORAGE_BUCKET, Key=key))
        return

    target = _local_path(key)
    await asyncio.to_thread(target.unlink, missing_ok=True)


def validate_declared_size(size: int | None) -> None:
    """Reject an obviously oversized file before producing a presigned URL."""
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise ValueError(f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")


def presign_put_upload(image_url: str, *, content_type: str | None = None) -> dict[str, Any]:
    """Create a short-lived S3 PUT URL for one exact object key.

    The browser sends the file straight to Neon Object Storage. Only a few KB
    of JSON cross the Vercel BFF, so the platform's request-body cap no longer
    limits photo size. The signed Content-Type must be sent verbatim by the
    client or S3 rejects the PUT.
    """
    if settings.STORAGE_BACKEND != "s3":
        raise RuntimeError("Direct uploads require STORAGE_BACKEND=s3.")

    params: dict[str, Any] = {
        "Bucket": settings.NEON_STORAGE_BUCKET,
        "Key": object_key(image_url),
    }
    if content_type:
        params["ContentType"] = content_type

    url = _s3_client().generate_presigned_url(
        "put_object",
        Params=params,
        ExpiresIn=PRESIGN_EXPIRES_IN,
    )
    return {"url": url, "expires_in": PRESIGN_EXPIRES_IN, "content_type": content_type}


def _token_message(image_url: str, user_id: int, purpose: str, expires_at: int) -> str:
    return f"{object_key(image_url)}|{user_id}|{purpose}|{expires_at}"


def create_upload_token(image_url: str, user_id: int, purpose: str) -> str:
    """Sign the (key, user, purpose, expiry) handoff for a direct upload."""
    expires_at = int(time.time()) + PRESIGN_EXPIRES_IN
    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        _token_message(image_url, user_id, purpose, expires_at).encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{expires_at}.{signature}"


def verify_upload_token(token: str, image_url: str, user_id: int, purpose: str) -> None:
    """Fail unless the token was issued for this exact key/user/purpose."""
    try:
        expires_at_raw, signature = token.split(".", 1)
        expires_at = int(expires_at_raw)
    except (AttributeError, ValueError) as exc:
        raise UploadTokenError("Invalid upload token.") from exc

    if expires_at < int(time.time()):
        raise UploadTokenError("Upload token expired. Please retry the upload.")

    expected = hmac.new(
        settings.SECRET_KEY.encode(),
        _token_message(image_url, user_id, purpose, expires_at).encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise UploadTokenError("Invalid upload token.")
