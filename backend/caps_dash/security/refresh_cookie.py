"""The refresh-token cookie.

httpOnly so no script can read it. That is the whole reason the split exists:
the short-lived access token lives in JavaScript memory where an XSS could
steal it and get fifteen minutes, while the long-lived credential sits somewhere
JavaScript cannot reach at all.
"""

from __future__ import annotations

from fastapi import Request, Response

from ..config.settings import Settings

COOKIE_NAME = "caps_refresh"

# Scoped to the refresh endpoints, so the cookie is not attached to every API
# call, every static asset and every websocket handshake.
COOKIE_PATH = "/api/auth"


def set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        # Strict is affordable because the SPA is same-origin with the API.
        # There is no cross-site navigation that needs to arrive authenticated.
        samesite="strict",
        # Local development is plain http; a Secure cookie would simply never
        # be sent and login would appear broken for no visible reason.
        secure=settings.is_prod,
        path=COOKIE_PATH,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    # Attributes must match the ones used when setting it, or the browser
    # keeps the original cookie and logout silently fails to log anyone out.
    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=settings.is_prod,
    )


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)
