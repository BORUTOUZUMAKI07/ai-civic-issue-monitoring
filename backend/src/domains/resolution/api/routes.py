import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.domains.engineers.repositories.engineer_repository import EngineerRepository
from src.domains.issues.services.issue_service import ALLOWED_EXTENSIONS, IssueService
from src.domains.users.deps import get_current_active_user
from src.domains.users.models.user import User
from src.shared.errors import BadRequestError, InvalidImageError, NotFoundError
from src.shared.uploads import read_upload_bounded

router = APIRouter(prefix="/resolution", tags=["Resolution"])

UPLOAD_DIR = Path("uploads/resolutions")


@router.post("")
async def resolve_issue(
    issue_id: str = Form(...),
    file: UploadFile = File(...),
    notes: str = Form("", max_length=2000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    svc = IssueService(db)

    # Read + validate BEFORE anything touches disk. This handler previously
    # wrote the file first and never validated at all — no extension allowlist,
    # no size cap, no PIL check — so a "photo" could be an .html or .svg that
    # the browser would execute, and every rejected (or never-processed) upload
    # left an orphan file behind in a directory that was publicly served.
    # Bounded read: see ``src.shared.uploads`` — never pull a whole spool into
    # memory, whatever the declared length.
    content = await read_upload_bounded(file)
    filename_in = file.filename or "after.jpg"
    svc.validate_image(filename_in, content)

    # Parse and validate the issue id up front so a bad value cannot leave a
    # freshly written file stranded on disk.
    try:
        issue_pk = int(issue_id)
    except (TypeError, ValueError):
        raise BadRequestError(detail="issue_id must be an integer.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Extension comes from the validated name, but is re-checked against the
    # same allowlist rather than trusted, and is forced to lower case so
    # "PhP" style case tricks cannot slip past a set lookup.
    ext = filename_in.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidImageError(f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = UPLOAD_DIR / filename
    await asyncio.to_thread(filepath.write_bytes, content)
    after_image_url = f"/uploads/resolutions/{filename}"

    engineer_repo = EngineerRepository(db)
    engineer = await engineer_repo.get_by_user_id(user.id)
    if not engineer:
        # Remove the file we just wrote; the caller is being rejected.
        try:
            filepath.unlink(missing_ok=True)
        except OSError:
            pass
        raise NotFoundError(detail="Engineer profile not found for this user.")

    try:
        resolution = await svc.create_resolution(
            issue_id=issue_pk,
            engineer_id=engineer.id,
            after_image_url=after_image_url,
            notes=notes,
        )
    except Exception:
        # Do not leave an orphan image behind when the resolution fails.
        try:
            filepath.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return {
        "id": resolution.id,
        "issue_id": resolution.issue_id,
        "status": "resolved",
        "message": f"Issue {issue_pk} resolved successfully.",
        "resolved_at": resolution.resolved_at.isoformat(),
    }
