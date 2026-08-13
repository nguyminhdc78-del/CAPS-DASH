"""Composing the public kiosk summary from two already-correct services.

Free bay codes are low-risk: an empty bay holds no car, so listing where
they are tells a stranger nothing about anyone. The plate search living
behind the same kill switch is the part that carries real risk - that
asymmetry is why the two share one flag but the search additionally needs
`plate_reading_enabled` and a per-IP rate limit (both enforced in the route
module, not here), while this summary needs neither.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..api.schemas.public_kiosk_schemas import MAX_FREE_CODES_PER_FLOOR, PublicOccupancySummary
from ..config.settings import Settings
from ..repositories import slot_repository
from . import summary_service


def get_public_summary(session: Session, settings: Settings) -> PublicOccupancySummary:
    """Occupancy counts (reused verbatim) plus FREE bay codes, capped per floor."""
    counts = summary_service.get_summary(session)

    codes_by_floor: dict[str, list[str]] = defaultdict(list)
    for floor, code in slot_repository.list_free_codes_by_floor(session):
        if len(codes_by_floor[floor]) < MAX_FREE_CODES_PER_FLOOR:
            codes_by_floor[floor].append(code)

    return PublicOccupancySummary(
        counts=counts,
        free_codes_by_floor=dict(codes_by_floor),
        # The search affordance is hidden, not shown-returning-nothing, when
        # plate reading is off: with it off there are zero plate_reads rows,
        # so a visible search box would be a promise the backend cannot keep.
        plate_search_enabled=settings.public_kiosk_enabled and settings.plate_reading_enabled,
    )
