"""`hourly_aggregation_service`: correct per-hour totals, and re-running the
same hour never doubles a row - the upsert is keyed on
`(scope_type, scope_key, hour_start)`, matching `HourlyStat`'s
`scope_hour_unique` constraint.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType, ScopeType, SlotState
from caps_dash.db.models import Camera, HourlyStat, ParkingSlot, SlotStateHistory
from caps_dash.services import hourly_aggregation_service

HOUR = dt.datetime(2026, 8, 11, 8, 0, 0, tzinfo=dt.UTC)


def _seed_one_slot(db_session: Session) -> ParkingSlot:
    camera = Camera(code="CAM-A", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    slot = ParkingSlot(code="A1", floor="B1")
    camera.slots = [slot]
    db_session.add(camera)
    db_session.commit()

    # No row before HOUR: the slot starts the hour at its default UNKNOWN,
    # occupied for 10..40 minutes in, free for the rest.
    db_session.add_all(
        [
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.UNKNOWN, new_state=SlotState.OCCUPIED,
                changed_at=HOUR + dt.timedelta(minutes=10),
            ),
            SlotStateHistory(
                slot_id=slot.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state=SlotState.OCCUPIED, new_state=SlotState.FREE,
                changed_at=HOUR + dt.timedelta(minutes=40),
            ),
        ]
    )
    db_session.commit()
    return slot


def _stat(db_session: Session, *, scope_type: str, scope_key: str) -> HourlyStat:
    return db_session.execute(
        select(HourlyStat).where(
            HourlyStat.scope_type == scope_type,
            HourlyStat.scope_key == scope_key,
            HourlyStat.hour_start == HOUR,
        )
    ).scalar_one()


def test_one_hour_produces_correct_slot_floor_and_site_totals(db_session: Session) -> None:
    slot = _seed_one_slot(db_session)

    hourly_aggregation_service.rebuild_hours(db_session, since=HOUR, until=HOUR)

    for scope_type, scope_key in (
        (ScopeType.SLOT, str(slot.id)),
        (ScopeType.FLOOR, "B1"),
        (ScopeType.SITE, ""),
    ):
        row = _stat(db_session, scope_type=scope_type, scope_key=scope_key)
        # 0-10min UNKNOWN, 10-40min OCCUPIED, 40-60min FREE.
        assert row.unknown_seconds == 600
        assert row.occupied_seconds == 1800
        assert row.free_seconds == 1200
        assert row.change_count == 2
        assert row.peak_occupied == 1
        assert row.clock_suspect is False


def test_rerunning_the_same_hour_upserts_in_place_never_duplicates(db_session: Session) -> None:
    _seed_one_slot(db_session)

    hourly_aggregation_service.rebuild_hours(db_session, since=HOUR, until=HOUR)
    first = _stat(db_session, scope_type=ScopeType.SITE, scope_key="")
    first_id = first.id

    hours_processed = hourly_aggregation_service.rebuild_hours(db_session, since=HOUR, until=HOUR)

    assert hours_processed == 1
    all_site_rows = db_session.execute(
        select(HourlyStat).where(HourlyStat.scope_type == ScopeType.SITE)
    ).scalars().all()
    assert len(all_site_rows) == 1  # not doubled

    second = _stat(db_session, scope_type=ScopeType.SITE, scope_key="")
    assert second.id == first_id  # same row, updated in place - not a new insert
    assert second.occupied_seconds == first.occupied_seconds
    assert second.free_seconds == first.free_seconds
    assert second.unknown_seconds == first.unknown_seconds
    assert second.change_count == first.change_count


def test_a_slot_occupied_the_whole_hour_with_no_change_rows_still_aggregates(
    db_session: Session,
) -> None:
    """A slot that never changed state in this hour must still be accounted
    for using its seed state - not silently skipped for having no rows."""
    camera = Camera(code="CAM-B", name="Deck B", floor="B2", source_type=CameraSourceType.FAKE)
    slot = ParkingSlot(code="B1", floor="B2")
    camera.slots = [slot]
    db_session.add(camera)
    db_session.commit()
    # The transition into OCCUPIED happened before HOUR; nothing changes
    # during HOUR itself.
    db_session.add(
        SlotStateHistory(
            slot_id=slot.id, camera_code="CAM-B", slot_code="B1", floor="B2",
            previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED,
            changed_at=HOUR - dt.timedelta(minutes=30),
        )
    )
    db_session.commit()

    hourly_aggregation_service.rebuild_hours(db_session, since=HOUR, until=HOUR)

    row = _stat(db_session, scope_type=ScopeType.SLOT, scope_key=str(slot.id))
    assert row.occupied_seconds == 3600
    assert row.change_count == 0
    assert row.peak_occupied == 1


def test_an_hour_written_entirely_under_a_suspect_clock_is_skipped(db_session: Session) -> None:
    camera = Camera(code="CAM-C", name="Deck C", floor="B1", source_type=CameraSourceType.FAKE)
    slot = ParkingSlot(code="C1", floor="B1")
    camera.slots = [slot]
    db_session.add(camera)
    db_session.commit()
    db_session.add(
        SlotStateHistory(
            slot_id=slot.id, camera_code="CAM-C", slot_code="C1", floor="B1",
            previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED,
            changed_at=HOUR + dt.timedelta(minutes=5), clock_suspect=True,
        )
    )
    db_session.commit()

    hourly_aggregation_service.rebuild_hours(db_session, since=HOUR, until=HOUR)

    existing = db_session.execute(
        select(HourlyStat).where(HourlyStat.hour_start == HOUR)
    ).scalars().all()
    assert existing == []
