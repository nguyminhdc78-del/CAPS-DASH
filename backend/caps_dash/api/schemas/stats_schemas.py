"""`/stats/hourly` response schema - frozen now, implemented in phase 13.

Mirrors `db/models/hourly_stat.py` field-for-field: durations stay in seconds
(not percentages) so a caller can re-aggregate hours into a day or week
without needing the raw history back.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class HourlyStatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope_type: str
    scope_key: str
    hour_start: dt.datetime
    occupied_seconds: float
    free_seconds: float
    unknown_seconds: float
    change_count: int
    peak_occupied: int
    slot_count: int
    clock_suspect: bool
