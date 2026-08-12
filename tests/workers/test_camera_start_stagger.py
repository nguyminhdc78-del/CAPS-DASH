"""Starting camera loops spread across the poll interval rather than together.

Two seams, deliberately tested with different techniques: the arithmetic is
pure and gets asserted directly, while the application only has to prove
*where* the sleep happens - once, before the retry loop. Asserting real
elapsed time across three async tasks would test the scheduler, not the code.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from caps_dash.config.settings import Settings
from caps_dash.realtime.broadcast_hub import BroadcastHub
from caps_dash.workers import camera_supervisor as supervisor_module
from caps_dash.workers.camera_start_stagger import stagger_offsets
from caps_dash.workers.camera_supervisor import CameraSupervisor
from caps_dash.workers.reload_signals import ReloadSignals

# --- The arithmetic ----------------------------------------------------------


def test_three_cameras_are_spread_across_one_interval() -> None:
    """The case the stagger exists for: 3 x ~616 ms of serialized inference
    against a 2.0 s tick. Started together, the third waits for the other two
    and describes a frame two ticks old; spread, each lands in its own window."""
    offsets = stagger_offsets(
        {3, 7, 9}, fleet_size=3, poll_interval_s={3: 2.0, 7: 2.0, 9: 2.0}
    )

    assert offsets == {
        3: pytest.approx(0.0),
        7: pytest.approx(2.0 / 3),
        9: pytest.approx(4.0 / 3),
    }


def test_the_order_follows_the_camera_ids_not_set_iteration() -> None:
    """Sorted, so the same fleet always gets the same assignment and a test can
    name which camera takes which slot."""
    assert list(
        stagger_offsets(
            {9, 3, 7}, fleet_size=3, poll_interval_s=dict.fromkeys((3, 7, 9), 3.0)
        )
    ) == [3, 7, 9]


def test_one_camera_is_not_delayed_at_all() -> None:
    """A single-camera system must behave exactly as it did before staggering
    existed - there is nothing to spread it against."""
    assert stagger_offsets({4}, fleet_size=1, poll_interval_s={4: 2.0}) == {4: 0.0}


def test_spacing_is_sized_by_the_fleet_not_by_how_many_are_starting() -> None:
    """Two cameras joining a fleet of three are spread a third of an interval
    apart, not half - the width matches the fleet they are joining.

    Note what this deliberately does not claim: a camera added *alone* gets
    offset 0 and starts immediately, at whatever phase the operator's click
    lands on. Aligning it to the cameras already ticking would need a shared
    epoch the loops do not have."""
    assert stagger_offsets({9}, fleet_size=3, poll_interval_s={9: 2.0}) == {9: 0.0}

    joining_a_fleet_of_three = stagger_offsets(
        {7, 9}, fleet_size=3, poll_interval_s={7: 2.0, 9: 2.0}
    )
    assert joining_a_fleet_of_three[9] == pytest.approx(2.0 / 3)

    # The same pair on their own would have been half an interval apart.
    alone = stagger_offsets({7, 9}, fleet_size=2, poll_interval_s={7: 2.0, 9: 2.0})
    assert alone[9] == pytest.approx(1.0)


def test_each_camera_is_spaced_by_its_own_interval() -> None:
    """`poll_interval_s` is per-camera, so there is no single interval to
    divide. A mixed fleet is still spread, just not evenly - which beats not
    spreading it at all."""
    offsets = stagger_offsets(
        {1, 2}, fleet_size=2, poll_interval_s={1: 2.0, 2: 10.0}
    )

    assert offsets == {1: pytest.approx(0.0), 2: pytest.approx(5.0)}


def test_an_empty_fleet_does_not_divide_by_zero() -> None:
    """`reconcile()` calls this whenever the camera table is empty or
    unreadable, which is the normal state of a fresh install."""
    assert stagger_offsets(set(), fleet_size=0, poll_interval_s={}) == {}


def test_a_camera_with_no_known_interval_is_not_delayed() -> None:
    """Defensive: a missing interval means the caller's two arguments disagree.
    Starting the camera immediately is the safe reading - a guess would delay a
    camera by an interval nobody chose."""
    assert stagger_offsets({1, 2}, fleet_size=2, poll_interval_s={1: 2.0}) == {
        1: 0.0,
        2: 0.0,
    }


# --- Where the sleep happens -------------------------------------------------


class _BuildFailed(Exception):
    """Stands in for a camera whose configuration or source cannot be built."""


def _bare_supervisor(settings: Settings) -> CameraSupervisor:
    """A supervisor whose `_build` every test below replaces.

    Nothing here reaches the database or the detector: these tests are about
    the shape of `_supervise`'s retry loop, not about what runs inside it.
    """
    return CameraSupervisor(
        settings=settings,
        session_factory=None,  # type: ignore[arg-type]
        loop=asyncio.get_running_loop(),
        inference_pool=ThreadPoolExecutor(max_workers=1),
        db_pool=ThreadPoolExecutor(max_workers=1),
        hub=BroadcastHub(),
        reload_signals=ReloadSignals(asyncio.get_running_loop()),
    )


def _record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture what `_supervise` sleeps, without sleeping it.

    The delays still yield to the event loop, so the loop's shape is unchanged
    - only the wall clock is removed. Asserting on the sequence is the point:
    the failure this catches is a sleep in the wrong place, not a sleep of the
    wrong length.
    """
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def record(delay: float, *args: object, **kwargs: object) -> None:
        slept.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", record)
    return slept


async def test_the_offset_is_slept_before_the_camera_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise every camera opens its source at once and the stagger only
    spreads the ticks after the expensive part has already collided."""
    settings = Settings(app_env="dev", secret_key="stagger-test-signing-key-padded-32")
    supervisor = _bare_supervisor(settings)
    order: list[str] = []

    def build(camera_id: int) -> None:
        order.append("build")
        supervisor._stop.set()
        raise _BuildFailed(camera_id)

    monkeypatch.setattr(supervisor, "_build", build)
    slept = _record_sleeps(monkeypatch)

    await supervisor._supervise(7, offset_s=1.25)

    assert slept == [1.25]
    assert order == ["build"]


async def test_the_offset_is_not_re_applied_after_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The most likely way to get this wrong is to sleep inside the `while`.

    A camera that crashes already has its own backoff. Adding the stagger to
    every restart would push a flapping camera further from its slot each
    time, so it would drift out of the spacing the stagger exists to keep.
    """
    settings = Settings(app_env="dev", secret_key="stagger-test-signing-key-padded-32")
    supervisor = _bare_supervisor(settings)
    monkeypatch.setattr(supervisor_module, "INITIAL_BACKOFF_S", 0.01)
    attempts: list[int] = []

    def build(camera_id: int) -> None:
        attempts.append(camera_id)
        if len(attempts) == 2:
            supervisor._stop.set()
        raise _BuildFailed(camera_id)

    monkeypatch.setattr(supervisor, "_build", build)
    slept = _record_sleeps(monkeypatch)

    await supervisor._supervise(7, offset_s=1.25)

    assert attempts == [7, 7], "the loop must still retry after a crash"
    assert slept == [1.25], "the stagger offset was re-applied on the retry"


async def test_a_camera_with_no_offset_sleeps_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`if offset_s:` rather than an unconditional `sleep(0)`, so the
    single-camera path does not gain an event-loop round trip it never had."""
    settings = Settings(app_env="dev", secret_key="stagger-test-signing-key-padded-32")
    supervisor = _bare_supervisor(settings)

    def build(camera_id: int) -> None:
        supervisor._stop.set()
        raise _BuildFailed(camera_id)

    monkeypatch.setattr(supervisor, "_build", build)
    slept = _record_sleeps(monkeypatch)

    await supervisor._supervise(7)

    assert slept == []
