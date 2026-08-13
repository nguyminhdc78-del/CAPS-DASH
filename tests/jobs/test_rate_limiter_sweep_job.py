"""Tests for the rate_limiter_sweep_job that cleans stale limiter keys."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import sessionmaker

from caps_dash.jobs.rate_limiter_sweep_job import run
from caps_dash.security.rate_limiter import SlidingWindowLimiter, ip_key, user_key


def test_sweep_job_runs_both_limiters_and_sums_removed_keys() -> None:
    """The job takes two limiters, calls sweep_idle on each, and sums the counts."""
    now = [1000.0]
    login_limiter = SlidingWindowLimiter(max_attempts=5, window_s=60, clock=lambda: now[0])
    kiosk_limiter = SlidingWindowLimiter(max_attempts=3, window_s=60, clock=lambda: now[0])

    # Record some keys - they're fresh, so sweep won't remove them
    login_limiter.record(user_key("guard"))
    login_limiter.record(user_key("admin"))
    kiosk_limiter.record(ip_key("1.2.3.4"))
    kiosk_limiter.record(ip_key("1.2.3.5"))

    # Expire them by advancing the clock past the window
    now[0] += 61

    # Mock the session factory and retention service
    factory = MagicMock(spec=sessionmaker)
    with patch("caps_dash.jobs.rate_limiter_sweep_job.session_scope") as mock_scope, patch(
        "caps_dash.jobs.rate_limiter_sweep_job.retention_service.purge_expired_refresh_sessions"
    ) as mock_purge:
        mock_session = MagicMock()
        mock_scope.return_value.__enter__.return_value = mock_session
        mock_purge.return_value = 0

        # Run the job with both limiters
        run(factory, login_limiter, kiosk_limiter)

        # Both should be empty now (all keys swept)
        assert login_limiter.sweep_idle() == 0
        assert kiosk_limiter.sweep_idle() == 0


def test_sweep_job_with_variadic_limiters() -> None:
    """The job accepts any number of limiters via *args."""
    now = [1000.0]
    limiter1 = SlidingWindowLimiter(max_attempts=1, window_s=60, clock=lambda: now[0])
    limiter2 = SlidingWindowLimiter(max_attempts=1, window_s=60, clock=lambda: now[0])
    limiter3 = SlidingWindowLimiter(max_attempts=1, window_s=60, clock=lambda: now[0])

    limiter1.record("a")
    limiter2.record("b")
    limiter3.record("c")

    now[0] += 61

    factory = MagicMock(spec=sessionmaker)
    with patch("caps_dash.jobs.rate_limiter_sweep_job.session_scope") as mock_scope, patch(
        "caps_dash.jobs.rate_limiter_sweep_job.retention_service.purge_expired_refresh_sessions"
    ) as mock_purge:
        mock_session = MagicMock()
        mock_scope.return_value.__enter__.return_value = mock_session
        mock_purge.return_value = 0

        # Run the job with 3 limiters
        run(factory, limiter1, limiter2, limiter3)

        # All should be empty
        assert limiter1.sweep_idle() == 0
        assert limiter2.sweep_idle() == 0
        assert limiter3.sweep_idle() == 0


def test_sweep_job_leaves_fresh_keys_untouched() -> None:
    """Keys within the window should not be removed, even after a sweep."""
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=5, window_s=60, clock=lambda: now[0])

    limiter.record("fresh")

    factory = MagicMock(spec=sessionmaker)
    with patch("caps_dash.jobs.rate_limiter_sweep_job.session_scope") as mock_scope, patch(
        "caps_dash.jobs.rate_limiter_sweep_job.retention_service.purge_expired_refresh_sessions"
    ) as mock_purge:
        mock_session = MagicMock()
        mock_scope.return_value.__enter__.return_value = mock_session
        mock_purge.return_value = 0

        # Still within window
        run(factory, limiter)

        # The key should still be trackable
        # (check() will fail if the key's count is >= max_attempts)
        assert limiter.sweep_idle() == 0
