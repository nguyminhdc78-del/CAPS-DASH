"""Application exception hierarchy.

Routes and services raise these; a single handler turns them into the error
envelope. Business logic never builds an HTTP response itself.
"""

from __future__ import annotations

from typing import Any

from .codes import ErrorCode


class AppError(Exception):
    """Base for every expected failure.

    `message` is a human-readable fallback. Clients should key off `code` and
    render their own localised string - the message is for logs and for
    developers hitting the API directly.
    """

    status_code: int = 500
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.message = message or self.code.replace("_", " ").capitalize()
        self.details = details or {}
        super().__init__(self.message)


class ValidationFailedError(AppError):
    status_code = 422
    code = ErrorCode.VALIDATION_FAILED


class NotFoundError(AppError):
    status_code = 404
    code = ErrorCode.NOT_FOUND


class ConflictError(AppError):
    status_code = 409
    code = ErrorCode.CONFLICT


class AuthError(AppError):
    """401 - who are you? Default code covers a plain missing credential."""

    status_code = 401
    code = ErrorCode.AUTH_REQUIRED


class ForbiddenError(AppError):
    """403 - we know who you are, and you may not do this."""

    status_code = 403
    code = ErrorCode.FORBIDDEN


class RateLimitedError(AppError):
    status_code = 429
    code = ErrorCode.RATE_LIMITED

    def __init__(self, message: str | None = None, *, retry_after_s: int | None = None) -> None:
        details = {"retry_after_s": retry_after_s} if retry_after_s is not None else None
        super().__init__(message, details=details)
        self.retry_after_s = retry_after_s


class UpstreamError(AppError):
    """502 - a device we depend on (typically a camera) failed us."""

    status_code = 502
    code = ErrorCode.CAMERA_UNREACHABLE
