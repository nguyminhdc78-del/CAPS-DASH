"""Periodic background jobs: aggregation, alerts and housekeeping.

Each job module exposes a plain sync `run(...)` callable; `interval_scheduler.
JobScheduler` is what turns a list of those into asyncio tasks with their own
interval, wired up in `lifespan.py`.
"""

from __future__ import annotations
