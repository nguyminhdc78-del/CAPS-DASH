"""Parking geometry.

Standard library only, like every module in this package. The reasoning behind
each function matters more than the arithmetic, so it is recorded here rather
than in a design document nobody will open.
"""

from __future__ import annotations

from .constants import BAND_COLS, BAND_FRACTION, BAND_ROWS

Point = tuple[float, float]
Polygon = list[Point]


def ground_point(x1: float, y1: float, x2: float, y2: float) -> Point:
    """The point that represents a vehicle: the middle of the bbox BOTTOM edge.

    Where the wheels meet the floor. Deliberately not the bbox centre: these
    cameras are mounted on the ceiling looking obliquely down, so the centre of
    a tall vehicle's box falls into the slot *behind* it. Simulation on the
    reference project put correct assignment at 0% for some camera geometries
    when the centre was used.

    `y1` is unused and kept in the signature so callers can pass a bbox
    positionally without slicing it apart.
    """
    del y1  # documented above: the top edge plays no part in a ground point
    return ((x1 + x2) / 2.0, y2)


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Ray casting. Works for concave polygons, which hand-drawn slots often are.

    Cast a horizontal ray from the point and count edge crossings: odd means
    inside. A point lying exactly on an edge may come out either way depending
    on rounding. That is acceptable here - slots are drawn by hand over a
    camera still, so no boundary is meaningful to sub-pixel precision.
    """
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y):  # this edge straddles the horizontal line y
            x_crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_crossing:
                inside = not inside
    return inside


def polygon_area(polygon: Polygon) -> float:
    """Shoelace area. Used to break ties between overlapping slots."""
    total = 0.0
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def bottom_band_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    band: float = BAND_FRACTION,
    cols: int = BAND_COLS,
    rows: int = BAND_ROWS,
) -> list[Point]:
    """A grid of sample points across the BOTTOM band of a bounding box.

    Fallback for when the ground point lands just outside a slot because the
    polygon was drawn a few pixels short.

    Only the bottom band, never the whole box: the upper part is roof and body,
    which overhang the row behind under an oblique view. Sampling the whole box
    would hand cars to the slot behind them - the exact failure the ground
    point exists to avoid.
    """
    band_top = y2 - (y2 - y1) * band
    return [
        (
            x1 + (x2 - x1) * (col + 0.5) / cols,
            band_top + (y2 - band_top) * (row + 0.5) / rows,
        )
        for col in range(cols)
        for row in range(rows)
    ]


def scale_polygon(polygon: Polygon, scale_x: float, scale_y: float) -> Polygon:
    """Scale horizontally and vertically with INDEPENDENT factors.

    Slot maps are drawn on a still of one size and matched against live frames
    of another, and the two aspect ratios are rarely identical (a map drawn on
    16:9, a frame arriving at 10:7).

    Collapsing these into one shared factor is a silent catastrophe: every slot
    reports FREE forever, no exception is raised, and the system looks
    perfectly healthy while being entirely wrong. There is a regression test
    pinning this behaviour - do not "simplify" it away.
    """
    return [(x * scale_x, y * scale_y) for x, y in polygon]
