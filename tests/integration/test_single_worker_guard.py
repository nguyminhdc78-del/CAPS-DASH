"""The single-worker runtime guard in `app_factory._reject_multiple_workers`.

Running more than one uvicorn worker is a correctness bug on this system, not
a performance knob: each worker starts its own `CameraSupervisor`, so N
workers means N duplicate polls of every ESP32-CAM, N inference runs, N vote
filters disagreeing about the same slot, and N writers racing for one SQLite
file. `WEB_CONCURRENCY` is checked because it is exactly what uvicorn's own
`--workers` flag defaults to when not passed explicitly, so it is the one
signal visible from inside the ASGI app process.
"""

from __future__ import annotations

import pytest

from caps_dash.app_factory import create_app
from caps_dash.config.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="dev",
        secret_key="single-worker-guard-test-key-0123456789",
        database_url=f"sqlite:///{tmp_path / 'guard.db'}",
        backup_dir=tmp_path / "backups",
        spa_dist_dir=tmp_path / "no-frontend",
        log_json=False,
    )


def test_more_than_one_worker_is_rejected(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeError, match="refuses to run"):
        create_app(settings)


def test_the_guard_applies_in_dev_too(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not a prod-only safety net - N camera loops is wrong in every environment."""
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(RuntimeError, match="WEB_CONCURRENCY=2"):
        create_app(settings)


def test_exactly_one_worker_is_accepted(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    create_app(settings)  # must not raise


def test_no_env_var_is_accepted(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    create_app(settings)  # must not raise


def test_a_non_integer_value_is_rejected_rather_than_silently_ignored(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed value is far more likely to be a typo than an intentional
    override; guessing "probably fine" here would defeat the whole guard."""
    monkeypatch.setenv("WEB_CONCURRENCY", "not-a-number")
    with pytest.raises(RuntimeError, match="not an integer"):
        create_app(settings)
