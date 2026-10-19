"""Hard bounds for incoming request bodies, in one place.

Three layers have to agree on these numbers, which is exactly why they live
here rather than being retyped in each:

* the two upload routes, which read the body into memory;
* ``IssueService.validate_image``, which decodes it with Pillow;
* ``RequestBodyLimitMiddleware``, which refuses an oversized request
  *before* FastAPI parses the body at all.

That last layer is the reason a byte cap inside the handler is not enough on
its own. Starlette spools a file part to a temporary file while parsing, so a
1 GB body has already been written to disk by the time any route-level check
runs — and ``await request.json()``, used by every JSON endpoint, does not
even have a temporary file: it accumulates the entire stream in memory.
Guards are therefore layered:

* the middleware rejects a declared ``Content-Length`` over the relevant
  ceiling with a 413, before parsing begins;
* :func:`read_upload_bounded` reads at most ``MAX_UPLOAD_BYTES + 1`` bytes in
  the handler, which bounds *memory* for clients that send no length at all
  (chunked uploads, a lying header) and for anything that slips past.
"""

from __future__ import annotations

from starlette.datastructures import UploadFile

from src.shared.errors import ImageTooLargeError

# The accepted file size, and the multipart envelope around it (boundary
# markers, part headers) plus the up-to-1 MB text fields the form parser
# allows. Anything larger cannot be a legal request, so it is refused whole.
MAX_FILE_SIZE_MB: int = 5
MAX_UPLOAD_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_UPLOAD_BODY_BYTES: int = MAX_UPLOAD_BYTES + 2 * 1024 * 1024

# Ceiling for every other bodied request (JSON, form-elsewhere). No endpoint
# in this API legitimately accepts more than a few KB, so 1 MB is already
# three orders of magnitude of headroom — and it is what keeps
# ``await request.json()``, which has no limit of its own, from being handed
# an arbitrarily large body by an unauthenticated caller.
MAX_JSON_BODY_BYTES: int = 1024 * 1024

# Decoded pixel ceiling. A 5 MB file is bounded, but the bytes are not: a
# tiny, highly-compressed PNG can declare tens of millions of pixels and cost
# ~3 bytes per pixel once decoded to RGB (48 MP -> ~144 MB), multiplied by
# however many uploads are in flight. 48 MP is the largest photo any current
# phone camera produces, so the cap rejects nothing a real user would send.
MAX_IMAGE_PIXELS: int = 48_000_000

# Exact request paths whose body is an upload. Matched verbatim (not by
# prefix) so a future endpoint is opted *in* rather than silently inheriting
# the limit, and so nothing else is ever rejected by this middleware.
UPLOAD_FORM_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/issues/upload",
        "/api/v1/resolution",
    }
)


async def read_upload_bounded(file: UploadFile, *, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read at most ``limit + 1`` bytes, raising if there is any more.

    The ``+ 1`` is what makes the check possible: a file of exactly ``limit``
    bytes reads back as ``limit`` and is accepted, while anything larger
    returns ``limit + 1`` bytes and is rejected — without the rest of the
    body ever being pulled into memory. ``UploadFile.read`` on Starlette
    backs onto the already-spooled temporary file, so the unread remainder
    stays on disk and is discarded with it when the request finishes.
    """
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise ImageTooLargeError()
    return content
