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
from caps_dash.workers import inference_runner
from caps_dash.workers.camera_context import CameraContext, build_context
from caps_dash.workers.camera_loop import run_camera_loop
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
