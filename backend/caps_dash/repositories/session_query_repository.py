"""Database access for `GET /sessions` - rows to derive sessions from.

Sessions are not stored; they are two consecutive `slot_state_history` rows
(see `db/models/slot_state_history.py`). This module only shapes the read
that feeds `services/session_derivation_service.py`'s state machine: an
ascending, per-slot-grouped stream of rows for a bounded range. The service
owns turning that stream into sessions; this module owns nothing but the
`select()`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Select, select

from ..db.models import SlotStateHistory


def build_ordered_range_query(
    *,
    since: dt.datetime,
    until: dt.datetime,
    slot_id: int | None = None,
    camera_code: str | None = None,
) -> Select[Any]:
    """Unexecuted statement: oldest-first, grouped by slot.

    Ordering is `(slot_id, changed_at, id)` rather than `changed_at` alone -
    the derivation service walks one slot's rows at a time
    (`itertools.groupby` on `slot_id`), which requires same-slot rows to be
    contiguous. `id` breaks ties between rows sharing a timestamp
    deterministically (two changes can land in the same millisecond on
    SQLite, which has no sub-millisecond resolution to separate them).

    A session whose opening OCCUPIED row is older than `since` is not
    reconstructed - the query has no visibility before the window, same as
    `/history` itself, which never looks outside its own mandatory range. Its
    closing FREE row, if inside the window, is simply not attached to
    anything and produces no session; see `session_derivation_service` for
    the state machine that relies on this being true.
    """
    stmt = select(SlotStateHistory).where(
        SlotStateHistory.changed_at >= since,
        SlotStateHistory.changed_at <= until,
    )
    if slot_id is not None:
        stmt = stmt.where(SlotStateHistory.slot_id == slot_id)
    if camera_code:
        stmt = stmt.where(SlotStateHistory.camera_code == camera_code)
    return stmt.order_by(
        SlotStateHistory.slot_id, SlotStateHistory.changed_at, SlotStateHistory.id
    )
