"""Serving the built single-page app.

Mounted LAST, at `/`, so it never shadows the API. Deep links such as
`/cameras/01` must return `index.html` rather than 404, but a missing
`/api/...` path must return an error envelope - that split is handled by
catch-all API routes registered before this mount.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from ..config.settings import Settings
from ..observability.logging_setup import get_logger

logger = get_logger(__name__)


class SpaStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            # A client-side route, not a missing asset. Hand back the shell and
            # let the router resolve it.
            return await super().get_response("index.html", scope)
        return response


def mount_spa(app: FastAPI, settings: Settings) -> None:
    """Mount the SPA if it has been built; otherwise log and carry on.

    Backend-only development is a normal state - refusing to start because the
    frontend has not been built yet would be hostile.
    """
    dist: Path = settings.spa_dist_dir
    if not (dist / "index.html").is_file():
        logger.warning(
            "spa_not_mounted",
            reason="no built frontend found",
            expected_dir=str(dist),
            hint="run `npm run build` in frontend/, or ignore during backend-only work",
        )
        return

    app.mount("/", SpaStaticFiles(directory=dist, html=True), name="spa")
    logger.info("spa_mounted", directory=str(dist))
