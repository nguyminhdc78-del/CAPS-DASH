"""Schemas shared by every endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """The `error` object inside an error response."""

    code: str = Field(description="Stable machine-readable code; clients localise from this.")
    message: str = Field(description="Developer-facing fallback text. Not for end users.")
    request_id: str = Field(default="", description="Correlates with the server log line.")
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Every non-2xx response has exactly this shape."""

    error: ErrorBody


class OkResponse(BaseModel):
    ok: bool = True


class Page[T](BaseModel):
    """Offset-paginated collection."""

    items: list[T]
    total: int
    limit: int
    offset: int


# Declared once on the aggregate router rather than per route. Without it
# `ErrorEnvelope` never reaches `components.schemas`, and every error branch in
# the generated TypeScript is `any` - which defeats the point of generating
# types from the contract at all.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope, "description": "Malformed request"},
    401: {"model": ErrorEnvelope, "description": "Authentication required or failed"},
    403: {"model": ErrorEnvelope, "description": "Insufficient role"},
    404: {"model": ErrorEnvelope, "description": "No such resource"},
    409: {"model": ErrorEnvelope, "description": "Conflicts with existing data"},
    422: {"model": ErrorEnvelope, "description": "Validation failed"},
    429: {"model": ErrorEnvelope, "description": "Rate limited"},
    500: {"model": ErrorEnvelope, "description": "Unexpected server error"},
}
