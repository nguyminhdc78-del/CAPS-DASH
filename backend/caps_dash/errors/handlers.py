"""Central exception handling.

One place decides how a failure becomes a response. Tracebacks are logged and
never serialised - an error envelope must not leak SQL, file paths or stack
frames to a browser.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..api.schemas.common_schemas import ErrorBody, ErrorEnvelope
from ..observability.logging_setup import get_logger
from ..observability.request_context import get_request_id
from .codes import ErrorCode
from .exceptions import AppError, RateLimitedError

logger = get_logger(__name__)

# Status codes that map onto a specific code when raised as a bare HTTPException.
_STATUS_TO_CODE = {
    401: ErrorCode.AUTH_REQUIRED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.RATE_LIMITED,
}


# Pydantic validator error types that deserve their own code rather than a
# generic VALIDATION_FAILED. Without this a degenerate polygon and a missing
# field are indistinguishable to the client, so the ROI editor cannot tell the
# operator *what* is wrong with the shape they just drew.
_PYDANTIC_TYPE_TO_CODE = {
    "polygon_degenerate": ErrorCode.POLYGON_DEGENERATE,
}


def _specific_code_for(errors: Sequence[Any]) -> ErrorCode:
    """First recognised validator type wins; otherwise the generic code."""
    for error in errors:
        code = _PYDANTIC_TYPE_TO_CODE.get(str(error.get("type", "")))
        if code is not None:
            return code
    return ErrorCode.VALIDATION_FAILED


def build_envelope(
    code: ErrorCode | str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=str(code),
            message=message,
            request_id=get_request_id(),
            details=dict(details or {}),
        )
    )
    return envelope.model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler. Order does not matter; FastAPI dispatches by type."""

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        # Expected failures are warnings, not errors: they are the system
        # working as designed. Logging them at error level trains operators
        # to ignore the error level.
        logger.warning(
            "app_error",
            code=str(exc.code),
            status_code=exc.status_code,
            detail=exc.message,
        )
        headers: dict[str, str] = {}
        if isinstance(exc, RateLimitedError) and exc.retry_after_s is not None:
            headers["Retry-After"] = str(exc.retry_after_s)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_envelope(exc.code, exc.message, exc.details),
            headers=headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        fields = {
            ".".join(str(part) for part in error["loc"][1:]) or "body": error["msg"]
            for error in errors
        }
        code = _specific_code_for(errors)
        logger.warning("validation_failed", code=str(code), fields=sorted(fields))
        return JSONResponse(
            status_code=422,
            content=build_envelope(code, "Request payload failed validation", {"fields": fields}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = str(exc.detail) if exc.detail else str(code)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_envelope(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Full traceback to the log, generic message to the caller.
        logger.exception("unhandled_exception", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=build_envelope(
                ErrorCode.INTERNAL_ERROR, "Internal server error. Check logs with this request_id."
            ),
        )
