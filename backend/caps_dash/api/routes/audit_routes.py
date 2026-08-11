"""Audit trail: read-only, admin-only, paginated."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from ...db.enums import AuditAction, UserRole
from ...db.session import get_session
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import audit_query_service
from ..pagination import PageParams, page_params
from ..schemas.audit_schemas import AuditLogResponse
from ..schemas.common_schemas import Page

router = APIRouter(tags=["Audit"])

AdminOnly = Depends(require_role(UserRole.ADMIN))


@router.get("/audit-logs", response_model=Page[AuditLogResponse], summary="Audit trail")
def list_audit_logs(
    entity_type: str | None = Query(default=None, max_length=24),
    entity_id: str | None = Query(default=None, max_length=32),
    username: str | None = Query(default=None, max_length=64),
    action: AuditAction | None = Query(default=None),
    since: AwareDatetime | None = Query(default=None, alias="from"),
    until: AwareDatetime | None = Query(default=None, alias="to"),
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
    _: CurrentUser = AdminOnly,
) -> Page[AuditLogResponse]:
    rows, total = audit_query_service.list_audit_logs(
        session,
        params,
        entity_type=entity_type,
        entity_id=entity_id,
        username=username,
        action=action,
        since=since,
        until=until,
    )
    return Page[AuditLogResponse](
        items=[AuditLogResponse.model_validate(row) for row in rows],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
