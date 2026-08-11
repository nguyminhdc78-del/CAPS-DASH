"""Streaming CSV export of `slot_state_history`, formula-injection-safe.

`GET /exports/history.csv` uses `StreamingResponse` over a server-side
cursor. It does NOT use the request's `Depends(get_session)` session for the
streaming part: that session is closed the instant the route handler
returns, which happens as soon as the `StreamingResponse` object is
constructed - BEFORE Starlette actually iterates the generator to send bytes.
So this module opens its own session from the app's `session_factory` and
owns closing it itself, in the generator's `finally`, after the last row (or
a client disconnect) - the same reason `slot_state_service.py` opens its own
session for executor-thread work instead of sharing one across threads.
"""

from __future__ import annotations

import csv
import datetime as dt
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..api.pagination import count_rows
from ..config.settings import Settings
from ..db.models import SlotStateHistory
from ..errors.codes import ErrorCode
from ..errors.exceptions import ValidationFailedError
from ..repositories import history_repository
from . import history_service

CSV_HEADER = (
    "id",
    "slot_id",
    "camera_code",
    "slot_code",
    "floor",
    "previous_state",
    "new_state",
    "changed_at",
    "clock_suspect",
)

# Rows are pulled from the cursor in chunks rather than one at a time or all
# at once - a middle ground between per-row Python overhead and materialising
# the whole (capped, but still potentially 100k-row) result set in memory.
FETCH_CHUNK_SIZE = 1000

# Prefixes that a spreadsheet (Excel, LibreOffice, Google Sheets) interprets
# as the start of a formula rather than literal text. A slot code or username
# is operator-entered data, not code - if it starts with one of these and the
# cell is opened unescaped, whatever formula it contains RUNS. OWASP calls
# this CSV/formula injection (CWE-1236).
_RISKY_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> str:
    """Prefix a leading apostrophe onto any cell a spreadsheet would treat as
    a formula. Excel and Sheets both render a leading apostrophe as "force
    this cell to text" and do not display the apostrophe itself.
    """
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_RISKY_PREFIXES) else text


class _Echo:
    """A write-only, do-nothing sink so `csv.writer` can format a line into
    memory instead of a real file - the standard streaming-CSV idiom, since
    `csv.writer` insists on a file-like object to write to.
    """

    def write(self, value: str) -> str:
        return value


def stream_history_csv(
    factory: sessionmaker[Session],
    settings: Settings,
    *,
    since: dt.datetime | None,
    until: dt.datetime | None,
    slot_id: int | None,
    camera_code: str | None,
    floor: str | None,
) -> Iterator[str]:
    """Yield CSV lines: a header, then every matching row, oldest connection
    kept open only for the lifetime of this generator.

    The row-count cap is enforced by the caller (`check_export_size`) BEFORE
    this generator starts, using the request-scoped session - so a request
    that will be rejected never opens a second connection or starts writing
    a response body at all.
    """
    session = factory()
    try:
        range_since, range_until = history_service.resolve_range(since, until, settings)
        stmt = history_repository.build_range_query(
            since=range_since, until=range_until, slot_id=slot_id, camera_code=camera_code,
            floor=floor,
        )
        writer = csv.writer(_Echo())
        yield writer.writerow(CSV_HEADER)

        result = session.execute(stmt.execution_options(yield_per=FETCH_CHUNK_SIZE))
        for row in result.scalars():
            yield writer.writerow(_row_cells(row))
    finally:
        session.close()


def check_export_size(
    session: Session,
    settings: Settings,
    *,
    since: dt.datetime | None,
    until: dt.datetime | None,
    slot_id: int | None,
    camera_code: str | None,
    floor: str | None,
) -> None:
    """Raise before streaming starts if the export would exceed the cap.

    Uses the request-scoped session (cheap: one COUNT query), so the
    generator in `stream_history_csv` never has to abort partway through an
    already-started download.
    """
    range_since, range_until = history_service.resolve_range(since, until, settings)
    stmt = history_repository.build_range_query(
        since=range_since, until=range_until, slot_id=slot_id, camera_code=camera_code,
        floor=floor,
    )
    total = count_rows(session, stmt)
    if total > settings.max_export_rows:
        raise ValidationFailedError(
            f"Export would contain {total} rows, over the "
            f"{settings.max_export_rows}-row cap; narrow the range or filters.",
            code=ErrorCode.RANGE_TOO_WIDE,
        )


def _row_cells(row: SlotStateHistory) -> list[str]:
    values: tuple[Any, ...] = (
        row.id,
        row.slot_id,
        row.camera_code,
        row.slot_code,
        row.floor,
        row.previous_state,
        row.new_state,
        row.changed_at.isoformat(),
        row.clock_suspect,
    )
    return [csv_safe(value) for value in values]
