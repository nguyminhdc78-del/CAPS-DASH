"""Every alert threshold and cooldown, in one place.

A threshold scattered across job files is a threshold nobody can audit in one
read - this module exists so a reviewer (or an operator tuning the system for
a new site) has exactly one place to look.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..config.settings import Settings
from ..db.enums import AlertSeverity


@dataclass(slots=True, frozen=True)
class DiskThresholds:
    """Both a fraction and an absolute floor, each halved for CRITICAL.

    A percentage alone misfires on a small flash card: 10% of a 64 MB card is
    already an emergency in absolute terms. Checking both catches the case
    the other one misses.
    """

    warning_free_fraction: float
    critical_free_fraction: float
    warning_min_free_bytes: int
    critical_min_free_bytes: int


def disk_thresholds(settings: Settings) -> DiskThresholds:
    min_free_bytes = settings.disk_low_min_free_mb * 1024 * 1024
    return DiskThresholds(
        warning_free_fraction=settings.disk_low_percent,
        critical_free_fraction=settings.disk_low_percent / 2,
        warning_min_free_bytes=min_free_bytes,
        critical_min_free_bytes=min_free_bytes // 2,
    )


def disk_severity(*, free_bytes: int, total_bytes: int, settings: Settings) -> AlertSeverity | None:
    """`None` when disk space is fine; otherwise the severity to raise at."""
    thresholds = disk_thresholds(settings)
    free_fraction = (free_bytes / total_bytes) if total_bytes else 0.0

    if free_fraction < thresholds.critical_free_fraction or free_bytes < (
        thresholds.critical_min_free_bytes
    ):
        return AlertSeverity.CRITICAL
    if free_fraction < thresholds.warning_free_fraction or free_bytes < (
        thresholds.warning_min_free_bytes
    ):
        return AlertSeverity.WARNING
    return None


def overstay_cutoff(settings: Settings, *, now: dt.datetime) -> dt.datetime:
    """A slot `OCCUPIED` since before this instant has overstayed."""
    return now - dt.timedelta(hours=settings.overstay_hours)


def cooldown_elapsed(
    *, last_created_at: dt.datetime | None, settings: Settings, now: dt.datetime
) -> bool:
    """True when enough time has passed since the last alert with this key
    to raise another one. No prior alert always counts as elapsed.
    """
    if last_created_at is None:
        return True
    return (now - last_created_at).total_seconds() >= settings.alert_cooldown_s
