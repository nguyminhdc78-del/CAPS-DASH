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
