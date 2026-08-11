"""Deriving parking sessions from `slot_state_history`.

There is deliberately no `parking_session` table (see
`db/models/slot_state_history.py`): a session is two consecutive rows,
OCCUPIED then FREE, for the same slot. This module is the state machine that
walks the ordered rows and turns them into sessions, plus the thin
orchestration `list_sessions` the route calls.

Kept pure and dependency-light on purpose (`derive_sessions` takes a plain
sequence, no `Session`, no settings) - it is the most subtly-wrong-prone piece
of this phase, and a pure function is what makes the edge-case fixtures in
`tests/services/test_session_derivation.py` possible without a database.
"""

from __future__ import annotations

import datetime as dt
import itertools
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..api.pagination import PageParams
from ..config.settings import Settings
from ..db.enums import SlotState
from ..db.models import SlotStateHistory
from ..db.types import utc_now
from ..repositories import session_query_repository
from . import history_service


@dataclass(slots=True)
class DerivedSession:
    """One computed session. See `api/schemas/history_schemas.py` for the
    wire shape this is rendered into."""

    slot_id: int
    camera_code: str
    slot_code: str
    floor: str
    started_at: dt.datetime
    ended_at: dt.datetime | None = None
    ongoing: bool = True
    clock_suspect: bool = False
    had_gap: bool = False

    def duration_seconds(self, *, now: dt.datetime) -> float:
        """Elapsed time; for an ongoing session, measured to `now`."""
        end = self.ended_at or now
        return max((end - self.started_at).total_seconds(), 0.0)


def derive_sessions(rows: Sequence[SlotStateHistory], *, now: dt.datetime) -> list[DerivedSession]:
    """Turn an ordered row stream into sessions, one slot at a time.

    `rows` MUST already be ordered `(slot_id, changed_at, id)` ascending -
    see `session_query_repository.build_ordered_range_query`. `itertools.
    groupby` only groups contiguous runs, so a different ordering silently
    produces one broken "session" per slot instead of one real one per slot.
    """
    sessions: list[DerivedSession] = []
    for _slot_id, slot_rows in itertools.groupby(rows, key=lambda row: row.slot_id):
        sessions.extend(_derive_for_one_slot(list(slot_rows), now=now))
    return sessions


def _derive_for_one_slot(
    rows: Sequence[SlotStateHistory], *, now: dt.datetime
) -> list[DerivedSession]:
    """The state machine from the phase-13 plan, for a single slot's rows.

    * -> OCCUPIED opens a session; OCCUPIED -> FREE closes it.
    OCCUPIED -> UNKNOWN -> OCCUPIED stays ONE session (a camera going
    offline mid-session is not "the car left") but is marked `had_gap` so
    the gap is visible rather than silently bridged. A session still open
    when the row stream ends is reported `ongoing=True, ended_at=None`.
    """
    sessions: list[DerivedSession] = []
    current: DerivedSession | None = None

    for row in rows:
        state = row.new_state
        if state == SlotState.OCCUPIED and current is None:
            current = DerivedSession(
                slot_id=row.slot_id,
                camera_code=row.camera_code,
                slot_code=row.slot_code,
                floor=row.floor,
                started_at=row.changed_at,
                clock_suspect=row.clock_suspect,
            )
        elif state == SlotState.FREE and current is not None:
            current.ended_at = row.changed_at
            current.ongoing = False
            current.clock_suspect = current.clock_suspect or row.clock_suspect
            sessions.append(current)
            current = None
        elif state == SlotState.UNKNOWN and current is not None:
            # The camera lost the slot mid-session. Do not close the
            # session - UNKNOWN means "we don't know", not "the car left" -
            # but mark it: this session's duration bridges a real gap, not
            # continuous observation.
            current.had_gap = True
            current.clock_suspect = current.clock_suspect or row.clock_suspect
        elif state == SlotState.OCCUPIED and current is not None:
            # A redundant OCCUPIED while a session is already open - e.g. a
            # worker restart re-observes the same physical state without an
            # intervening FREE (its `previous_state` resets to UNKNOWN on
            # restart, but `new_state` is unchanged). The session already
            # open owns this occupancy; this must not reset its clock or
            # open a second one.
            current.clock_suspect = current.clock_suspect or row.clock_suspect
        # FREE or UNKNOWN with no session open: nothing to close or mark.
        # Either this row's opening OCCUPIED predates the query window (see
        # `session_query_repository`) or it is a sensor blip with no
        # occupancy to report. Ignored either way.

    if current is not None:
        sessions.append(current)  # still open at the end of the range
    return sessions


def list_sessions(
    session: Session,
    settings: Settings,
    params: PageParams,
    *,
    since: dt.datetime | None,
    until: dt.datetime | None,
    slot_id: int | None,
    camera_code: str | None,
) -> tuple[list[DerivedSession], int]:
    """Newest-first page of derived sessions plus the unfiltered total.

    The mandatory, capped range is the same one `/history` enforces
    (`history_service.resolve_range`) and for the same reason: this reads
    every row in the window to derive sessions, so an unbounded range is an
    unbounded scan of the largest table in the system.
    """
    range_since, range_until = history_service.resolve_range(since, until, settings)
    stmt = session_query_repository.build_ordered_range_query(
        since=range_since, until=range_until, slot_id=slot_id, camera_code=camera_code
    )
    rows = session.execute(stmt).scalars().all()
    sessions = derive_sessions(rows, now=utc_now())
    sessions.sort(key=lambda derived: derived.started_at, reverse=True)

    total = len(sessions)
    page = sessions[params.offset : params.offset + params.limit]
    return page, total
