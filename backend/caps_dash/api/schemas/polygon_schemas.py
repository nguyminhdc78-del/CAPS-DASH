"""Polygon validation, shared by every endpoint that accepts one.

The domain assumes polygons are already sane - finite, at least a triangle, and
with a real area. This is where that is enforced, so `assign_detection` never
has to defend itself against a degenerate shape.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

MIN_POINTS = 3
MAX_POINTS = 64
MIN_AREA_PX = 100.0

Point = tuple[float, float]


class PolygonModel(BaseModel):
    """A slot outline in source-frame pixel coordinates."""

    points: list[Point] = Field(min_length=MIN_POINTS, max_length=MAX_POINTS)

    @field_validator("points")
    @classmethod
    def _finite_and_positive(cls, points: list[Point]) -> list[Point]:
        for x, y in points:
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError("polygon points must be finite numbers")
            if x < 0 or y < 0:
                raise ValueError("polygon points must be inside the frame")
        return points

    @model_validator(mode="after")
    def _has_real_area(self) -> PolygonModel:
        """Reject collinear points.

        A zero-area polygon would always win the smallest-area tie-break in
        slot assignment, quietly capturing every vehicle that overlaps it.
        """
        if _shoelace_area(self.points) < MIN_AREA_PX:
            # A typed error, not a bare ValueError: the handler maps this
            # `polygon_degenerate` type onto `ErrorCode.POLYGON_DEGENERATE` so
            # the ROI editor can tell the operator what is wrong with the shape
            # they drew, instead of a generic "validation failed".
            raise PydanticCustomError(
                "polygon_degenerate",
                "polygon area must exceed {minimum} px; points may be collinear",
                {"minimum": MIN_AREA_PX},
            )
        return self


def _shoelace_area(points: list[Point]) -> float:
    total = 0.0
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0
