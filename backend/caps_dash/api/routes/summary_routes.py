"""Occupancy summary. The one endpoint a resident can call."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db.enums import UserRole
from ...db.session import get_session
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import summary_service
from ..schemas.summary_schemas import OccupancySummary

router = APIRouter(prefix="/summary", tags=["Summary"])

ResidentOrAbove = Depends(require_role(UserRole.RESIDENT))


@router.get("", response_model=OccupancySummary, summary="Occupancy counts")
def get_summary(
    session: Session = Depends(get_session), _: CurrentUser = ResidentOrAbove
) -> OccupancySummary:
    return summary_service.get_summary(session)
