"""Temporal stabilisation of slot states.

Why this is not optional:

Judging each frame independently makes states flicker. Someone walks between
the camera and a car for half a second, the slot reads FREE, the dashboard
offers the space, a driver crosses the garage and finds it taken. Trust in the
system is gone, and it does not come back.

So: never change state on a single disagreeing frame. Require `threshold` of
the last `window` frames to agree.
"""

from __future__ import annotations

from collections import deque

from .constants import DEFAULT_VOTE_THRESHOLD, DEFAULT_VOTE_WINDOW
from .states import SlotState


class SlotVoteFilter:
    """Rolling vote for ONE slot."""

    __slots__ = ("_state", "_threshold", "_votes", "_window")

    def __init__(
        self,
        window: int = DEFAULT_VOTE_WINDOW,
        threshold: int = DEFAULT_VOTE_THRESHOLD,
    ) -> None:
        if window < 1:
            raise ValueError("vote window must be at least 1")
        if threshold < 1:
            raise ValueError("vote threshold must be at least 1")
        if threshold > window:
            raise ValueError("vote threshold cannot exceed window size")
        self._window = window
        self._threshold = threshold
        self._votes: deque[bool] = deque(maxlen=window)
        self._state = SlotState.UNKNOWN

    @property
    def state(self) -> SlotState:
        return self._state

    @property
    def is_warmed_up(self) -> bool:
        """Whether enough frames have been seen to draw any conclusion."""
        return len(self._votes) >= self._window

    def update(self, occupied_now: bool) -> SlotState:
        """Record one frame's verdict and return the filtered state."""
        self._votes.append(occupied_now)

        # Not enough samples yet. Guessing here would be a lie to the user.
        if len(self._votes) < self._window:
            return self._state

        occupied_votes = sum(self._votes)
        free_votes = len(self._votes) - occupied_votes

        if occupied_votes >= self._threshold:
            self._state = SlotState.OCCUPIED
        elif free_votes >= self._threshold:
            self._state = SlotState.FREE
        # Neither side reached the threshold: hold the previous state rather
        # than invent one. This is the branch that absorbs brief occlusions.

        return self._state

    def reset(self) -> None:
        self._votes.clear()
        self._state = SlotState.UNKNOWN


class SlotMapFilter:
    """One vote filter per slot of one camera."""

    __slots__ = ("_filters",)

    def __init__(
        self,
        slot_ids: list[str],
        window: int = DEFAULT_VOTE_WINDOW,
        threshold: int = DEFAULT_VOTE_THRESHOLD,
    ) -> None:
        self._filters = {
            slot_id: SlotVoteFilter(window, threshold) for slot_id in slot_ids
        }

    def update(self, occupied_ids: set[str]) -> dict[str, SlotState]:
        """Feed one frame's raw result in, get every slot's filtered state out."""
        return {
            slot_id: vote_filter.update(slot_id in occupied_ids)
            for slot_id, vote_filter in self._filters.items()
        }

    @property
    def is_warmed_up(self) -> bool:
        return all(f.is_warmed_up for f in self._filters.values())

    @property
    def slot_ids(self) -> list[str]:
        return list(self._filters)

    def reset(self) -> None:
        for vote_filter in self._filters.values():
            vote_filter.reset()


def build_filter(
    slot_ids: list[str],
    window: int = DEFAULT_VOTE_WINDOW,
    threshold: int = DEFAULT_VOTE_THRESHOLD,
) -> SlotMapFilter:
    """Create a filter for a camera.

    The only sanctioned way to make one, so that "always build a fresh filter
    after a slot-map edit" is a single call at the call site. Reusing a filter
    across an edit lets a newly drawn slot inherit the votes of whatever slot
    happened to share its id - wrong, and completely silent.
    """
    return SlotMapFilter(slot_ids, window, threshold)
