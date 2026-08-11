"""Read-only, filtered, paginated access to the audit trail.

No dedicated repository: the audit log has exactly one read shape (a filtered
list for the admin screen) and `audit_service.record` already owns every
write, so a second module here would only forward a `select()` untouched.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..api.pagination import PageParams, apply_page, count_rows
from ..db.models import AuditLog


def _build_query(
    *,
    entity_type: str | None,
    entity_id: str | None,
    username: str | None,
    action: str | None,
    since: dt.datetime | None,
    until: dt.datetime | None,
) -> Select[Any]:
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditLog.created_at <= until)
    return stmt.order_by(AuditLog.created_at.desc())


def list_audit_logs(
    session: Session,
    params: PageParams,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    username: str | None = None,
    action: str | None = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> tuple[Sequence[AuditLog], int]:
    """Newest-first page of audit rows plus the unfiltered total."""
    stmt = _build_query(
        entity_type=entity_type,
        entity_id=entity_id,
        username=username,
        action=action,
        since=since,
        until=until,
    )
    total = count_rows(session, stmt)
    rows = session.execute(apply_page(stmt, params)).scalars().all()
    return rows, total
