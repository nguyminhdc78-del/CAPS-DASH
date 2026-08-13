"""Finding a car by its plate - the guard's "where did they park?".

Two things here are not conveniences and are tested as such: a resident cannot
reach this endpoint at all, and every search lands in the audit log. A plate
identifies a vehicle and through it a person, so who asked and what they asked
has to be answerable afterwards.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from caps_dash.db.enums import AuditAction, SlotState
from caps_dash.db.models import AuditLog, Camera, ParkingSlot, PlateRead
from tests.api.conftest import auth_headers

SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]


def make_slot(db: Session, camera: Camera, code: str, state: str) -> ParkingSlot:
    slot = ParkingSlot(
        camera_id=camera.id,
        code=code,
        floor="B1",
        polygon_json=SQUARE,
        src_frame_width=640,
        src_frame_height=480,
        current_state=state,
    )
    db.add(slot)
    db.flush()
    return slot


def make_camera(db: Session, code: str = "CAM-1") -> Camera:
    camera = Camera(code=code, source_type="fake", source_url="", poll_interval_s=1.0)
    db.add(camera)
    db.flush()
    return camera


def add_read(
    db: Session,
    slot: ParkingSlot,
    plate: str,
    *,
    minutes_ago: int = 0,
    confidence: float = 0.9,
    width: int = 140,
) -> None:
    db.add(
        PlateRead(
            slot_id=slot.id,
            camera_id=slot.camera_id,
            plate=plate,
            confidence=confidence,
            plate_width_px=width,
            # Timezone-aware on purpose: `UtcDateTime` rejects naive values, and
            # that guard is the reason this project's timestamps are comparable
            # at all.
            read_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=minutes_ago),
        )
    )
    db.flush()


# --- who may ask -------------------------------------------------------------


def test_a_resident_cannot_search_plates(client: TestClient, resident):
    """The promise in project-overview-pdr.md is that residents are never shown
    which bay holds which car. This route is one role change away from
    breaking it, which is why the check is a test and not a comment."""
    response = client.get("/api/plates/search?q=30H83231", headers=auth_headers(client, "tenant"))

    assert response.status_code == 403


def test_an_anonymous_request_cannot_search_plates(client: TestClient):
    assert client.get("/api/plates/search?q=30H83231").status_code == 401


def test_a_guard_can_search(client: TestClient, guard, db: Session):
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.OCCUPIED)
    add_read(db, slot, "30H83231")
    db.commit()

    response = client.get("/api/plates/search?q=30H83231", headers=auth_headers(client, "guard"))

    assert response.status_code == 200
    assert [m["slot_code"] for m in response.json()["matches"]] == ["A1"]


# --- what it answers ---------------------------------------------------------


def test_the_separators_a_guard_types_do_not_matter(client: TestClient, guard, db: Session):
    """A plate is stored `30H83231`; a windscreen reads `30H-832.31`. Making
    the guard guess which convention the database used would be a search that
    only works when you already know the answer."""
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.OCCUPIED)
    add_read(db, slot, "30H83231")
    db.commit()

    response = client.get("/api/plates/search?q=30H-832.31", headers=auth_headers(client, "guard"))

    body = response.json()
    assert body["query"] == "30H83231"
    assert len(body["matches"]) == 1


def test_a_partial_plate_matches(client: TestClient, guard, db: Session):
    """A driver half-remembers their own number more often than not."""
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.OCCUPIED)
    add_read(db, slot, "30H83231")
    db.commit()

    response = client.get("/api/plates/search?q=83231", headers=auth_headers(client, "guard"))

    assert len(response.json()["matches"]) == 1


def test_a_query_too_short_to_be_a_search_returns_nothing(client: TestClient, guard, db: Session):
    """Two characters match nearly every plate, at which point the result is
    noise dressed as an answer."""
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.OCCUPIED)
    add_read(db, slot, "30H83231")
    db.commit()

    response = client.get("/api/plates/search?q=30", headers=auth_headers(client, "guard"))

    assert response.json()["matches"] == []


def test_a_bay_the_car_has_left_is_not_offered(client: TestClient, guard, db: Session):
    """Sending a guard to a bay the car has left is worse than saying nothing,
    because they will trust it and walk there."""
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.FREE)
    add_read(db, slot, "30H83231")
    db.commit()

    response = client.get("/api/plates/search?q=30H83231", headers=auth_headers(client, "guard"))

    assert response.json()["matches"] == []


def test_a_vacated_bay_is_findable_when_explicitly_asked_for(
    client: TestClient, guard, db: Session
):
    """"Where was it last seen" is a different and rarer question - an
    investigation rather than a lost driver - and has to be asked for."""
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.FREE)
    add_read(db, slot, "30H83231")
    db.commit()

    response = client.get(
        "/api/plates/search?q=30H83231&include_vacated=true", headers=auth_headers(client, "guard")
    )

    assert [m["slot_code"] for m in response.json()["matches"]] == ["A1"]


def test_a_bay_reports_its_newest_occupant_not_an_older_one(
    client: TestClient, guard, db: Session
):
    """The failure this prevents: a car parked in A1 this morning and left; a
    different car is there now. Searching the first plate must not send a
    guard to A1, where they would find a stranger's car."""
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.OCCUPIED)
    add_read(db, slot, "11A11111", minutes_ago=120)
    add_read(db, slot, "30H83231", minutes_ago=1)
    db.commit()

    stale = client.get("/api/plates/search?q=11A11111", headers=auth_headers(client, "guard"))
    current = client.get("/api/plates/search?q=30H83231", headers=auth_headers(client, "guard"))

    assert stale.json()["matches"] == []
    assert [m["slot_code"] for m in current.json()["matches"]] == ["A1"]


def test_the_reading_carries_its_own_provenance(client: TestClient, guard, db: Session):
    """A plate read at 62 px with 0.31 confidence is a lead to check, not a
    fact. Returning the numbers is what lets a guard tell the two apart."""
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.OCCUPIED)
    add_read(db, slot, "30H83231", confidence=0.31, width=62)
    db.commit()

    match = client.get(
        "/api/plates/search?q=30H83231", headers=auth_headers(client, "guard")
    ).json()["matches"][0]

    assert match["confidence"] == 0.31
    assert match["plate_width_px"] == 62
    assert match["camera_code"] == "CAM-1"


# --- the audit trail ---------------------------------------------------------


def test_every_search_is_audited(client: TestClient, guard, db: Session):
    camera = make_camera(db)
    slot = make_slot(db, camera, "A1", SlotState.OCCUPIED)
    add_read(db, slot, "30H83231")
    db.commit()

    client.get("/api/plates/search?q=30H-832.31", headers=auth_headers(client, "guard"))

    entry = db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.PLATE_SEARCHED)
    ).scalar_one()
    assert entry.username == "guard"
    # The normalised form, so the log can be searched the same way the table is.
    assert entry.entity_id == "30H83231"


def test_a_search_that_found_nothing_is_audited_too(client: TestClient, guard, db: Session):
    """"Who went looking for this plate" is exactly the question an audit of a
    plate database exists to answer, and a fruitless search was still a
    search."""
    client.get("/api/plates/search?q=99Z99999", headers=auth_headers(client, "guard"))

    entry = db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.PLATE_SEARCHED)
    ).scalar_one()
    assert entry.entity_id == "99Z99999"
