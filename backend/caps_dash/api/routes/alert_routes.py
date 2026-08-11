"""Alert listing and acknowledgement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...db.enums import AlertSeverity, AlertType, UserRole
from ...db.models import User
from ...db.session import get_session
from ...errors.codes import ErrorCode
from ...errors.exceptions import AuthError
from ...repositories import user_repository
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import alert_service
from ..deps import RequestContext, get_request_context
from ..pagination import PageParams, page_params
from ..schemas.alert_schemas import AlertResponse
from ..schemas.common_schemas import Page

router = APIRouter(prefix="/alerts", tags=["Alerts"])

SecurityOrAbove = Depends(require_role(UserRole.SECURITY))


def _actor(session: Session, current: CurrentUser) -> User:
    """Load the acting account for the audit row. Mirrors `user_routes._actor`."""
    user = user_repository.get_by_id(session, current.id)
    if user is None:
        raise AuthError("Account no longer exists", code=ErrorCode.AUTH_INACTIVE_USER)
    return user


@router.get("", response_model=Page[AlertResponse], summary="List alerts")
def list_alerts(
    acknowledged: bool | None = Query(default=None),
    alert_type: AlertType | None = Query(default=None, alias="type"),
    severity: AlertSeverity | None = Query(default=None),
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
    _: CurrentUser = SecurityOrAbove,
) -> Page[AlertResponse]:
    rows, total = alert_service.list_alerts(
        session, params, acknowledged=acknowledged, alert_type=alert_type, severity=severity
    )
    return Page[AlertResponse](
        items=[AlertResponse.model_validate(row) for row in rows],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/{alert_id}/acknowledge", response_model=AlertResponse, summary="Acknowledge an alert"
)
def acknowledge_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current: CurrentUser = SecurityOrAbove,
    context: RequestContext = Depends(get_request_context),
) -> AlertResponse:
    alert = alert_service.acknowledge(
        session, alert_id, actor=_actor(session, current), client_ip=context.client_ip
    )
    return AlertResponse.model_validate(alert)
