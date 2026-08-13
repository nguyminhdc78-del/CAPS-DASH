"""When a plate is read, and when it is deliberately not.

The reader itself is covered in `tests/vision/test_plate_reader.py`. This file
covers the decision to call it at all - which is where the cost lives (about a
second of the single inference worker) and where the privacy promise lives (a
plate is stored only when a car arrives, never on a schedule).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.models import Base, Camera, ParkingSlot, PlateRead
from caps_dash.db.session import create_session_factory, session_scope
from caps_dash.observability.logging_setup import get_logger
from caps_dash.vision.domain import Slot, SlotMap, SlotState
from caps_dash.workers import plate_capture
from caps_dash.workers.plate_capture import read_plates_for_filled_slots
from caps_dash.workers.state_tracker import SlotChange

POLYGON = [(40.0, 260.0), (300.0, 260.0), (300.0, 440.0), (40.0, 440.0)]


class _Read:
    """Stands in for `PlateRead` from the reader."""

    def __init__(self, plate: str, confidence: float = 0.9, width_px: int = 140) -> None:
        self.plate = plate
        self.confidence = confidence
        self.width_px = width_px
        self.process_ms = 900.0


class _Context:
    """The parts of `CameraContext` this module touches, and nothing else."""

    def __init__(self, settings: Settings, session_factory, pool: ThreadPoolExecutor) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.camera_id = 1
        self.loop = asyncio.get_event_loop()
        self.inference_pool = pool
        self.db_pool = pool


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="dev",
        secret_key="plate-capture-test-signing-key-padded",
        database_url=f"sqlite:///{tmp_path / 'plates.db'}",
        detector_backend="fake",
        plate_reading_enabled=True,
        log_json=False,
    )


@pytest.fixture
def session_factory(settings: Settings):
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        session.add(
            Camera(id=1, code="CAM-1", source_type="fake", source_url="", poll_interval_s=1.0)
        )
        session.add(
            ParkingSlot(
                camera_id=1,
                code="A1",
                floor="B1",
                polygon_json=[[40, 260], [300, 260], [300, 440], [40, 440]],
                src_frame_width=640,
                src_frame_height=480,
                current_state="OCCUPIED",
            )
        )
    yield factory
    engine.dispose()


@pytest.fixture
def pool():
    with ThreadPoolExecutor(max_workers=1) as executor:
        yield executor


def frame() -> np.ndarray:
    return np.full((480, 640, 3), 90, dtype=np.uint8)


def slot_map() -> SlotMap:
    return SlotMap(slots=[Slot(id="A1", polygon=POLYGON)], width=640, height=480)


def arrival(code: str = "A1") -> SlotChange:
    return SlotChange(slot_code=code, previous=SlotState.FREE, new=SlotState.OCCUPIED)


def departure(code: str = "A1") -> SlotChange:
    return SlotChange(slot_code=code, previous=SlotState.OCCUPIED, new=SlotState.FREE)


async def run(context, changes, monkeypatch, reads: list, *, calls: list | None = None):
    """Drive the module with a scripted reader, recording every call."""

    def fake_read(image: np.ndarray, polygon: list, confidence: float) -> _Read | None:
        if calls is not None:
            calls.append((polygon, confidence))
        return reads.pop(0) if reads else None

    monkeypatch.setattr(plate_capture, "read_plate", fake_read)
    await read_plates_for_filled_slots(
        context, changes, frame(), slot_map(), get_logger("test")
    )


def stored(session_factory) -> list[PlateRead]:
    with session_scope(session_factory) as session:
        return list(session.execute(select(PlateRead)).scalars().all())


# --- when the reader runs at all ---------------------------------------------


@pytest.mark.asyncio
async def test_an_arrival_is_read_and_stored(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    context = _Context(settings, session_factory, pool)

    await run(context, [arrival()], monkeypatch, [_Read("30H83231")])

    rows = stored(session_factory)
    assert [row.plate for row in rows] == ["30H83231"]
    assert rows[0].camera_id == 1
    assert rows[0].plate_width_px == 140


@pytest.mark.asyncio
async def test_a_departure_is_not_read(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    """A bay emptying has nothing to photograph. Reading it would spend a
    second of the board's single inference worker to look at tarmac."""
    context = _Context(settings, session_factory, pool)
    calls: list = []

    await run(context, [departure()], monkeypatch, [_Read("30H83231")], calls=calls)

    assert calls == []
    assert stored(session_factory) == []


@pytest.mark.asyncio
async def test_nothing_runs_when_the_feature_is_off(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    """The default. Off must mean the reader is never called - not that its
    result is discarded, which would still cost the second and still download
    the models."""
    settings = settings.model_copy(update={"plate_reading_enabled": False})
    context = _Context(settings, session_factory, pool)
    calls: list = []

    await run(context, [arrival()], monkeypatch, [_Read("30H83231")], calls=calls)

    assert calls == []
    assert stored(session_factory) == []


@pytest.mark.asyncio
async def test_a_slot_missing_from_the_map_is_skipped(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    """The slot map was redrawn between the detection and this write. Ordinary
    during ROI editing, and not a reason to raise inside a camera loop."""
    context = _Context(settings, session_factory, pool)
    calls: list = []

    await run(context, [arrival("B9")], monkeypatch, [_Read("30H83231")], calls=calls)

    assert calls == []
    assert stored(session_factory) == []


# --- what gets stored --------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unreadable_plate_stores_nothing(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    """The ordinary outcome for a car parked nose-in. Storing a row with an
    empty plate would put a permanent unanswerable entry in a personal-data
    table."""
    context = _Context(settings, session_factory, pool)

    await run(context, [arrival()], monkeypatch, [])

    assert stored(session_factory) == []


@pytest.mark.asyncio
async def test_a_bumper_sticker_is_not_stored_as_a_plate(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    """`TOYOTA` read off a tailgate is not a plate, and a guard searching for
    a car should never be shown one."""
    context = _Context(settings, session_factory, pool)

    await run(context, [arrival()], monkeypatch, [_Read("TOYOTA")])

    assert stored(session_factory) == []


@pytest.mark.asyncio
async def test_a_doubtful_read_is_stored_with_its_confidence(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    """Kept, not discarded: a doubtful read a guard can weigh beats no answer
    at all, which is why the confidence and pixel width travel with it."""
    context = _Context(settings, session_factory, pool)

    await run(context, [arrival()], monkeypatch, [_Read("30H83231", confidence=0.34, width_px=62)])

    rows = stored(session_factory)
    assert len(rows) == 1
    assert rows[0].confidence == pytest.approx(0.34)
    assert rows[0].plate_width_px == 62


@pytest.mark.asyncio
async def test_the_reader_gets_the_bay_it_was_asked_about(
    settings, session_factory, pool, monkeypatch: pytest.MonkeyPatch
):
    """The polygon is what turns a 2642 ms whole-frame read into a ~1000 ms
    crop. Passing the wrong one - or none - would silently undo the entire
    reason this is affordable."""
    context = _Context(settings, session_factory, pool)
    calls: list = []

    await run(context, [arrival()], monkeypatch, [_Read("30H83231")], calls=calls)

    assert len(calls) == 1
    assert calls[0][0] == POLYGON
