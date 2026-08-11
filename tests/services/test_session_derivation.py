"""`session_derivation_service.derive_sessions` - the state machine that turns
`slot_state_history` rows into sessions, with no database involved.

Rows are plain (unpersisted) `SlotStateHistory` instances built directly,
already ordered `(slot_id, changed_at)` ascending - the contract
`session_query_repository.build_ordered_range_query` guarantees in
production. `id` is left at its default (`None`) throughout: the pure
function never reads it.
"""

from __future__ import annotations

import datetime as dt

from caps_dash.db.enums import SlotState
from caps_dash.db.models import SlotStateHistory
from caps_dash.services.session_derivation_service import derive_sessions

T0 = dt.datetime(2026, 8, 11, 8, 0, 0, tzinfo=dt.UTC)


def _row(
    *,
    slot_id: int = 1,
    minute: float,
    new_state: str,
    previous_state: str = SlotState.UNKNOWN,
    clock_suspect: bool = False,
    camera_code: str = "CAM-A",
    slot_code: str = "A1",
    floor: str = "B1",
) -> SlotStateHistory:
    return SlotStateHistory(
        slot_id=slot_id,
        camera_code=camera_code,
        slot_code=slot_code,
        floor=floor,
        previous_state=previous_state,
        new_state=new_state,
        changed_at=T0 + dt.timedelta(minutes=minute),
        clock_suspect=clock_suspect,
    )


def test_a_closed_session_reports_start_end_and_duration() -> None:
    rows = [
        _row(minute=0, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED),
        _row(minute=30, previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE),
    ]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(hours=2))

    assert len(sessions) == 1
    session = sessions[0]
    assert session.started_at == rows[0].changed_at
    assert session.ended_at == rows[1].changed_at
    assert session.ongoing is False
    assert session.duration_seconds(now=T0 + dt.timedelta(hours=2)) == 30 * 60


def test_ongoing_session_has_no_end_and_duration_measured_to_now() -> None:
    """Edge case: OCCUPIED with no later row - still open at range end."""
    rows = [_row(minute=0, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED)]
    now = T0 + dt.timedelta(minutes=45)

    sessions = derive_sessions(rows, now=now)

    assert len(sessions) == 1
    session = sessions[0]
    assert session.ended_at is None
    assert session.ongoing is True
    # Measured to "now", not left null - the UI shows a live running duration.
    assert session.duration_seconds(now=now) == 45 * 60


def test_unknown_gap_in_the_middle_does_not_split_the_session() -> None:
    """Edge case: the camera loses the slot mid-session (UNKNOWN). UNKNOWN
    means "we don't know", not "the car left" - one session, marked."""
    rows = [
        _row(minute=0, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED),
        _row(minute=10, previous_state=SlotState.OCCUPIED, new_state=SlotState.UNKNOWN),
        _row(minute=20, previous_state=SlotState.UNKNOWN, new_state=SlotState.OCCUPIED),
        _row(minute=30, previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE),
    ]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(hours=1))

    assert len(sessions) == 1  # NOT split into two sessions around the gap
    session = sessions[0]
    assert session.started_at == rows[0].changed_at
    assert session.ended_at == rows[3].changed_at
    assert session.had_gap is True


def test_worker_restart_mid_session_does_not_reset_or_duplicate_it() -> None:
    """Edge case: a worker restart re-observes OCCUPIED without an
    intervening FREE (`previous_state` resets to UNKNOWN on restart, but
    `new_state` is unchanged). Must not open a second session or move
    `started_at`."""
    rows = [
        _row(minute=0, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED),
        # The restart: same physical state re-observed, previous_state reset.
        _row(minute=5, previous_state=SlotState.UNKNOWN, new_state=SlotState.OCCUPIED),
        _row(minute=15, previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE),
    ]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(hours=1))

    assert len(sessions) == 1
    session = sessions[0]
    assert session.started_at == rows[0].changed_at  # NOT the restart's timestamp
    assert session.ended_at == rows[2].changed_at


def test_restart_producing_unknown_to_occupied_opens_a_fresh_session() -> None:
    """Edge case from the phase-13 plan: "a worker restart producing
    UNKNOWN->OCCUPIED without a preceding FREE" - a normal session open,
    since only `new_state == OCCUPIED` gates opening one."""
    rows = [_row(minute=0, previous_state=SlotState.UNKNOWN, new_state=SlotState.OCCUPIED)]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(minutes=10))
    assert len(sessions) == 1
    assert sessions[0].started_at == rows[0].changed_at


def test_rows_written_under_a_suspect_clock_flag_the_whole_session() -> None:
    """Edge case: any row (open, gap or close) written while the clock was
    suspect flags the session, even when other rows in it were not."""
    rows = [
        _row(
            minute=0, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED,
            clock_suspect=True,
        ),
        _row(minute=30, previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE),
    ]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(hours=1))
    assert sessions[0].clock_suspect is True


def test_a_session_with_no_suspect_rows_is_not_flagged() -> None:
    rows = [
        _row(minute=0, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED),
        _row(minute=30, previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE),
    ]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(hours=1))
    assert sessions[0].clock_suspect is False


def test_a_free_row_with_no_open_session_is_ignored_not_an_error() -> None:
    """A close with no matching open in view - e.g. the session's start is
    older than the query window. Must not raise or fabricate a session."""
    rows = [_row(minute=0, previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE)]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(hours=1))
    assert sessions == []


def test_multiple_slots_are_derived_independently() -> None:
    """Rows for two slots, contiguous per slot (the repository's ordering
    contract) - `itertools.groupby` in `derive_sessions` must not bleed one
    slot's state machine into the other's."""
    rows = [
        _row(slot_id=1, minute=0, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED),
        _row(slot_id=1, minute=10, previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE),
        _row(slot_id=2, minute=5, previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED),
    ]
    sessions = derive_sessions(rows, now=T0 + dt.timedelta(hours=1))

    assert {session.slot_id for session in sessions} == {1, 2}
    slot_2 = next(session for session in sessions if session.slot_id == 2)
    assert slot_2.ongoing is True
