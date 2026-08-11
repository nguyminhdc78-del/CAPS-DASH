"""`/stats/hourly`: pre-aggregated occupancy, read from `hourly_stats`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from ...config.settings import Settings
from ...db.enums import ScopeType, UserRole
from ...db.session import get_session
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import stats_service
from ..deps import get_settings_dep
from ..pagination import PageParams, page_params
from ..schemas.common_schemas import Page
from ..schemas.stats_schemas import HourlyStatResponse

router = APIRouter(prefix="/stats", tags=["Stats"])

SecurityOrAbove = Depends(require_role(UserRole.SECURITY))


@router.get(
    "/hourly",
    response_model=Page[HourlyStatResponse],
    summary="Pre-aggregated hourly occupancy",
)
def list_hourly_stats(
    scope_type: ScopeType = Query(default=ScopeType.SITE),
    scope_key: str = Query(default=""),
    since: AwareDatetime | None = Query(default=None, alias="from"),
    until: AwareDatetime | None = Query(default=None, alias="to"),
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    _: CurrentUser = SecurityOrAbove,
) -> Page[HourlyStatResponse]:
    rows, total = stats_service.list_hourly_stats(
        session,
        settings,
        params,
        scope_type=scope_type,
        scope_key=scope_key,
        since=since,
        until=until,
    )
    return Page[HourlyStatResponse](
        items=[HourlyStatResponse.model_validate(row) for row in rows],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
