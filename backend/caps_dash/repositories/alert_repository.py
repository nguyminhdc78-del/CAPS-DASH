"""Database access for operational alerts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..db.models import Alert


def get_by_id(session: Session, alert_id: int) -> Alert | None:
    return session.get(Alert, alert_id)


def get_latest_by_key(
    session: Session, *, alert_type: str, entity_type: str, entity_id: str
) -> Alert | None:
    """The newest alert for one `(type, entity)` key, whatever its ack state.

    `alert_service.create_deduplicated` uses this for both halves of
    deduplication: an unacknowledged result means the issue is still open (no
    new alert needed at all), and its `created_at` drives the cooldown check
    when it is already acknowledged.
    """
    stmt = (
        select(Alert)
        .where(
            Alert.alert_type == alert_type,
            Alert.entity_type == entity_type,
            Alert.entity_id == entity_id,
        )
        .order_by(Alert.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def build_list_query(
    *,
    acknowledged: bool | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
) -> Select[Any]:
    """Unexecuted statement, open alerts first then newest first.

    Matches the `ix_alerts_open_recent` index on `(acknowledged_at,
    created_at)`: ordering by "is open" descending puts every row where
    `acknowledged_at IS NULL` (True) ahead of acknowledged ones, then newest
    first within each group.
    """
    stmt = select(Alert)
    if acknowledged is not None:
        stmt = stmt.where(
            Alert.acknowledged_at.is_not(None) if acknowledged else Alert.acknowledged_at.is_(None)
        )
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    return stmt.order_by(Alert.acknowledged_at.is_(None).desc(), Alert.created_at.desc())
