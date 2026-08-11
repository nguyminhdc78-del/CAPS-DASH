"""The prod-profile guard in `Settings._refuse_unsafe_production`.

Exercised end to end against the real `Settings` class (not a copy of the
validator's logic) because this is exactly the kind of check that must survive
a refactor: a wildcard CORS origin or a placeholder signing key reaching
production is scout anti-pattern #10, and the whole point of failing fast here
is that it can never ship silently.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from caps_dash.config.settings import Settings

pytestmark = pytest.mark.integration

VALID_SECRET = "a" * 40
VALID_ORIGIN = "https://dash.example.internal"


def test_wildcard_cors_is_rejected_in_prod() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS contains"):
        Settings(app_env="prod", secret_key=VALID_SECRET, cors_origins=["*"])


def test_empty_cors_is_rejected_in_prod() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS is empty"):
        Settings(app_env="prod", secret_key=VALID_SECRET, cors_origins=[])


def test_placeholder_secret_is_rejected_in_prod() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY is unset"):
        Settings(app_env="prod", secret_key="change-me", cors_origins=[VALID_ORIGIN])


def test_short_secret_is_rejected_in_prod() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(app_env="prod", secret_key="too-short", cors_origins=[VALID_ORIGIN])


def test_both_problems_are_reported_together() -> None:
    """One failed start should tell the operator everything wrong at once,
    not make them fix a placeholder secret only to hit the CORS error next."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(app_env="prod", secret_key="change-me", cors_origins=["*"])
    message = str(excinfo.value)
    assert "SECRET_KEY" in message
    assert "CORS_ORIGINS" in message


def test_a_real_prod_configuration_is_accepted() -> None:
    settings = Settings(app_env="prod", secret_key=VALID_SECRET, cors_origins=[VALID_ORIGIN])
    assert settings.is_prod


def test_dev_profile_ignores_wildcard_cors_and_placeholder_secret() -> None:
    """Prod-only: a dev box serving the SPA from the same origin legitimately
    runs with no CORS restriction and the documented placeholder secret."""
    settings = Settings(app_env="dev", cors_origins=["*"])
    assert settings.cors_origins == ["*"]
    assert not settings.is_prod
