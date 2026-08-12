"""The change gate looks only where parking slots are drawn.

Averaging the whole frame is wrong in both directions, and both are tested
here: motion outside every slot must not wake the detector, and a change
inside one slot must not be diluted below the threshold by the rest of the
picture holding still.
"""

from __future__ import annotations

import numpy as np

from caps_dash.vision.frame_change_gate import (
    SAMPLE_HEIGHT,
    SAMPLE_WIDTH,
    FrameChangeGate,
    build_roi_mask,
)

FRAME_W, FRAME_H = 640, 480
# One slot in the lower-left quadrant - a twentieth of the frame, which is
# roughly what one bay of a real car park occupies.
SLOT = [(40.0, 260.0), (180.0, 260.0), (180.0, 400.0), (40.0, 400.0)]


def blank() -> np.ndarray:
    return np.full((FRAME_H, FRAME_W, 3), 60, dtype=np.uint8)


def with_block(x1: int, y1: int, x2: int, y2: int, value: int = 220) -> np.ndarray:
    frame = blank()
    frame[y1:y2, x1:x2] = value
    return frame


def gate_watching_slot(threshold: float = 8.0) -> FrameChangeGate:
    gate = FrameChangeGate(threshold=threshold, force_interval_s=3600.0)
    gate.set_region(build_roi_mask([SLOT], FRAME_W, FRAME_H))
    return gate


def test_mask_covers_the_slot_and_little_else() -> None:
    mask = build_roi_mask([SLOT], FRAME_W, FRAME_H)

    assert mask is not None
    assert mask.shape == (SAMPLE_HEIGHT, SAMPLE_WIDTH)
    # The slot is ~1/16 of the frame; dilation adds a ring, so allow headroom
    # but insist it is nothing like the whole grid.
    covered = mask.mean()
    assert 0.02 < covered < 0.20, covered


def test_no_slots_means_watch_everything() -> None:
    """Otherwise a camera whose ROI has not been drawn yet would never infer -
    the detector would go quiet exactly when nobody has configured it."""
    assert build_roi_mask([], FRAME_W, FRAME_H) is None
    assert build_roi_mask([[(0.0, 0.0), (1.0, 1.0)]], FRAME_W, FRAME_H) is None


def test_movement_outside_every_slot_does_not_wake_the_detector() -> None:
    """Somebody walking past the top of the view cannot change any slot's
    state, so paying ~5 s of inference to confirm that is pure waste."""
    gate = gate_watching_slot()
    gate.mark_inferred(blank())

    # A large bright block in the opposite corner - far more change than the
    # threshold, if you were averaging the whole frame.
    decision = gate.evaluate(with_block(420, 20, 620, 200))

    assert decision.infer is False
    assert decision.reason == "unchanged"


def test_the_same_movement_does_wake_a_gate_watching_the_whole_frame() -> None:
    """Pins the difference the ROI makes, rather than asserting it in prose."""
    gate = FrameChangeGate(threshold=8.0, force_interval_s=3600.0)
    gate.set_region(None)
    gate.mark_inferred(blank())

    assert gate.evaluate(with_block(420, 20, 620, 200)).infer is True


def test_a_car_arriving_in_one_slot_is_not_diluted_away() -> None:
    """The failure this fixes: one bay filling out of many barely moves a
    whole-frame average, so the detector never looks and the slot stays FREE."""
    roi_gate = gate_watching_slot()
    roi_gate.mark_inferred(blank())
    whole_frame_gate = FrameChangeGate(threshold=8.0, force_interval_s=3600.0)
    whole_frame_gate.mark_inferred(blank())

    arriving = with_block(50, 270, 170, 390)

    roi_decision = roi_gate.evaluate(arriving)
    whole_decision = whole_frame_gate.evaluate(arriving)

    assert roi_decision.infer is True
    assert roi_decision.reason == "changed"
    # Same pixels, same threshold: only the region being averaged differs.
    assert roi_decision.difference > whole_decision.difference


def test_the_heartbeat_still_fires_inside_the_roi() -> None:
    """Restricting the region must not disable the safety net that catches
    drift the threshold misses."""
    gate = FrameChangeGate(threshold=8.0, force_interval_s=0.0)
    gate.set_region(build_roi_mask([SLOT], FRAME_W, FRAME_H))
    gate.mark_inferred(blank())

    decision = gate.evaluate(blank())

    assert decision.infer is True
    assert decision.reason == "heartbeat"


def test_a_redrawn_map_replaces_the_region() -> None:
    gate = gate_watching_slot()
    gate.mark_inferred(blank())

    # Redrawn to cover the top-right instead.
    moved = [(420.0, 20.0), (620.0, 20.0), (620.0, 200.0), (420.0, 200.0)]
    gate.set_region(build_roi_mask([moved], FRAME_W, FRAME_H))

    assert gate.evaluate(with_block(420, 20, 620, 200)).infer is True


class _FakeSettings:
    min_inference_interval_s = 0.0


class _FakeSlotMap:
    def __init__(self, count: int) -> None:
        self.slots = list(range(count))


class _FakeContext:
    """Just enough context for the rule, which reads three fields."""

    settings = _FakeSettings()

    def __init__(
        self,
        states: dict[str, str] | None,
        votes_settled: bool = True,
        slots: int = 2,
    ) -> None:
        self.last_states = states or {}
        self.votes_settled = votes_settled
        self.slot_map = _FakeSlotMap(slots)


def test_a_camera_with_no_results_yet_needs_observations() -> None:
    """First tick after a restart: nothing has been decided, so nothing may be
    skipped on the grounds that it was already decided."""
    from caps_dash.workers.camera_tick_policy import needs_more_observations

    assert needs_more_observations(_FakeContext(None)) is True


def test_an_unknown_slot_needs_observations() -> None:
    """Measured on the board: a static three-car scene sat at UNKNOWN for over
    two minutes after a restart, because the gate skipped every tick and only
    the 30 s heartbeat fed the filter."""
    from caps_dash.workers.camera_tick_policy import needs_more_observations

    assert needs_more_observations(_FakeContext({"A1": "UNKNOWN", "A2": "OCCUPIED"})) is True


def test_a_slot_mid_transition_needs_observations() -> None:
    """The reported failure, and the worse half of this bug: a car is taken
    out, the scene changes ONCE so the gate fires once, and then the scene is
    static again. Every subsequent tick is skipped, so the four votes needed
    to flip the slot never arrive and it keeps reporting OCCUPIED - with a
    detector that can plainly see the bay is empty.
    """
    from caps_dash.workers.camera_tick_policy import needs_more_observations

    settled = _FakeContext({"A1": "OCCUPIED", "A2": "FREE"}, votes_settled=True)
    mid_transition = _FakeContext({"A1": "OCCUPIED", "A2": "FREE"}, votes_settled=False)

    assert needs_more_observations(settled) is False
    assert needs_more_observations(mid_transition) is True


class _FakeVoteFilter:
    """Reports a fixed verdict, so the applier's agreement check is what is
    under test rather than the filter's own arithmetic."""

    def __init__(self, states: dict[str, object]) -> None:
        self._states = states

    def update(self, _occupied: set[str]) -> dict[str, object]:
        return self._states


def test_the_applier_notices_when_a_car_has_gone_but_the_vote_has_not() -> None:
    """End of the chain: a detector that no longer sees a car in A1, while the
    filter still reports OCCUPIED, must leave `votes_settled` False so the
    loop keeps looking.
    """
    from caps_dash.vision.domain import SlotState
    from caps_dash.workers.inference_outcome_applier import _disagreeing_slots

    states = {"A1": SlotState.OCCUPIED, "A2": SlotState.OCCUPIED}

    # Both cars still there: nothing to settle.
    assert _disagreeing_slots({"A1", "A2"}, states) == []

    # A1 emptied, but the vote has not carried yet.
    assert _disagreeing_slots({"A2"}, states) == ["A1"]

    # ...and the reverse: a car has arrived where the filter still says FREE.
    arriving = {"A1": SlotState.FREE}
    assert _disagreeing_slots({"A1"}, arriving) == ["A1"]

    # UNKNOWN always counts, whichever way the observation points.
    assert _disagreeing_slots(set(), {"A1": SlotState.UNKNOWN}) == ["A1"]
    assert _disagreeing_slots({"A1"}, {"A1": SlotState.UNKNOWN}) == ["A1"]


def test_a_camera_with_no_roi_drawn_is_left_alone() -> None:
    """A camera with no slot map has no state to settle, and forcing it to
    infer is actively harmful rather than merely wasteful.

    Measured on the board: an unconfigured second camera ran a detection on
    every tick forever, which saturated the single shared inference worker -
    two cameras x 1.5 s of work per 3 s tick - and starved the camera that
    did have slots. 11 inferences a minute on the empty one, 0 on the
    configured one. That is what turned a twelve-second vote into a minute.
    """
    from caps_dash.workers.camera_tick_policy import needs_more_observations

    unconfigured = _FakeContext(None, votes_settled=False, slots=0)
    configured = _FakeContext(None, votes_settled=False, slots=3)

    assert needs_more_observations(unconfigured) is False
    assert needs_more_observations(configured) is True
