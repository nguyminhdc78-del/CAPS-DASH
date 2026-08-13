"""Serving the built app: deep links, and not serving a stale one.

Both of these were broken and neither showed on the happy path. Someone who
enters at `/` and clicks through the sidebar never requests a deep link and
never re-fetches `index.html`, so a dashboard can look completely healthy
while a bookmark 404s and a week-old build is still on screen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from caps_dash.config.settings import Settings
from caps_dash.web.spa_static import mount_spa

SHELL = "<!doctype html><html><body>caps-dash shell</body></html>"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(SHELL, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")

    app = FastAPI()
    settings = Settings(
        app_env="dev",
        secret_key="spa-static-test-signing-key-padded-32",
        database_url=f"sqlite:///{tmp_path / 'spa.db'}",
        spa_dist_dir=dist,
        log_json=False,
    )
    mount_spa(app, settings)
    return TestClient(app)


# --- deep links --------------------------------------------------------------


@pytest.mark.parametrize("route", ["/plates", "/slots", "/cameras/01/live", "/history"])
def test_a_client_route_returns_the_shell(client: TestClient, route: str) -> None:
    """Starlette RAISES its 404 rather than returning one, so a fallback
    written as `if response.status_code == 404` silently never runs and every
    refresh lands on an error envelope instead of the app."""
    response = client.get(route)

    assert response.status_code == 200
    assert "caps-dash shell" in response.text


def test_a_real_asset_is_still_served(client: TestClient) -> None:
    """The fallback must not swallow genuine files - a bundle served as
    index.html is a white screen with no error anywhere."""
    response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert response.text == "console.log(1)"


# --- caching -----------------------------------------------------------------


def test_the_shell_is_never_cached_blind(client: TestClient) -> None:
    """index.html is the one unhashed file and it names the current bundle.
    With no header a browser applies its own heuristic and keeps serving the
    previous app for hours after a deploy - which looks exactly like a deploy
    that did not happen."""
    assert client.get("/").headers["cache-control"] == "no-cache, must-revalidate"


def test_a_client_route_is_not_cached_either(client: TestClient) -> None:
    """The same shell, reached the other way. Caching it under the deep-link
    URL would pin a stale app to whichever page was bookmarked."""
    assert client.get("/plates").headers["cache-control"] == "no-cache, must-revalidate"


def test_hashed_assets_are_cached_hard(client: TestClient) -> None:
    """Their URL changes when their content does, so revalidating them is a
    round trip that can never find anything new - and this dashboard is served
    off the same small board it monitors, where the round trip is the
    expensive part."""
    cache_control = client.get("/assets/index-abc123.js").headers["cache-control"]

    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control
