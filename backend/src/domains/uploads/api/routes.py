"""Short-lived presigned URLs for browser-to-object-storage uploads.

The browser uploads image bytes directly to Neon Object Storage. This endpoint
only issues a signed URL for one random key and signs the handoff token the
issue/resolution routes later verify — no image bytes cross the Vercel BFF.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.storage import (
    create_upload_token,
    presign_put_upload,
    validate_declared_size,
)
from src.domains.users.deps import get_current_active_user
from src.domains.users.models.user import User
from src.shared.errors import BadRequestError
from src.shared.uploads import UPLOAD_CONTENT_TYPES

router = APIRouter(prefix="/uploads", tags=["Uploads"])


class PresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    purpose: Literal["issue", "resolution"]
    size: int | None = Field(default=None, ge=0)
    # When present, the object key is stable for this (user, key, purpose).
    # A retried create then hashes to the same idempotency request even though
    # it had to request a fresh short-lived presigned URL.
    idempotency_key: str | None = Field(default=None, max_length=128)


class PresignResponse(BaseModel):
    method: Literal["PUT"]
    upload_url: str
    image_url: str
    upload_token: str
    required_headers: dict[str, str]
    expires_in: int


@router.post("/presign", response_model=PresignResponse)
async def presign_upload(
    body: PresignRequest,
    user: User = Depends(get_current_active_user),
) -> PresignResponse:
    if settings.STORAGE_BACKEND != "s3":
        # Local development keeps the legacy multipart path. A presigned URL
        # for a local filesystem has no meaning outside the backend process.
        raise HTTPException(status_code=501, detail="Direct uploads require object storage.")

    ext = body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else ""
    content_type = UPLOAD_CONTENT_TYPES.get(ext)
    if content_type is None:
        allowed = ", ".join(sorted(UPLOAD_CONTENT_TYPES))
        raise BadRequestError(f"Invalid file type '{ext}'. Allowed: {allowed}")

    try:
        validate_declared_size(body.size)
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    folder = "issues" if body.purpose == "issue" else "resolutions"
    if body.idempotency_key:
        object_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"civicpulse:{user.id}:{body.purpose}:{body.idempotency_key}",
        ).hex
    else:
        object_id = uuid.uuid4().hex
    image_url = f"/uploads/{folder}/{object_id}.{ext}"
    signed = presign_put_upload(image_url, content_type=content_type)

    return PresignResponse(
        method="PUT",
        upload_url=signed["url"],
        image_url=image_url,
        upload_token=create_upload_token(image_url, user.id, body.purpose),
        required_headers={"Content-Type": content_type},
        expires_in=signed["expires_in"],
    )
