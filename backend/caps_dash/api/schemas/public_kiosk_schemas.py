"""Public kiosk response schemas.

This is the whole contract for what an anonymous passer-by at the lobby
kiosk may see: aggregate occupancy counts, the codes of FREE bays (never
occupied ones), and - when a plate search matches - the four fields a
customer needs to find their own car. Nothing here names a detector, a
camera, a confidence score, or a pixel measurement.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from .summary_schemas import OccupancySummary

# Mirrors plate_search_service.MAX_RESULTS' intent: enough codes to be
# useful on a lobby screen, few enough that a large floor cannot dump its
# entire slot map into one public response.
MAX_FREE_CODES_PER_FLOOR = 40


class PublicOccupancySummary(BaseModel):
    """Counts (reused verbatim, never widened) plus the codes of empty bays."""

    counts: OccupancySummary
    # Truncated to MAX_FREE_CODES_PER_FLOOR per floor. The client detects
    # truncation itself by comparing len(codes) against counts.by_floor[].free
    # for that floor - deliberately no separate "truncated" flag that could
    # drift out of sync with the cap.
    free_codes_by_floor: dict[str, list[str]]
    plate_search_enabled: bool


class PublicPlateMatch(BaseModel):
    """One car and the bay it is in - nothing a customer cannot act on.

    Deliberately absent, compared to the staff-only `PlateMatchResponse`:
    `camera_id`, `camera_code`, `confidence`, `plate_width_px`. A customer
    cannot weigh detector confidence or act on a camera id, and
    `camera_code` is a live-view route key a stranger has no business
    holding.
    """

    plate: str
    slot_code: str
    floor: str
    read_at: dt.datetime


class PublicPlateSearchResponse(BaseModel):
    query: str
    matches: list[PublicPlateMatch]
