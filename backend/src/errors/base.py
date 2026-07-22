class AppError(Exception):
    def __init__(self, detail: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(detail)
