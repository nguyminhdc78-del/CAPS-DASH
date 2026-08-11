"""The camera loop, end to end, with no hardware and no model file.

Source to slot state to database to broadcast - the whole tick, driven by the
fake frame source and the scripted detector. This is what those two backends
exist for.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import select

from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.enums import CameraSourceType
from caps_dash.db.enums import SlotState as DbSlotState
from caps_dash.db.models import Base, Camera, ParkingSlot, SlotStateHistory
from caps_dash.db.session import create_session_factory, session_scope
from caps_dash.realtime.broadcast_hub import BroadcastHub
from caps_dash.realtime.frame_protocol import decode_frame_message
from caps_dash.vision.detectors import fake_detector
from caps_dash.vision.domain import Detection, SlotState
from caps_dash.workers import camera_loop, inference_runner
from caps_dash.workers.camera_context import CameraContext, build_context
from caps_dash.workers.camera_loop import run_camera_loop
from caps_dash.workers.camera_supervisor import CameraSupervisor
from caps_dash.workers.reload_signals import ReloadSignals

# A slot covering the lower-left quadrant of a 640x480 frame.
SLOT_POLYGON = [[40, 260], [300, 260], [300, 440], [40, 440]]
# A car whose ground point (170, 430) sits inside it.
PARKED_CAR = Detection(x1=120.0, y1=300.0, x2=220.0, y2=430.0, confidence=0.9, label="car")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="dev",
        secret_key="worker-test-signing-key-padded-out-32",
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        detector_backend="fake",
        # Fast ticks: the loop is bounded by max_ticks, not by wall clock.
        default_poll_interval_s=0.01,
        # Gate off for these tests. The fake source produces near-identical
        # frames, so the change gate would correctly skip inference after the
        # first tick and the vote filter would never see enough observations -
        # which is the gate's own behaviour, tested separately below, not the
        # voting behaviour these tests are about.
        motion_change_threshold=0.0,
        log_json=False,
    )


@pytest.fixture
def session_factory(settings: Settings):
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture
def camera_id(session_factory) -> int:
    with session_scope(session_factory) as session:
        camera = Camera(
            code="demo-01",
            name="Fake camera",
            floor="B1",
            source_type=CameraSourceType.FAKE,
            source_url="",
            poll_interval_s=0.01,
            vote_window=3,
            vote_threshold=2,
        )
        camera.slots = [
            ParkingSlot(
                code="A1",
                floor="B1",
                polygon_json=SLOT_POLYGON,
                src_frame_width=640,
                src_frame_height=480,
            )
        ]
        session.add(camera)
        session.flush()
        return camera.id


@pytest.fixture(autouse=True)
def scripted_detector(monkeypatch: pytest.MonkeyPatch):
    """Force every worker thread to use a detector that always sees the car."""
    inference_runner.reset_thread_detector()
    detector = fake_detector.FakeVehicleDetector([[PARKED_CAR]])
    monkeypatch.setattr(inference_runner, "build_detector", lambda _settings: detector)
    yield detector
    inference_runner.reset_thread_detector()


async def _run(settings, session_factory, camera_id, hub, ticks: int) -> CameraContext:
    loop = asyncio.get_running_loop()
    inference_pool = ThreadPoolExecutor(max_workers=1)
    db_pool = ThreadPoolExecutor(max_workers=1)
    signals = ReloadSignals(loop)
    try:
        context = build_context(
            camera_id=camera_id,
            settings=settings,
            session_factory=session_factory,
            loop=loop,
            inference_pool=inference_pool,
            db_pool=db_pool,
            hub=hub,
            reload_signals=signals,
        )
        stop = asyncio.Event()

        async def rebuild(old: CameraContext) -> CameraContext:
            return old

        await run_camera_loop(context, stop, rebuild=rebuild, max_ticks=ticks)
        return context
    finally:
        inference_pool.shutdown(wait=True)
        db_pool.shutdown(wait=True)


async def test_a_parked_car_eventually_marks_the_slot_occupied(
    settings, session_factory, camera_id
) -> None:
    context = await _run(settings, session_factory, camera_id, BroadcastHub(), ticks=4)

    assert context.metrics.frames_ok == 4
    assert context.metrics.fail_streak == 0

    with session_scope(session_factory) as session:
        slot = session.execute(select(ParkingSlot)).scalar_one()
        assert slot.current_state == DbSlotState.OCCUPIED
        assert slot.state_since is not None


async def test_the_slot_stays_unknown_until_the_filter_warms_up(
    settings, session_factory, camera_id
) -> None:
    """Two ticks with a window of three: not enough evidence to conclude."""
    await _run(settings, session_factory, camera_id, BroadcastHub(), ticks=2)

    with session_scope(session_factory) as session:
        slot = session.execute(select(ParkingSlot)).scalar_one()
        assert slot.current_state == DbSlotState.UNKNOWN


async def test_history_records_the_transition_once_not_every_tick(
    settings, session_factory, camera_id
) -> None:
    """The write-on-change rule, measured. Ten ticks, one row."""
    await _run(settings, session_factory, camera_id, BroadcastHub(), ticks=10)

    with session_scope(session_factory) as session:
        rows = list(session.execute(select(SlotStateHistory)).scalars())

    assert len(rows) == 1
    assert rows[0].new_state == SlotState.OCCUPIED
    assert rows[0].slot_code == "A1"
    assert rows[0].camera_code == "demo-01"


async def test_frames_are_published_to_a_watching_viewer(
    settings, session_factory, camera_id
) -> None:
    hub = BroadcastHub()
    viewer = hub.subscribe(camera_id)

    await _run(settings, session_factory, camera_id, hub, ticks=4)

    message = decode_frame_message(await viewer.get())
    assert message.header["camera_code"] == "demo-01"
    assert message.header["slots"][0]["code"] == "A1"
    assert message.header["detections"][0]["label"] == "car"
    # The JPEG travelled with the state in the same message.
    assert message.jpeg.startswith(b"\xff\xd8")


async def test_the_published_jpeg_is_the_frame_inference_ran_on(
    settings, session_factory, camera_id
) -> None:
    """The atomic-message guarantee, asserted rather than assumed.

    One message carries the frame and the state describing it. That only holds
    if the bytes published are the same bytes the detector saw - if a future
    change ever re-encodes, resizes or re-fetches for the stream, the overlay
    would be drawn over a different picture than the one it describes, and
    nothing else in the suite would notice.
    """
    hub = BroadcastHub()
    viewer = hub.subscribe(camera_id)

    context = await _run(settings, session_factory, camera_id, hub, ticks=4)

    message = decode_frame_message(await viewer.get())
    assert message.jpeg == context.last_jpeg
    assert (message.header["frame_w"], message.header["frame_h"]) == context.last_frame_size


async def test_encoding_happens_once_per_tick_regardless_of_viewer_count(
    settings, session_factory, camera_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fan-out must cost a reference copy per viewer, never an encode.

    Counted against the real loop, not against a helper the test calls itself:
    five viewers over four ticks is four encodes, or the CPU cost of a stream
    grows with the number of people watching - which is exactly what this
    design refuses to do on a single-board host.
    """
    hub = BroadcastHub()
    for _ in range(5):
        hub.subscribe(camera_id)

    calls = 0
    real_encode = camera_loop.encode_frame_message

    def counting_encode(header: dict, jpeg: bytes) -> bytes:
        nonlocal calls
        calls += 1
        return real_encode(header, jpeg)

    monkeypatch.setattr(camera_loop, "encode_frame_message", counting_encode)

    await _run(settings, session_factory, camera_id, hub, ticks=4)

    assert calls == 4


async def test_nothing_is_published_when_nobody_is_watching(
    settings, session_factory, camera_id
) -> None:
    """No viewers, no encoding. Cheap ticks matter on a small board."""
    hub = BroadcastHub()
    await _run(settings, session_factory, camera_id, hub, ticks=3)
    assert hub.viewer_count(camera_id) == 0


async def test_the_camera_row_records_the_frame_size_it_saw(
    settings, session_factory, camera_id
) -> None:
    await _run(settings, session_factory, camera_id, BroadcastHub(), ticks=2)

    with session_scope(session_factory) as session:
        camera = session.get(Camera, camera_id)
        assert camera is not None
        assert (camera.frame_width, camera.frame_height) == (640, 480)
        assert camera.last_seen_at is not None


async def test_a_camera_added_after_startup_starts_running(settings, session_factory) -> None:
    """The reconcile signal raised by `camera_service` has to be acted on.

    Reconciling only at startup would mean a camera added from the dashboard
    sat there doing nothing until somebody restarted the process - a bug that
    presents as "the new camera is broken" rather than as a missing watcher.
    """
    loop = asyncio.get_running_loop()
    inference_pool = ThreadPoolExecutor(max_workers=1)
    db_pool = ThreadPoolExecutor(max_workers=1)
    signals = ReloadSignals(loop)
    supervisor = CameraSupervisor(
        settings=settings,
        session_factory=session_factory,
        loop=loop,
        inference_pool=inference_pool,
        db_pool=db_pool,
        hub=BroadcastHub(),
        reload_signals=signals,
    )

    try:
        await supervisor.start()
        assert supervisor.running_camera_ids == []

        with session_scope(session_factory) as session:
            session.add(
                Camera(
                    code="late-01",
                    source_type=CameraSourceType.FAKE,
                    source_url="",
                    poll_interval_s=0.01,
                )
            )

        signals.request_reconcile()
        for _ in range(50):
            await asyncio.sleep(0.02)
            if supervisor.running_camera_ids:
                break

        assert supervisor.running_camera_ids, "the camera added after startup never started"
    finally:
        await supervisor.stop(timeout=2.0)
        inference_pool.shutdown(wait=True)
        db_pool.shutdown(wait=True)


async def test_a_barely_changing_scene_skips_most_inferences(
    settings, session_factory, camera_id
) -> None:
    """Parked cars do not move, so most frames are the same picture.

    Running the detector on each of them re-derives an unchanged answer for
    ~616 ms of a shared four-core board; the gate compares a 64x48 greyscale
    sample for 2.7 ms instead.

    The arithmetic here is exact and worth following, because it demonstrates
    the rule that matters: `FakeSource` brightens by one grey level per frame,
    and the gate measures against the last frame the detector *saw*, not the
    previous frame. So the difference accumulates 1, 2, 3 and trips the
    threshold of 3.0 on every third tick. Measured frame-to-frame it would be
    a constant 1.0 and the detector would never run again - which is exactly
    how a car easing into a slot over several frames would be missed.
    """
    gated = settings.model_copy(
        update={"motion_change_threshold": 3.0, "motion_force_interval_s": 3600.0}
    )
    calls = 0
    real_inference = camera_loop.run_inference

    def counting_inference(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real_inference(*args, **kwargs)

    camera_loop.run_inference = counting_inference
    try:
        await _run(gated, session_factory, camera_id, BroadcastHub(), ticks=8)
    finally:
        camera_loop.run_inference = real_inference

    # Tick 1 (no reference yet), then ticks 4 and 7 as the drift reaches 3.
    assert calls == 3


async def test_the_heartbeat_forces_inference_on_a_static_scene(
    settings, session_factory, camera_id
) -> None:
    """Slow drift - dusk, a light switched on, auto-exposure creeping - can
    stay under the threshold indefinitely. The heartbeat bounds how long the
    system is allowed to be wrong about a slot."""
    gated = settings.model_copy(
        update={"motion_change_threshold": 3.0, "motion_force_interval_s": 0.0}
    )
    calls = 0
    real_inference = camera_loop.run_inference

    def counting_inference(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real_inference(*args, **kwargs)

    camera_loop.run_inference = counting_inference
    try:
        await _run(gated, session_factory, camera_id, BroadcastHub(), ticks=5)
    finally:
        camera_loop.run_inference = real_inference

    # A zero interval means every tick is overdue, so nothing is ever skipped.
    assert calls == 5


async def test_a_skipped_frame_still_reaches_viewers(
    settings, session_factory, camera_id
) -> None:
    """The live view must stay smooth while the detector is idle.

    That is the point of skipping: the picture is unchanged, so the previous
    detections still describe it and the frame goes out carrying them.
    """
    gated = settings.model_copy(
        update={"motion_change_threshold": 3.0, "motion_force_interval_s": 3600.0}
    )
    hub = BroadcastHub()
    viewer = hub.subscribe(camera_id)

    await _run(gated, session_factory, camera_id, hub, ticks=6)

    message = decode_frame_message(await viewer.get())
    assert message.jpeg.startswith(b"\xff\xd8")
    # Marked so a client can tell a reused result from a fresh one.
    assert message.header["inference_skipped"] is True
    assert message.header["slots"][0]["code"] == "A1"
