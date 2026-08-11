"""Parking slots and the per-camera map of them.

No file I/O and no ORM here. Slot maps are persisted by the database layer and
edited through the ROI editor; the domain only ever receives plain values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import Polygon, polygon_area, scale_polygon
from .states import SlotState

# (min_x, min_y, max_x, max_y)
Bounds = tuple[float, float, float, float]


@dataclass(eq=False, slots=True)
class Slot:
    """One parking slot: an identifier and the polygon enclosing it in frame pixels.

    Not frozen, because `state` is updated in place each cycle and because the
    lazily computed area needs somewhere to live.
    """

    id: str
    polygon: Polygon
    state: SlotState = SlotState.UNKNOWN
    _area: float | None = field(default=None, repr=False, compare=False)
    _bounds: Bounds | None = field(default=None, repr=False, compare=False)

    @property
    def area(self) -> float:
        """Polygon area, computed once. Used to break overlapping-slot ties."""
        if self._area is None:
            self._area = polygon_area(self.polygon)
        return self._area

    @property
    def bounds(self) -> Bounds:
        """Axis-aligned bounding box, computed once.

        A cheap reject before the real point-in-polygon test. The fallback step
        of assignment tests 25 sample points against every slot, so on a
        twelve-slot camera that is 300 ray casts per vehicle - measurably slow
        on the aarch64 board this runs on. Comparing four floats first skips
        almost all of them.
        """
        if self._bounds is None:
            xs = [x for x, _ in self.polygon]
            ys = [y for _, y in self.polygon]
            self._bounds = (min(xs), min(ys), max(xs), max(ys))
        return self._bounds


@dataclass(slots=True)
class SlotMap:
    """The slot layout for a single camera.

    Drawn once at installation against a still of a known size. The camera is
    bolted to the ceiling, so its view does not change - but the frame size it
    delivers might, which is what `fit_to_frame` exists for.
    """

    slots: list[Slot]
    width: int
    height: int
    camera_id: str = ""

    def fit_to_frame(self, frame_w: int, frame_h: int) -> SlotMap:
        """Rescale the map onto a frame of a different size.

        The two axis factors are computed and applied SEPARATELY. Using one
        shared factor (a `min()`, or width-only) silently breaks assignment
        whenever the source and live aspect ratios differ: every slot reads
        FREE forever and nothing raises. See `scale_polygon`.
        """
        if (frame_w, frame_h) == (self.width, self.height):
            return self
        scale_x = frame_w / self.width
        scale_y = frame_h / self.height
        return SlotMap(
            slots=[
                Slot(slot.id, scale_polygon(slot.polygon, scale_x, scale_y), slot.state)
                for slot in self.slots
            ],
            width=frame_w,
            height=frame_h,
            camera_id=self.camera_id,
        )

    def states(self) -> dict[str, SlotState]:
        return {slot.id: slot.state for slot in self.slots}

    def apply_states(self, states: dict[str, SlotState]) -> None:
        """Write filtered states back onto the slots, leaving unknown ids alone."""
        for slot in self.slots:
            if slot.id in states:
                slot.state = states[slot.id]

    @property
    def slot_ids(self) -> list[str]:
        return [slot.id for slot in self.slots]

    def to_payload(self) -> str:
        """Compact wire form, e.g. `01|A1:1 A2:0 A3:?`.

        Kept because it is the whole privacy argument of the CAPS design made
        concrete: a few dozen bytes of text, never an image, leaves the device
        boundary when reporting upstream.
        """
        symbols = {SlotState.OCCUPIED: "1", SlotState.FREE: "0", SlotState.UNKNOWN: "?"}
        body = " ".join(f"{slot.id}:{symbols[slot.state]}" for slot in self.slots)
        return f"{self.camera_id}|{body}"
