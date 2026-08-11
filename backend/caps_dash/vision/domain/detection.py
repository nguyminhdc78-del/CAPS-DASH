"""A vehicle found in a frame."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Detection:
    """One detected object.

    COORDINATE CONTRACT: `x1, y1, x2, y2` are pixels in the ORIGINAL frame, not
    normalised, and not in the detector's input resolution. Every detector is
    responsible for mapping its own letterboxing and rescaling back before it
    returns.

    That contract is what keeps the assignment layer from needing to know
    anything about the model - swap the model, change its input size, and
    nothing downstream moves.
    """

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    label: str = "car"

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1
