"""Periodic job: alert when free disk space drops below the low-space
thresholds (`alert_rules.disk_severity` - both a percentage and an absolute
floor, since a percentage alone misfires on a small flash card).

Registered on the scheduler every 15 minutes.
"""

from __future__ import annotations

import shutil

from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import Settings
from ..db.enums import AlertType
from ..db.session import session_scope
from ..db.types import utc_now
from ..services import alert_rules, alert_service, system_service


def run(factory: sessionmaker[Session], settings: Settings) -> None:
    usage = shutil.disk_usage(system_service.database_directory(settings))
    severity = alert_rules.disk_severity(
        free_bytes=usage.free, total_bytes=usage.total, settings=settings
    )
    if severity is None:
        return

    free_mib = usage.free / (1024 * 1024)
    with session_scope(factory) as session:
        alert_service.create_deduplicated(
            session,
            alert_type=AlertType.DISK_LOW,
            entity_type="disk",
            entity_id="data",
            severity=severity,
            message_code="alert.disk_low",
            message=f"Free disk space is low: {free_mib:.0f} MiB free",
            details={
                "free_bytes": usage.free,
                "total_bytes": usage.total,
                "free_mib": round(free_mib, 1),
            },
            settings=settings,
            now=utc_now(),
        )
