"""Plate-search schemas for the authenticated `/api/plates/search` route.

Kept apart from `slot_schemas` for the same reason the summary schemas are:
these carry a plate number, which identifies a vehicle and through it a
person, and a route that returns one should be obviously distinguishable from
a route that returns an occupancy count. An authenticated-only endpoint must
never be able to reach for one of these by accident.

The public kiosk uses a narrower projection (`public_kiosk_schemas.PublicPlateSchema`)
that returns only `{plate, slot_code, floor, read_at}` - no `camera_id`,
`camera_code`, `confidence`, or `plate_width_px`.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class PlateMatchResponse(BaseModel):
    """One car and the bay it is in."""

    model_config = ConfigDict(from_attributes=True)

    plate: str
    slot_code: str
    floor: str
    camera_id: int
    camera_code: str
    slot_state: str
    read_at: dt.datetime

    # Returned so the guard can weigh the answer rather than take it on faith.
    # A plate read at 62 px with 0.31 confidence is a lead to check, not a
    # fact; one read at 150 px with 0.91 is worth walking to. Hiding these
    # would make the two look identical on screen.
    confidence: float = Field(description="Detector confidence in the plate, 0-1")
    plate_width_px: int = Field(description="How wide the plate was, in pixels")


class PlateSearchResponse(BaseModel):
    query: str = Field(description="The normalised query actually searched for")
    matches: list[PlateMatchResponse]
