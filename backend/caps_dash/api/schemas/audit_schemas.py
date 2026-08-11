"""Audit log response schema. Read-only, admin-only (see `audit_routes.py`)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    username: str
    action: str
    entity_type: str
    entity_id: str
    before_json: dict[str, Any] | None
    after_json: dict[str, Any] | None
    client_ip: str
    request_id: str
    created_at: dt.datetime
    clock_suspect: bool
