from src.shared.errors.common import BadRequestError, NotFoundError


class IssueNotFound(NotFoundError):
    def __init__(self):
        super().__init__(detail="Issue not found.")


class InvalidImageError(BadRequestError):
    def __init__(self, detail: str = "Invalid image file."):
        super().__init__(detail=detail)


class ImageTooLargeError(BadRequestError):
    # Two ceilings can trip this — the byte count and the decoded pixel count
    # — so the caller says which one fired. Both are the same *kind* of
    # failure (the upload is too big to accept) and both are 400s.
    def __init__(self, detail: str = "Image exceeds maximum size of 5MB."):
        super().__init__(detail=detail)


class CorruptedImageError(BadRequestError):
    def __init__(self):
        super().__init__(detail="Corrupted or unreadable image file.")
