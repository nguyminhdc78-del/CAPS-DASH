"""Plate search - the guard's "where did they park?" answered.

SECURITY AND ABOVE ONLY, and every search is written to the audit log (with
`username` and `user_id`).

The gate is the feature's price rather than decoration. A plate number
identifies a vehicle and through it a person, so who may ask and what they
asked has to be answerable later. The authenticated dashboard's promise that
residents are never shown which bay holds which car is still kept and tested
(`tests/api/test_plate_search.py:74`); this route does not break that because
a resident cannot reach it.

A separate, unauthenticated public route (`/api/public/plates/search`) now
exists with rate limiting and anonymous audit. The staff route's own gate is
unchanged and remains the correct enforcement boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...db.enums import AuditAction, UserRole
from ...db.session import get_session
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import audit_service, plate_search_service
from ..schemas.plate_schemas import PlateMatchResponse, PlateSearchResponse

router = APIRouter(prefix="/plates", tags=["Plates"])

SecurityOrAbove = Depends(require_role(UserRole.SECURITY))


@router.get(
    "/search",
    response_model=PlateSearchResponse,
    summary="Find which bay a plate is parked in",
)
def search_plates(
    q: str = Query(min_length=1, description="Plate, or part of one. Separators are ignored."),
    include_vacated: bool = Query(
        default=False,
        description=(
            "Also return bays that have since emptied. Off by default: the "
            "usual question is where a car IS, and sending a guard to a bay "
            "the car has left is worse than returning nothing, because they "
            "will trust it and walk there."
        ),
    ),
    session: Session = Depends(get_session),
    current: CurrentUser = SecurityOrAbove,
) -> PlateSearchResponse:
    normalised = plate_search_service.normalise_query(q)
    matches = plate_search_service.search(session, q, occupied_only=not include_vacated)

    # Recorded even when nothing matched. "Who looked for this plate, and
    # when" is the question an audit of a plate database has to answer, and a
    # search that found nothing was still a search.
    audit_service.record(
        session,
        action=AuditAction.PLATE_SEARCHED,
        username=current.username,
        user_id=current.id,
        entity_type="plate",
        entity_id=normalised,
        after={"matches": len(matches), "include_vacated": include_vacated},
    )
    session.commit()

    return PlateSearchResponse(
        query=normalised,
        matches=[PlateMatchResponse.model_validate(match) for match in matches],
    )
