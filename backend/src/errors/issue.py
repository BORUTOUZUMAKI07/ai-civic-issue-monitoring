from src.errors.common import BadRequestError, NotFoundError


class IssueNotFound(NotFoundError):
    def __init__(self):
        super().__init__(detail="Issue not found.")


class InvalidImageError(BadRequestError):
    def __init__(self, detail: str = "Invalid image file."):
        super().__init__(detail=detail)


class ImageTooLargeError(BadRequestError):
    def __init__(self):
        super().__init__(detail="Image exceeds maximum size of 5MB.")


class CorruptedImageError(BadRequestError):
    def __init__(self):
        super().__init__(detail="Corrupted or unreadable image file.")


class LowConfidenceError(BadRequestError):
    def __init__(self, confidence: float):
        super().__init__(detail=f"Classification confidence too low ({confidence:.2f}). Manual review required.")
