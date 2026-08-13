"""Serving the built single-page app.

Mounted LAST, at `/`, so it never shadows the API. Deep links such as
`/cameras/01` must return `index.html` rather than 404, but a missing
`/api/...` path must return an error envelope - that split is handled by
catch-all API routes registered before this mount.
"""

from __future__ import annotations

from pathlib import Path, PurePath

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from ..config.settings import Settings
from ..observability.logging_setup import get_logger

logger = get_logger(__name__)

# Vite fingerprints everything under assets/ with a content hash, so a given
# URL's bytes never change and a year is as safe as a minute.
ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"

# index.html is the one unhashed file, and it is what names the current
# bundle. Without a header a browser applies its own heuristic - roughly a
# tenth of the file's age - and keeps serving the previous app for hours after
# a deploy. `no-cache` still allows the ETag round trip; it forbids guessing.
SHELL_CACHE_CONTROL = "no-cache, must-revalidate"


class SpaStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as missing:
            if missing.status_code != 404:
                raise
            # A client-side route, not a missing asset. Hand back the shell and
            # let the router resolve it.
            #
            # Starlette RAISES 404 rather than returning one, so an
            # `if response.status_code == 404` check here never runs and every
            # deep link falls through to the API error envelope instead. The
            # app still works while a visitor only ever enters at `/` and
            # navigates in the client, which is why this survived: it breaks
            # on refresh and on bookmarks, not on the happy path.
            response = await super().get_response("index.html", scope)

        # `path` arrives already joined with the host's separator - Starlette
        # builds it with `os.path.join`, so it is `assets\app.js` on Windows and
        # `assets/app.js` on the board. Comparing against a literal "assets/"
        # would quietly do the right thing in production and the wrong thing in
        # development, which is the worst way for a caching bug to behave.
        is_asset = PurePath(path).parts[:1] == ("assets",)
        response.headers["Cache-Control"] = (
            ASSET_CACHE_CONTROL if is_asset else SHELL_CACHE_CONTROL
        )
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
