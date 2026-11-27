"""Application error hierarchy. Every error carries a plain-language message and,
where possible, a hint telling the user how to fix it (Section 2.3.1)."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 400
    default_code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        hint: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.hint = hint
        self.details = details

    def to_dict(self, request_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            body["hint"] = self.hint
        if self.details is not None:
            body["details"] = self.details
        if request_id:
            body["request_id"] = request_id
        return {"error": body}


class AuthenticationError(AppError):
    status_code = 401
    default_code = "unauthenticated"


class PermissionDeniedError(AppError):
    status_code = 403
    default_code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    default_code = "not_found"


class ConflictError(AppError):
    status_code = 409
    default_code = "conflict"


class ValidationFailedError(AppError):
    status_code = 422
    default_code = "validation_failed"


class RateLimitedError(AppError):
    status_code = 429
    default_code = "rate_limited"


class QuotaExceededError(AppError):
    status_code = 402
    default_code = "quota_exceeded"


class ServiceUnavailableError(AppError):
    status_code = 503
    default_code = "service_unavailable"
