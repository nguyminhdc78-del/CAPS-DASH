"""Settings must load from a real `.env` file, not just from keyword arguments.

Every other test builds `Settings(cors_origins=[...])` in Python, which skips
the settings *sources* entirely. That gap hid a production-blocking bug:
pydantic-settings JSON-decodes complex-typed fields as it reads the dotenv
file, before any validator runs, so the `CORS_ORIGINS=https://parking.local`
documented in `.env.example` and `deploy/caps-dash.env.example` raised
SettingsError. In prod the field is mandatory, so following the shipped
deployment guide produced an app that could not start.

These tests load through the file, the way the board does.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from caps_dash.config.settings import Settings

LONG_KEY = "x" * 48


def write_env(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_comma_separated_cors_origins_parse_from_a_dotenv_file(tmp_path: Path):
    """The exact format both shipped env examples document."""
    env = write_env(
        tmp_path,
        f"APP_ENV=dev\nSECRET_KEY={LONG_KEY}\n"
        "CORS_ORIGINS=http://localhost:5173,https://parking.local\n",
    )

    settings = Settings(_env_file=env)  # type: ignore[call-arg]

    assert settings.cors_origins == ["http://localhost:5173", "https://parking.local"]


def test_a_single_origin_parses(tmp_path: Path):
    env = write_env(
        tmp_path, f"APP_ENV=dev\nSECRET_KEY={LONG_KEY}\nCORS_ORIGINS=https://parking.local\n"
    )

    assert Settings(_env_file=env).cors_origins == ["https://parking.local"]  # type: ignore[call-arg]


def test_an_empty_value_is_an_empty_list_not_a_blank_origin(tmp_path: Path):
    env = write_env(tmp_path, f"APP_ENV=dev\nSECRET_KEY={LONG_KEY}\nCORS_ORIGINS=\n")

    assert Settings(_env_file=env).cors_origins == []  # type: ignore[call-arg]


def test_the_shipped_production_env_example_boots(tmp_path: Path):
    """A prod profile written the way `deploy/caps-dash.env.example` shows.

    This is the case that was broken: prod requires a non-empty allowlist, so
    a parse failure here meant the documented deployment could never start.
    """
    env = write_env(
        tmp_path,
        f"APP_ENV=prod\nSECRET_KEY={LONG_KEY}\nCORS_ORIGINS=https://parking.local\n",
    )

    settings = Settings(_env_file=env)  # type: ignore[call-arg]

    assert settings.is_prod
    assert settings.cors_origins == ["https://parking.local"]


def test_prod_still_refuses_a_wildcard_from_a_dotenv_file(tmp_path: Path):
    """Parsing correctly must not weaken the guard it feeds."""
    env = write_env(tmp_path, f"APP_ENV=prod\nSECRET_KEY={LONG_KEY}\nCORS_ORIGINS=*\n")

    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(_env_file=env)  # type: ignore[call-arg]
