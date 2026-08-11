"""Alert listing and acknowledgement."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from ..api.pagination import PageParams, apply_page, count_rows
from ..config.settings import Settings
from ..db.enums import AlertSeverity, AlertType, AuditAction
from ..db.models import Alert, User
from ..db.types import utc_now
from ..errors.codes import ErrorCode
from ..errors.exceptions import NotFoundError
from ..observability.logging_setup import get_logger
from ..repositories import alert_repository
from . import alert_rules, audit_service

logger = get_logger(__name__)


def list_alerts(
    session: Session,
    params: PageParams,
    *,
    acknowledged: bool | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
) -> tuple[Sequence[Alert], int]:
    """Open-first, newest-first page of alerts plus the unfiltered total."""
    stmt = alert_repository.build_list_query(
        acknowledged=acknowledged, alert_type=alert_type, severity=severity
    )
    total = count_rows(session, stmt)
    rows = session.execute(apply_page(stmt, params)).scalars().all()
    return rows, total


def acknowledge(session: Session, alert_id: int, *, actor: User, client_ip: str = "") -> Alert:
    """Mark an alert acknowledged. Idempotent by design.

    A guard's retried click, or two guards clicking the same alert within a
    second of each other, must not surface as an error - the alert ends up
    acknowledged either way. So a second call is a no-op that returns the
    existing row (keeping the FIRST acknowledger on record) rather than a
    `ConflictError`.
    """
    alert = alert_repository.get_by_id(session, alert_id)
    if alert is None:
        raise NotFoundError(f"No alert with id {alert_id}", code=ErrorCode.NOT_FOUND)
    if alert.acknowledged_at is not None:
        return alert

    alert.acknowledged_at = utc_now()
    alert.acknowledged_by_id = actor.id

    audit_service.record(
        session,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        username=actor.username,
        user_id=actor.id,
        entity_type="alert",
        entity_id=str(alert.id),
        after={
            "acknowledged_by": actor.username,
            "acknowledged_at": alert.acknowledged_at.isoformat(),
        },
        client_ip=client_ip,
    )
    session.commit()
    return alert


def create_deduplicated(
    session: Session,
    *,
    alert_type: AlertType,
    entity_type: str,
    entity_id: str,
    severity: AlertSeverity,
    message_code: str,
    message: str,
    settings: Settings,
    details: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> Alert | None:
    """Create an alert unless the same `(type, entity)` key is still open or
    still in cooldown. Returns `None` when the create is skipped.

    Two conditions, either of which skips the write:
    - an unacknowledged alert with this key already exists (it already
      represents the ongoing issue; a camera down for a week must produce
      one alert, not one per job tick), or
    - the most recent alert with this key - open or acknowledged - was
      created less than `settings.alert_cooldown_s` ago (guards the moment
      right after someone acknowledges: the underlying condition may still
      be true on the very next tick).

    Called from job threads without a `User` in scope, so there is no
    `actor` here the way `acknowledge()` has one; the alert itself has no
    "created by" column to fill.
    """
    moment = now or utc_now()
    latest = alert_repository.get_latest_by_key(
        session, alert_type=alert_type, entity_type=entity_type, entity_id=entity_id
    )
    if latest is not None:
        still_open = latest.acknowledged_at is None
        in_cooldown = not alert_rules.cooldown_elapsed(
            last_created_at=latest.created_at, settings=settings, now=moment
        )
        if still_open or in_cooldown:
            return None

    alert = Alert(
        alert_type=alert_type,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        message_code=message_code,
        details_json=details or {},
        message=message,
        created_at=moment,
    )
    session.add(alert)
    session.commit()
    logger.info(
        "alert_created", alert_type=alert_type, entity_type=entity_type, entity_id=entity_id
    )
    return alert
