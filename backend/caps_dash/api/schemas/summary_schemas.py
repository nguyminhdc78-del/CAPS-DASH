"""Occupancy summary schemas for the authenticated `/api/summary` endpoint.

The authenticated dashboard's shape IS the privacy boundary: no slot id, no slot
code, no camera id, no polygon - counts only. Which slot holds a car is private,
the way a car park's occupancy board shows "42 free" and never "space B-17 is
empty".

The public kiosk endpoint uses a different schema (`public_kiosk_schemas.py`)
that adds free bay codes and (optionally) plate search. Both responses share the
counts, but the public surface deliberately trades that asymmetry: bay codes are
low-risk (an empty bay holds no car), plate search is high-risk (vehicle
enumeration).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class FloorSummary(BaseModel):
    floor: str
    total: int
    free: int
    occupied: int
    unknown: int


class OccupancySummary(BaseModel):
    """Counts only, aggregated from `parking_slots.current_state`.

    `unknown` is never folded into `free`: a slot the detector cannot currently
    classify (camera offline, still warming up, occluded) is a different fact
    from a slot with no car in it. Merging the two would let a stalled camera
    silently report itself as free parking. The four counts (`total`, `free`,
    `occupied`, `unknown`) are always independent and `free + occupied +
    unknown == total`.
    """

    total: int
    free: int
    occupied: int
    unknown: int
    by_floor: list[FloorSummary]
    updated_at: dt.datetime
