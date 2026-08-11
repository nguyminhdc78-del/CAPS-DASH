"""Slot schemas.

Occupancy-summary schemas (`FloorSummary`, `OccupancySummary`) live in
`summary_schemas.py` - a resident-facing aggregate has a different privacy
shape than a slot row, and keeping the two apart makes it obvious at a glance
which schemas a resident-scoped route is allowed to return.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from ...db.enums import SlotState


class SlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    code: str
    floor: str
    current_state: str
    state_since: dt.datetime | None
    is_active: bool


class SlotDetailResponse(SlotResponse):
    # `validation_alias` reads the ORM column `polygon_json` under the public
    # name `polygon`: the stored column name is an implementation detail (the
    # column is opaque JSON, nothing queries inside it), the wire contract is
    # not, so `model_validate(slot)` still works without a manual mapping step.
    polygon: list[tuple[float, float]] = Field(validation_alias="polygon_json")
    src_frame_width: int
    src_frame_height: int


class UpdateSlotRequest(BaseModel):
    """Metadata only. Polygons are never edited through this schema.

    Geometry changes exclusively through `PUT /cameras/{id}/slot-map`, so the
    ROI editor has exactly one atomic write path for polygon + frame size
    together - a second path here could desync a polygon from the
    `src_frame_width/height` it was drawn against.
    """

    code: str | None = Field(default=None, min_length=1, max_length=16)
    floor: str | None = Field(default=None, max_length=16)
    is_active: bool | None = None


SLOT_STATES = tuple(state.value for state in SlotState)
