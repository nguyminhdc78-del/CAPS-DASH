"""JWT encoding and decoding.

PyJWT, HS256. Symmetric is right here: one process issues and verifies every
token, so there is no second party needing a public key, and asymmetric keys
would add operational work for no gain.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import jwt

from ..config.settings import Settings
from ..errors.codes import ErrorCode
from ..errors.exceptions import AuthError

ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str
    token_type: TokenType
    token_version: int
    role: str = ""
    jti: str = ""
    expires_at: dt.datetime | None = None


def encode_access(settings: Settings, *, username: str, role: str, token_version: int) -> str:
    now = dt.datetime.now(dt.UTC)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "tv": token_version,
        "typ": "access",
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.access_token_ttl_min),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def encode_refresh(
    settings: Settings, *, username: str, token_version: int, jti: str | None = None
) -> tuple[str, str, dt.datetime]:
    """Return (token, jti, expires_at). The jti is what the session row stores."""
    now = dt.datetime.now(dt.UTC)
    expires_at = now + dt.timedelta(days=settings.refresh_token_ttl_days)
    token_id = jti or uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": username,
        "tv": token_version,
        "jti": token_id,
        "typ": "refresh",
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)
    return token, token_id, expires_at


def decode_token(settings: Settings, token: str, *, expected_type: TokenType) -> TokenClaims:
    """Decode and validate, or raise AuthError with a precise code.

    `expected_type` is not optional on purpose. Accepting either kind would
    let a long-lived refresh token be replayed as a bearer credential - the
    classic token-confusion bug, and the reason `typ` is a required claim.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired", code=ErrorCode.AUTH_TOKEN_EXPIRED) from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Token is not valid", code=ErrorCode.AUTH_TOKEN_INVALID) from exc

    if payload.get("typ") != expected_type:
        raise AuthError(
            "Wrong token type for this endpoint",
            code=ErrorCode.AUTH_TOKEN_TYPE_MISMATCH,
        )

    return TokenClaims(
        subject=str(payload["sub"]),
        token_type=expected_type,
        token_version=int(payload.get("tv", 0)),
        role=str(payload.get("role", "")),
        jti=str(payload.get("jti", "")),
        expires_at=dt.datetime.fromtimestamp(payload["exp"], tz=dt.UTC),
    )
