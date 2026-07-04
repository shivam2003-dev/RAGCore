class AppError(Exception):
    """Base for domain errors mapped to HTTP responses in one exception handler."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "", **context: object) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.context = context


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"


class AuthorizationError(AppError):
    status_code = 403
    code = "forbidden"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class IngestionError(AppError):
    status_code = 422
    code = "ingestion_failed"


class ProviderError(AppError):
    """Upstream embedding/LLM provider failure."""

    status_code = 502
    code = "provider_error"
