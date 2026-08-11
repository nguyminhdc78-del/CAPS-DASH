"""Shared route dependencies.

`get_session` lives in `db.session` and is re-exported here so a route module
imports every dependency from one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from ..app_state import AppState
from ..config.settings import Settings
from ..db.session import get_session
from ..services.service_context import ServiceContext

__all__ = [
    "RequestContext",
    "ServiceContext",
    "get_app_state",
    "get_request_context",
    "get_service_context",
    "get_session",
    "get_settings_dep",
]


@dataclass(slots=True, frozen=True)
class RequestContext:
    """Who is calling and which log line this request will appear in."""

    request_id: str
    client_ip: str


def get_app_state(request: Request) -> AppState:
    state: AppState = request.app.state.caps
    return state


def get_settings_dep(request: Request) -> Settings:
    return get_app_state(request).settings


def get_request_context(request: Request) -> RequestContext:
    """Correlation data for audit rows.

    The request id is set by the logging middleware; the client IP prefers the
    socket address. `X-Forwarded-For` is deliberately ignored - it is
    caller-controlled, and a forged value in an audit row is worse than a
    proxy IP repeated on every row.
    """
    request_id = getattr(request.state, "request_id", "") or ""
    client_ip = request.client.host if request.client else ""
    return RequestContext(request_id=request_id, client_ip=client_ip)


def get_service_context(
    request: Request, context: RequestContext = Depends(get_request_context)
) -> ServiceContext:
    """Everything a mutating service needs beyond its own arguments."""
    state = get_app_state(request)
    return ServiceContext(
        settings=state.settings,
        request_id=context.request_id,
        client_ip=context.client_ip,
        reload_signals=state.services.get("reload_signals"),
        supervisor=state.supervisor,
        hub=state.hub,
    )
