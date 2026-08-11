"""`/history` response schema, plus the frozen `/sessions` and CSV export
contracts phase 13 implements.

The `/history` query range is mandatory and capped
(`history_service.resolve_range`): `slot_state_history` is the largest table
in the system, stored on flash behind a CPU shared with every camera loop, so
one unbounded scan would stall all of them behind a single request.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class SlotStateChange(BaseModel):
    """One row of `slot_state_history`, newest-first in the list response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slot_id: int
    camera_code: str
    slot_code: str
    floor: str
    previous_state: str
    new_state: str
    changed_at: dt.datetime
    clock_suspect: bool


class ParkingSessionResponse(BaseModel):
    """A derived session: one OCCUPIED -> FREE pair from `slot_state_history`.

    There is no `parking_session` table (see
    `db/models/slot_state_history.py`) - a session IS two consecutive history
    rows, computed on read. `ended_at` is null for a session still open (no
    matching FREE row yet); `duration_seconds` is still populated for an open
    session, measured to "now" at request time, so the UI can show a live
    running duration rather than a blank cell.

    PHASE-13 ADDITION to the schema phase 07 froze: `ongoing`, `clock_suspect`
    and `had_gap` did not exist on the original contract. They are additive
    (nothing removed or renamed) and necessary to satisfy this phase's own
    requirements - "ongoing badge", "suspect badge" and "flag [suspect rows]
    in the response" - none of which the original three fields could express.
    See phase-13 implementation report for the full justification.
    """

    slot_id: int
    camera_code: str
    slot_code: str
    floor: str
    started_at: dt.datetime
    ended_at: dt.datetime | None
    duration_seconds: float | None
    # No matching FREE row yet - `ended_at` is null and this session is still
    # accumulating duration.
    ongoing: bool
    # True when any row that makes up this session (open, mid-session gap, or
    # close) was written while `db/clock_guard.is_clock_suspect()` was true.
    # Duration statistics should exclude these rather than silently average
    # in a wrong timestamp.
    clock_suspect: bool
    # True when an UNKNOWN row occurred between the opening OCCUPIED and the
    # closing FREE (the camera lost the slot mid-session, e.g. went offline).
    # The session is NOT split - UNKNOWN means "we don't know", not "the car
    # left" - but it is marked rather than silently bridged, per this phase's
    # own edge-case requirement.
    had_gap: bool
