"""Sliding-window rate limiting for login attempts.

In-process, and that is correct here rather than a shortcut: the app runs as
exactly one uvicorn worker by design (see the CLI), so there is no second
process whose counters would need sharing. Adding Redis to a box in a security
room would be one more service to install, monitor and restart.

Thread-safe because FastAPI runs sync handlers in a threadpool.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from ..errors.exceptions import RateLimitedError


class SlidingWindowLimiter:
    """Counts failures per key within a moving time window."""

    def __init__(
        self,
        max_attempts: int,
        window_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_s = window_s
        # Injectable so tests can step time exactly instead of sleeping.
        # Sleeping past a short window is unreliable on Windows, where the
        # timer granularity is coarse enough to make the margin a coin flip.
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Raise if this key is currently locked out."""
        with self._lock:
            attempts = self._prune(key)
            if len(attempts) >= self._max_attempts:
                oldest = attempts[0]
                retry_after = int(self._window_s - (self._clock() - oldest)) + 1
                raise RateLimitedError(
                    "Too many failed attempts. Try again later.",
                    retry_after_s=max(retry_after, 1),
                )

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._prune(key)
            self._failures[key].append(self._clock())

    def reset(self, key: str) -> None:
        """Clear a key's history after a genuine success."""
        with self._lock:
            self._failures.pop(key, None)

    def sweep_idle(self) -> int:
        """Drop keys with no recent failures. Returns how many were removed.

        Without this the dictionary grows one entry per distinct username ever
        tried, which is unbounded and attacker-controlled.
        """
        with self._lock:
            stale = [key for key in list(self._failures) if not self._prune(key)]
            for key in stale:
                self._failures.pop(key, None)
            return len(stale)

    def _prune(self, key: str) -> deque[float]:
        """Drop timestamps that have fallen out of the window. Caller holds the lock."""
        cutoff = self._clock() - self._window_s
        attempts = self._failures[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts


def user_key(username: str) -> str:
    return f"user:{username.strip().lower()}"


def ip_key(client_ip: str) -> str:
    return f"ip:{client_ip}"
