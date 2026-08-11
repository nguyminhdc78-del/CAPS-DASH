"""Liveness and readiness.

Split deliberately: liveness answers "is the process up" and must never touch
the database, or a slow disk turns into a restart loop. Readiness answers
"can it actually serve traffic" and is allowed to check dependencies.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ... import __version__

router = APIRouter(tags=["System"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    app_env: str


class ReadinessComponent(BaseModel):
    name: str
    ready: bool
    detail: str = ""


class ReadinessResponse(BaseModel):
    ready: bool
    components: list[ReadinessComponent]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(request: Request) -> HealthResponse:
    settings = request.app.state.caps.settings
    return HealthResponse(version=__version__, app_env=settings.app_env)


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
def readiness(request: Request) -> ReadinessResponse:
    """Report each dependency separately.

    A single boolean tells an operator that something is wrong but not what;
    naming the failing component is the difference between a two-minute and a
    two-hour diagnosis. Phase 06 appends the camera supervisor here.
    """
    state = request.app.state.caps
    components = [
        ReadinessComponent(
            name="database",
            ready=state.session_factory is not None,
            detail="" if state.session_factory is not None else "not initialised",
        )
    ]
    return ReadinessResponse(
        ready=all(component.ready for component in components),
        components=components,
    )
