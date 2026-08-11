"""Recording who changed what.

Only mutating actions. Logging reads would bury the single question this table
exists to answer: when a slot is reported wrong, who last edited the slot map.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..db.enums import AuditAction
from ..db.models import AuditLog
from ..observability.request_context import get_request_id

# Never written to the audit trail, whatever a caller passes. An audit log is
# read by more people than the database itself, so a leaked hash here is worse
# than one in the users table.
REDACTED_FIELDS = frozenset(
    {"password", "new_password", "current_password", "password_hash", "token", "secret_key"}
)

REDACTED = "[redacted]"


def redact(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        key: (REDACTED if key.lower() in REDACTED_FIELDS else value)
        for key, value in payload.items()
    }


def record(
    session: Session,
    *,
    action: AuditAction,
    username: str = "",
    user_id: int | None = None,
    entity_type: str = "",
    entity_id: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    client_ip: str = "",
) -> AuditLog:
    """Add an audit row to the session. The caller owns the commit.

    Deliberately not committing here: the audit entry and the change it
    describes must land in the same transaction, or a rolled-back change
    leaves behind a record claiming it happened.
    """
    entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before_json=redact(before),
        after_json=redact(after),
        client_ip=client_ip,
        request_id=get_request_id(),
    )
    session.add(entry)
    return entry
