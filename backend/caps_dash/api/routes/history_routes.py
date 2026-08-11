"""Slot state history: `/history`, derived `/sessions`, and the streaming
CSV export.

`/history`'s range is mandatory and capped by `history_service.resolve_range`:
`slot_state_history` is the largest table in the system, stored on flash
behind a CPU shared with every camera loop, so one unbounded scan would stall
all of them behind a single request. `/sessions` and the CSV export share
that same guard - see `session_derivation_service.py` and
`export_service.py`.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from ...app_state import AppState
from ...config.settings import Settings
from ...db.enums import UserRole
from ...db.session import get_session
from ...db.types import utc_now
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import export_service, history_service, session_derivation_service
from ...services.session_derivation_service import DerivedSession
from ..deps import get_app_state, get_settings_dep
from ..pagination import PageParams, page_params
from ..schemas.common_schemas import Page
from ..schemas.history_schemas import ParkingSessionResponse, SlotStateChange

router = APIRouter(tags=["History"])

SecurityOrAbove = Depends(require_role(UserRole.SECURITY))


@router.get("/history", response_model=Page[SlotStateChange], summary="Slot state changes")
def list_history(
    since: AwareDatetime | None = Query(default=None, alias="from"),
    until: AwareDatetime | None = Query(default=None, alias="to"),
    slot_id: int | None = Query(default=None),
    camera_code: str | None = Query(default=None, max_length=16),
    floor: str | None = Query(default=None, max_length=16),
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    _: CurrentUser = SecurityOrAbove,
) -> Page[SlotStateChange]:
    rows, total = history_service.list_history(
        session,
        settings,
        params,
        since=since,
        until=until,
        slot_id=slot_id,
        camera_code=camera_code,
        floor=floor,
    )
    return Page[SlotStateChange](
        items=[SlotStateChange.model_validate(row) for row in rows],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get(
    "/sessions",
    response_model=Page[ParkingSessionResponse],
    summary="Derived parking sessions",
)
def list_sessions(
    since: AwareDatetime | None = Query(default=None, alias="from"),
    until: AwareDatetime | None = Query(default=None, alias="to"),
    slot_id: int | None = Query(default=None),
    camera_code: str | None = Query(default=None, max_length=16),
    params: PageParams = Depends(page_params),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    _: CurrentUser = SecurityOrAbove,
) -> Page[ParkingSessionResponse]:
    sessions, total = session_derivation_service.list_sessions(
        session, settings, params, since=since, until=until, slot_id=slot_id,
        camera_code=camera_code,
    )
    now = utc_now()
    return Page[ParkingSessionResponse](
        items=[_to_session_response(derived, now=now) for derived in sessions],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def _to_session_response(derived: DerivedSession, *, now: dt.datetime) -> ParkingSessionResponse:
    return ParkingSessionResponse(
        slot_id=derived.slot_id,
        camera_code=derived.camera_code,
        slot_code=derived.slot_code,
        floor=derived.floor,
        started_at=derived.started_at,
        ended_at=derived.ended_at,
        duration_seconds=derived.duration_seconds(now=now),
        ongoing=derived.ongoing,
        clock_suspect=derived.clock_suspect,
        had_gap=derived.had_gap,
    )


@router.get("/exports/history.csv", summary="CSV export of slot state history")
def export_history_csv(
    since: AwareDatetime | None = Query(default=None, alias="from"),
    until: AwareDatetime | None = Query(default=None, alias="to"),
    slot_id: int | None = Query(default=None),
    camera_code: str | None = Query(default=None, max_length=16),
    floor: str | None = Query(default=None, max_length=16),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    state: AppState = Depends(get_app_state),
    _: CurrentUser = SecurityOrAbove,
) -> StreamingResponse:
    # SECURITY: every cell beginning =, +, - or @ is escaped in
    # `export_service.csv_safe` (a slot or camera code shaped like a
    # spreadsheet formula must not run as one when the file is opened -
    # OWASP CWE-1236). The size check runs on THIS request's session, before
    # any bytes are sent, so an over-cap request fails as a normal error
    # response rather than an aborted download.
    export_service.check_export_size(
        session, settings, since=since, until=until, slot_id=slot_id, camera_code=camera_code,
        floor=floor,
    )
    # The streaming generator opens and closes its OWN session against the
    # app's `session_factory` rather than reusing this request's `session` -
    # see `export_service.py`'s module docstring for why: this request's
    # session is closed the instant this function returns, which happens as
    # soon as `StreamingResponse` is constructed, before Starlette actually
    # iterates the generator to send bytes.
    lines = export_service.stream_history_csv(
        state.require_session_factory(),
        settings,
        since=since,
        until=until,
        slot_id=slot_id,
        camera_code=camera_code,
        floor=floor,
    )
    filename = f"history-export-{utc_now():%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(
        lines,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )