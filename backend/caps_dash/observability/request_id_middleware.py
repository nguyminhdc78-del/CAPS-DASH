"""Correlation-id middleware.

Pure ASGI rather than BaseHTTPMiddleware: BaseHTTPMiddleware wraps the
response in an anyio task group, which interferes with long-lived streaming
responses and does not apply cleanly to websocket scopes. This version passes
websocket scopes through while still binding an id for their logs.
"""

from __future__ import annotations

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .request_context import REQUEST_ID_HEADER, new_request_id, set_request_id


class RequestIdMiddleware:
    """Bind a request id to the log context for the life of one exchange."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = incoming or new_request_id()

        set_request_id(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            structlog.contextvars.clear_contextvars()
