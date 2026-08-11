"""Models persist and read back correctly."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import dialect as SQLiteDialect
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType, SlotState, UserRole
from caps_dash.db.models import Camera, ParkingSlot, SlotStateHistory, User
from caps_dash.db.types import UtcDateTime, utc_now


def _camera(code: str = "01", **kwargs: object) -> Camera:
    defaults: dict[str, object] = {
        "code": code,
        "name": "Basement north",
        "floor": "B1",
        "source_type": CameraSourceType.ESP32CAM_HTTP,
        "source_url": "192.168.1.50",
    }
    return Camera(**{**defaults, **kwargs})


def test_camera_and_slots_roundtrip(db_session: Session) -> None:
    camera = _camera()
    camera.slots = [
        ParkingSlot(
            code="A1",
            polygon_json=[[10.0, 20.0], [30.0, 20.0], [30.0, 40.0]],
            src_frame_width=1600,
            src_frame_height=900,
        )
    ]
    db_session.add(camera)
    db_session.commit()

    loaded = db_session.execute(select(Camera).where(Camera.code == "01")).scalar_one()
    assert loaded.slots[0].polygon_json == [[10.0, 20.0], [30.0, 20.0], [30.0, 40.0]]
    # The source frame size travels with the polygon; without it the two axis
    # scale factors cannot be computed.
    assert (loaded.slots[0].src_frame_width, loaded.slots[0].src_frame_height) == (1600, 900)
    assert loaded.slots[0].current_state == SlotState.UNKNOWN


def test_deleting_a_camera_cascades_to_its_slots(db_session: Session) -> None:
    camera = _camera()
    camera.slots = [ParkingSlot(code="A1", polygon_json=[[0, 0], [1, 0], [1, 1]])]
    db_session.add(camera)
    db_session.commit()

    db_session.delete(camera)
    db_session.commit()

    assert db_session.execute(select(ParkingSlot)).scalars().all() == []


def test_slot_code_must_be_unique_within_a_camera(db_session: Session) -> None:
    camera = _camera()
    camera.slots = [
        ParkingSlot(code="A1", polygon_json=[[0, 0]]),
        ParkingSlot(code="A1", polygon_json=[[1, 1]]),
    ]
    db_session.add(camera)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_slot_code_is_allowed_on_a_different_camera(db_session: Session) -> None:
    first = _camera("01")
    first.slots = [ParkingSlot(code="A1", polygon_json=[[0, 0]])]
    second = _camera("02")
    second.slots = [ParkingSlot(code="A1", polygon_json=[[0, 0]])]
    db_session.add_all([first, second])
    db_session.commit()
    assert len(db_session.execute(select(ParkingSlot)).scalars().all()) == 2


def test_vote_threshold_above_window_is_rejected(db_session: Session) -> None:
    """Unreachable threshold: the camera would sit at UNKNOWN forever."""
    db_session.add(_camera("03", vote_window=3, vote_threshold=5))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invalid_role_is_rejected(db_session: Session) -> None:
    db_session.add(User(username="bob", password_hash="x", role="superuser"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_valid_role_is_accepted(db_session: Session) -> None:
    db_session.add(User(username="bob", password_hash="x", role=UserRole.ADMIN))
    db_session.commit()
    assert db_session.execute(select(User)).scalar_one().role == "admin"


def test_timestamps_come_back_timezone_aware_utc(db_session: Session) -> None:
    db_session.add(_camera("04"))
    db_session.commit()
    camera = db_session.execute(select(Camera).where(Camera.code == "04")).scalar_one()
    assert camera.created_at.tzinfo is not None
    assert camera.created_at.utcoffset() == dt.timedelta(0)


def test_utc_datetime_type_rejects_naive_values() -> None:
    """Assuming a naive value is UTC is how a database ends up holding both."""
    with pytest.raises(ValueError, match="naive datetime rejected"):
        UtcDateTime().process_bind_param(
            dt.datetime(2026, 8, 11, 12, 0, 0),
            SQLiteDialect(),
        )


def test_writing_a_naive_datetime_fails_the_statement(db_session: Session) -> None:
    """End to end: SQLAlchemy wraps the rejection, but the write still fails."""
    camera = _camera("05")
    camera.last_seen_at = dt.datetime(2026, 8, 11, 12, 0, 0)
    db_session.add(camera)
    with pytest.raises(StatementError, match="naive datetime rejected"):
        db_session.commit()


def test_history_rows_carry_a_clock_suspect_flag(db_session: Session) -> None:
    camera = _camera("06")
    slot = ParkingSlot(code="A1", polygon_json=[[0, 0]])
    camera.slots = [slot]
    db_session.add(camera)
    db_session.commit()

    db_session.add(
        SlotStateHistory(
            slot_id=slot.id,
            camera_code="06",
            slot_code="A1",
            previous_state=SlotState.FREE,
            new_state=SlotState.OCCUPIED,
            changed_at=utc_now(),
        )
    )
    db_session.commit()

    row = db_session.execute(select(SlotStateHistory)).scalar_one()
    # The board has no RTC battery; the flag is how reports stay honest.
    assert row.clock_suspect is False
