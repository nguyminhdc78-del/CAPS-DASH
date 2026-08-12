"""Spreading camera loops across the poll interval instead of starting them together.

Every camera's tick is self-contained - it sleeps the remainder of its own
interval from its own start - so N cameras spawned in the same millisecond keep
firing in the same millisecond forever. They then hand N inferences to a
one-worker pool at once, and the last one waits (N-1) x ~616 ms for a result
describing a frame that is already ticks old.

Delaying each camera's first tick by a fraction of the interval spreads the
arrivals so each inference mostly lands in an empty queue. This matters at a
2 s tick in a way it did not at 0.2 s, where the queue drained between ticks
by accident.

Kept apart from `camera_supervisor` because it is pure arithmetic over a set
of ids: testable without an event loop, and the supervisor is already over the
file-size budget.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def stagger_offsets(
    spawning: Iterable[int],
    *,
    fleet_size: int,
    poll_interval_s: Mapping[int, float],
) -> dict[int, float]:
    """How long each camera about to start should wait before its first tick.

    `spawning` is the cameras being started now; `fleet_size` is every enabled
    camera, including ones already running. Spacing divides by the whole fleet
    rather than by how many are starting, so two cameras added to a fleet of
    three are spread a third of an interval apart, not half - the width matches
    the fleet they are joining.

    What this does **not** do is align a late arrival against the cameras
    already ticking. A single camera added on its own gets offset 0 and starts
    immediately, at whatever phase the operator's click lands on, possibly on
    top of a running camera. Aligning would need a shared epoch every loop
    measured from, which the loops do not have - each anchors to its own start.
    Cold start is the case this exists for, and there it is exact.

    Each camera is spaced by its **own** interval: `poll_interval_s` is
    per-camera, so there is no single "the" interval to divide. With a
    homogeneous fleet that is exact; with a mixed one it is still strictly
    better than starting everything at once.

    A one-camera system gets 0.0 and therefore behaves exactly as it did
    before staggering existed.
    """
    ordered = sorted(spawning)
    if fleet_size <= 1:
        # Also covers fleet_size == 0, which only happens if the caller passes
        # an inconsistent pair - no division, no ZeroDivisionError.
        return dict.fromkeys(ordered, 0.0)

    return {
        camera_id: index * poll_interval_s.get(camera_id, 0.0) / fleet_size
        for index, camera_id in enumerate(ordered)
    }
