"""Temporal vote filter."""

from __future__ import annotations

import pytest

from caps_dash.vision.domain import SlotState, SlotVoteFilter, build_filter


def test_stays_unknown_until_the_window_is_full() -> None:
    vote_filter = SlotVoteFilter(window=5, threshold=4)
    for _ in range(4):
        assert vote_filter.update(True) is SlotState.UNKNOWN
    assert not vote_filter.is_warmed_up
    # Fifth sample completes the window and 5/5 clears the threshold.
    assert vote_filter.update(True) is SlotState.OCCUPIED
    assert vote_filter.is_warmed_up


def test_four_of_five_flips_the_state() -> None:
    vote_filter = SlotVoteFilter(window=5, threshold=4)
    for vote in (True, False, True, True, True):
        state = vote_filter.update(vote)
    assert state is SlotState.OCCUPIED


def test_three_of_five_holds_the_previous_state() -> None:
    """Neither side reaches 4, so the filter must not invent an answer."""
    vote_filter = SlotVoteFilter(window=5, threshold=4)
    for vote in (True,) * 5:
        vote_filter.update(vote)
    assert vote_filter.state is SlotState.OCCUPIED

    # Now 3 occupied / 2 free: below threshold either way.
    for vote in (False, False):
        vote_filter.update(vote)
    assert vote_filter.state is SlotState.OCCUPIED


def test_a_brief_occlusion_does_not_free_an_occupied_slot() -> None:
    """Someone walks past the camera for one frame. The slot must not flip."""
    vote_filter = SlotVoteFilter(window=5, threshold=4)
    for _ in range(5):
        vote_filter.update(True)
    assert vote_filter.update(False) is SlotState.OCCUPIED


def test_a_car_that_really_leaves_is_reported_free() -> None:
    vote_filter = SlotVoteFilter(window=5, threshold=4)
    for _ in range(5):
        vote_filter.update(True)
    for _ in range(4):
        vote_filter.update(False)
    assert vote_filter.state is SlotState.FREE


def test_reset_returns_to_unknown() -> None:
    vote_filter = SlotVoteFilter(window=3, threshold=2)
    for _ in range(3):
        vote_filter.update(True)
    assert vote_filter.state is SlotState.OCCUPIED
    vote_filter.reset()
    assert vote_filter.state is SlotState.UNKNOWN
    assert not vote_filter.is_warmed_up


@pytest.mark.parametrize(
    ("window", "threshold", "match"),
    [
        (3, 4, "cannot exceed"),
        (0, 0, "window must be at least 1"),
        (3, 0, "threshold must be at least 1"),
    ],
)
def test_invalid_parameters_are_rejected(window: int, threshold: int, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        SlotVoteFilter(window=window, threshold=threshold)


def test_map_filter_keeps_slots_independent() -> None:
    """A shared filter would leak one slot's votes into another."""
    map_filter = build_filter(["A1", "A2"], window=3, threshold=2)
    for _ in range(3):
        states = map_filter.update({"A1"})
    assert states["A1"] is SlotState.OCCUPIED
    assert states["A2"] is SlotState.FREE


def test_map_filter_reports_unknown_for_a_slot_never_seen_occupied_before_warmup() -> None:
    map_filter = build_filter(["A1"], window=4, threshold=3)
    states = map_filter.update(set())
    assert states["A1"] is SlotState.UNKNOWN
    assert not map_filter.is_warmed_up


def test_build_filter_returns_a_fresh_instance_every_time() -> None:
    """Hot reload depends on this: a reused filter would carry stale votes."""
    first = build_filter(["A1"], window=2, threshold=2)
    for _ in range(2):
        first.update({"A1"})
    assert first.update({"A1"})["A1"] is SlotState.OCCUPIED

    second = build_filter(["A1"], window=2, threshold=2)
    assert second.update({"A1"})["A1"] is SlotState.UNKNOWN
    assert second is not first
