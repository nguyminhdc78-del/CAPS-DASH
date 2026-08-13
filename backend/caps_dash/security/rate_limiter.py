"""Sliding-window event counter, used for login failures and for public
request throttling.

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
    """Counts events per key within a moving time window."""

    def __init__(
        self,
        max_attempts: int,
        window_s: float,
        clock: Callable[[], float] = time.monotonic,
        message: str = "Too many failed attempts. Try again later.",
    ) -> None:
        self._max_attempts = max_attempts
        self._window_s = window_s
        # Injectable so tests can step time exactly instead of sleeping.
        # Sleeping past a short window is unreliable on Windows, where the
        # timer granularity is coarse enough to make the margin a coin flip.
        self._clock = clock
        # Shown to the caller on lockout. Defaults to the login wording;
        # public throttling passes its own so the message a customer sees
        # never claims a "failed attempt" for a search that simply succeeded
        # too many times.
        self._message = message
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Raise if this key is currently locked out."""
        with self._lock:
            events = self._prune(key)
            if len(events) >= self._max_attempts:
                oldest = events[0]
                retry_after = int(self._window_s - (self._clock() - oldest)) + 1
                raise RateLimitedError(
                    self._message,
                    retry_after_s=max(retry_after, 1),
                )

    def record(self, key: str) -> None:
        """Count one event against this key."""
        with self._lock:
            self._prune(key)
            self._events[key].append(self._clock())

    def try_acquire(self, key: str) -> None:
        """Check and count in one step. Raises if the key is over budget.

        `check()` then `record()` takes the lock twice, so N threads can all
        pass the check before any of them records - admitting well over the
        budget under a burst. Sync handlers run in a threadpool, so that race
        is reachable from concurrent requests, and on the public search it
        erodes the only throttle standing between an anonymous caller and the
        plate database.

        Login keeps `check`/`record`/`reset`: there the two steps are
        deliberately separate, because a *successful* login calls `reset()`
        instead of `record()`, and an over-budget attempt must not count
        itself again.
        """
        with self._lock:
            events = self._prune(key)
            if len(events) >= self._max_attempts:
                oldest = events[0]
                retry_after = int(self._window_s - (self._clock() - oldest)) + 1
                raise RateLimitedError(self._message, retry_after_s=max(retry_after, 1))
            self._events[key].append(self._clock())

    def reset(self, key: str) -> None:
        """Clear a key's history after a genuine success."""
        with self._lock:
            self._events.pop(key, None)

    def sweep_idle(self) -> int:
        """Drop keys with no recent events. Returns how many were removed.

        Without this the dictionary grows one entry per distinct username or
        client IP ever attempted, which is unbounded and attacker-controlled.
        """
        with self._lock:
            stale = [key for key in list(self._events) if not self._prune(key)]
            for key in stale:
                self._events.pop(key, None)
            return len(stale)

    def _prune(self, key: str) -> deque[float]:
        """Drop timestamps that have fallen out of the window. Caller holds the lock."""
        cutoff = self._clock() - self._window_s
        events = self._events[key]
        while events and events[0] < cutoff:
            events.popleft()
        return events


def user_key(username: str) -> str:
    return f"user:{username.strip().lower()}"


def ip_key(client_ip: str) -> str:
    return f"ip:{client_ip}"
