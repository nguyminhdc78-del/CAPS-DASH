"""Request-scoped correlation id.

A contextvar rather than a parameter threaded through every call: the worker
threads and service functions that need to log a request id are many layers
below the handler that knows it.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")

REQUEST_ID_HEADER = "X-Request-ID"


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    """Current request id, or an empty string outside a request."""
    return _request_id.get()
