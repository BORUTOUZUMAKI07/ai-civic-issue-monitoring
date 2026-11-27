import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.storage import (
    UploadNotFoundError,
    UploadTokenError,
    delete_upload,
    get_upload,
    put_upload,
    verify_upload_token,
)
from src.domains.engineers.repositories.engineer_repository import EngineerRepository
from src.domains.issues.services.issue_service import ALLOWED_EXTENSIONS, IssueService
from src.domains.users.deps import get_current_active_user
from src.domains.users.models.user import User
from src.shared.errors import BadRequestError, InvalidImageError, NotFoundError
from src.shared.uploads import read_upload_bounded

router = APIRouter(prefix="/resolution", tags=["Resolution"])


@router.post("")
async def resolve_issue(
    issue_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
    after_image_url: Optional[str] = Form(None, max_length=255),
    upload_token: Optional[str] = Form(None, max_length=255),
    notes: str = Form("", max_length=2000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)

    # Parse and validate the issue id up front so a bad value cannot leave a
    # freshly written or presigned object stranded in storage.
    try:
        issue_pk = int(issue_id)
    except (TypeError, ValueError):
        raise BadRequestError(detail="issue_id must be an integer.")

    # Authorize BEFORE accepting any image. Object-level ownership is checked
    # inside IssueService.create_resolution too; doing it here as well means a
    # rejected caller never causes an orphaned upload to be written.
    engineer_repo = EngineerRepository(db)
    engineer = await engineer_repo.get_by_user_id(user.id)
    if not engineer:
        raise NotFoundError(detail="Engineer profile not found for this user.")
    await svc.check_resolution_permission(issue_pk, engineer.id)

    if after_image_url is not None:
        if file is not None:
            raise BadRequestError("Provide either file or after_image_url, not both.")
        if not upload_token:
            raise BadRequestError("Missing upload token.")
        try:
            verify_upload_token(upload_token, after_image_url, user.id, "resolution")
        except UploadTokenError as exc:
            raise BadRequestError(str(exc)) from exc
        filename_in = after_image_url.rsplit("/", 1)[-1]
        try:
            content = await get_upload(after_image_url)
        except UploadNotFoundError as exc:
            raise BadRequestError("Uploaded image was not found. Please retry.") from exc
        try:
            svc.validate_image(filename_in, content)
        except Exception:
            try:
                await delete_upload(after_image_url)
            except Exception:  # best-effort cleanup  # nosec B110
                pass
            raise
    else:
        if file is None:
            raise BadRequestError("Provide either file or after_image_url.")
        # Read + validate BEFORE anything touches disk. This handler previously
        # wrote the file first and never validated at all — no extension
        # allowlist, no size cap, no PIL check — so a "photo" could be an .html
        # or .svg that the browser would execute, and every rejected upload
        # left an orphan file behind in a directory that was publicly served.
        # Bounded read: see ``src.shared.uploads`` — never pull a whole spool
        # into memory, whatever the declared length.
        content = await read_upload_bounded(file)
        filename_in = file.filename or "after.jpg"
        svc.validate_image(filename_in, content)

    # Extension comes from the validated name, but is re-checked against the
    # same allowlist rather than trusted, and is forced to lower case so
    # "PhP" style case tricks cannot slip past a set lookup.
    ext = filename_in.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidImageError(f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    if after_image_url is None:
        filename = f"{uuid.uuid4().hex}.{ext}"
        after_image_url = f"/uploads/resolutions/{filename}"
        await put_upload(after_image_url, content)

    try:
        resolution = await svc.create_resolution(
            issue_id=issue_pk,
            engineer_id=engineer.id,
            after_image_url=after_image_url,
            notes=notes,
        )
    except Exception:
        # Do not leave an orphan object behind when the resolution fails.
        try:
            await delete_upload(after_image_url)
        except Exception:  # best-effort cleanup, non-fatal  # nosec B110
            pass
        raise

    return {
        "id": resolution.id,
        "issue_id": resolution.issue_id,
        "status": "resolved",
        "message": f"Issue {issue_pk} resolved successfully.",
        "resolved_at": resolution.resolved_at.isoformat(),
    }
