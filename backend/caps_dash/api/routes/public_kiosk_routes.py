"""Public kiosk endpoints - no authentication, by design.

These two routes exist so the lobby kiosk can run with nobody logged in.
`GET /public/summary` returns aggregate occupancy counts and the codes of
FREE bays only - never an occupied one, never a camera id, never a polygon.
`GET /public/plates/search` runs the same partial-match search the guard
route uses, restricted to occupied bays, and returns exactly four fields per
match: `plate`, `slot_code`, `floor`, `read_at`.

Both routes 404 with `PUBLIC_KIOSK_DISABLED` when `public_kiosk_enabled` is
false; the search route also 404s the same way when `plate_reading_enabled`
is false, because with it off there are zero `plate_reads` rows and nothing
to search. 404, not 403: a surface that is switched off should not confirm
to an anonymous caller that it exists at all.

The search is rate-limited per client IP (`kiosk_limiter`, built in the
lifespan) and every search is written to the audit log with an anonymous
actor (`username=""`, `user_id=None`) and the caller's IP, including
searches that matched nothing - "who looked for this plate" is the question
an audit of a plate database exists to answer.

**The trade-off, stated plainly, not euphemistically**: a public,
unauthenticated, partial-match plate search means anyone on the network
this kiosk is reachable from can locate any vehicle in the car park by
typing part of its plate. That is an accepted decision, not an oversight -
see `plans/260813-1401-public-customer-kiosk-dashboard/plan.md`, whose
containing assumption is an internal-LAN-only deployment. It is not solved
by this file; it is bounded by it (kill switch, rate limit, audit trail)
and made visible here so nobody discovers it by accident later.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ...config.settings import Settings
from ...db.enums import AuditAction
from ...db.session import get_session
from ...errors.codes import ErrorCode
from ...errors.exceptions import NotFoundError
from ...security.client_ip import client_ip
from ...security.rate_limiter import ip_key
from ...services import audit_service, plate_search_service, public_kiosk_service
from ..schemas.public_kiosk_schemas import (
    PublicOccupancySummary,
    PublicPlateMatch,
    PublicPlateSearchResponse,
)

router = APIRouter(prefix="/public", tags=["Public kiosk"])


def _require_public_kiosk(settings: Settings) -> None:
    """404, not 403: a disabled surface should not confirm it exists."""
    if not settings.public_kiosk_enabled:
        raise NotFoundError(
            "The public kiosk is not enabled on this server",
            code=ErrorCode.PUBLIC_KIOSK_DISABLED,
        )


@router.get(
    "/summary",
    response_model=PublicOccupancySummary,
    summary="Public occupancy counts and FREE bay codes",
)
def get_public_summary(
    request: Request, session: Session = Depends(get_session)
) -> PublicOccupancySummary:
    settings = request.app.state.caps.settings
    _require_public_kiosk(settings)
    return public_kiosk_service.get_public_summary(session, settings)


@router.get(
    "/plates/search",
    response_model=PublicPlateSearchResponse,
    summary="Public partial-match plate search",
)
def search_public_plates(
    request: Request,
    q: str = Query(min_length=1, description="Plate, or part of one. Separators are ignored."),
    session: Session = Depends(get_session),
) -> PublicPlateSearchResponse:
    state = request.app.state.caps
    settings = state.settings
    _require_public_kiosk(settings)
    if not settings.plate_reading_enabled:
        # Nothing to search: zero plate_reads rows exist while reading is off.
        # Same code as the kill switch - the caller does not need a second
        # reason to distinguish, and the frontend hides the search box before
        # either 404 is ever reached.
        raise NotFoundError(
            "Plate reading is not enabled; there is nothing to search",
            code=ErrorCode.PUBLIC_KIOSK_DISABLED,
        )

    ip = client_ip(request)
    key = ip_key(ip)
    limiter = state.services["kiosk_limiter"]
    # One atomic step, not check()-then-record(): taking the lock twice lets
    # concurrent requests all pass the check before any of them records, which
    # admits well over the budget under a burst (sync handlers run in a
    # threadpool, so this is reachable from real traffic). A refused request
    # does not count itself, and there is deliberately no reset() - this is a
    # request-rate throttle, not a failure lockout, so a *successful* search
    # still spends budget like every other one.
    limiter.try_acquire(key)

    normalised = plate_search_service.normalise_query(q)
    matches = plate_search_service.search(session, q, occupied_only=True)

    # Written after the search and before commit, mirroring the staff route -
    # even when matches is empty, because a fruitless search was still a
    # search. username="" and user_id=None mark it anonymous; client_ip is
    # what stands in for identity here.
    audit_service.record(
        session,
        action=AuditAction.PLATE_SEARCHED,
        username="",
        user_id=None,
        entity_type="plate",
        entity_id=normalised,
        after={"public": True, "matches": len(matches)},
        client_ip=ip,
    )
    session.commit()

    return PublicPlateSearchResponse(
        query=normalised,
        matches=[
            # Explicit field construction, never model_validate: this is what
            # guarantees a future field added to PlateMatch (confidence,
            # camera_id, ...) cannot leak into a public response by accident.
            # Each field below is a deliberate choice, not "whatever the
            # source object happens to carry".
            PublicPlateMatch(
                plate=match.plate,
                slot_code=match.slot_code,
                floor=match.floor,
                read_at=match.read_at,
            )
            for match in matches
        ],
    )
