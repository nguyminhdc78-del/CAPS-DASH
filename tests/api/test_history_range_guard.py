"""`/history`: mandatory + capped date range, filters, ordering, RBAC."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from caps_dash.db.enums import CameraSourceType
from caps_dash.db.models import Camera, ParkingSlot, SlotStateHistory, User
from tests.api.conftest import auth_headers


def _seed_history(db: Session, *, now: dt.datetime) -> dict[str, ParkingSlot]:
    camera_a = Camera(code="CAM-A", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE)
    camera_b = Camera(code="CAM-B", name="Deck B", floor="B2", source_type=CameraSourceType.FAKE)
    db.add_all([camera_a, camera_b])
    db.commit()

    slot_a1 = ParkingSlot(camera_id=camera_a.id, code="A1", floor="B1")
    slot_b1 = ParkingSlot(camera_id=camera_b.id, code="B1", floor="B2")
    db.add_all([slot_a1, slot_b1])
    db.commit()

    db.add_all(
        [
            # Within the default 7-day span.
            SlotStateHistory(
                slot_id=slot_a1.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state="UNKNOWN", new_state="FREE",
                changed_at=now - dt.timedelta(days=3),
            ),
            SlotStateHistory(
                slot_id=slot_a1.id, camera_code="CAM-A", slot_code="A1", floor="B1",
                previous_state="FREE", new_state="OCCUPIED",
                changed_at=now - dt.timedelta(hours=1),
            ),
            # Outside the default span, inside the max span - only visible
            # when the caller asks for a wider explicit range.
            SlotStateHistory(
                slot_id=slot_b1.id, camera_code="CAM-B", slot_code="B1", floor="B2",
                previous_state="UNKNOWN", new_state="FREE",
                changed_at=now - dt.timedelta(days=30),
            ),
        ]
    )
    db.commit()
    return {"A1": slot_a1, "B1": slot_b1}


def test_omitted_range_defaults_to_the_configured_span(
    client: TestClient, db: Session, guard: User
) -> None:
    now = dt.datetime.now(dt.UTC)
    _seed_history(db, now=now)

    response = client.get("/api/history", headers=auth_headers(client, "guard"))

    assert response.status_code == 200
    body = response.json()
    # Only the two CAM-A rows fall inside the default 7-day span; the 30-day-
    # old CAM-B row does not.
    assert body["total"] == 2
    assert {item["camera_code"] for item in body["items"]} == {"CAM-A"}


def test_a_400_day_span_is_rejected_with_range_too_wide(
    client: TestClient, db: Session, guard: User
) -> None:
    now = dt.datetime.now(dt.UTC)
    _seed_history(db, now=now)

    response = client.get(
        "/api/history",
        params={"from": (now - dt.timedelta(days=400)).isoformat(), "to": now.isoformat()},
        headers=auth_headers(client, "guard"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RANGE_TOO_WIDE"


def test_from_after_to_is_rejected_with_range_invalid(
    client: TestClient, db: Session, guard: User
) -> None:
    now = dt.datetime.now(dt.UTC)
    _seed_history(db, now=now)

    response = client.get(
        "/api/history",
        params={"from": now.isoformat(), "to": (now - dt.timedelta(days=1)).isoformat()},
        headers=auth_headers(client, "guard"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RANGE_INVALID"


def test_naive_datetime_is_rejected(client: TestClient, db: Session, guard: User) -> None:
    """No UTC offset on `from` - `db/types.py` insists on aware datetimes
    everywhere, and the query params are typed `AwareDatetime` to match."""
    now = dt.datetime.now(dt.UTC)
    _seed_history(db, now=now)

    response = client.get(
        "/api/history",
        params={"from": now.replace(tzinfo=None).isoformat()},
        headers=auth_headers(client, "guard"),
    )

    assert response.status_code == 422


def test_filters_narrow_the_result_within_an_explicit_range(
    client: TestClient, db: Session, guard: User
) -> None:
    now = dt.datetime.now(dt.UTC)
    _seed_history(db, now=now)

    response = client.get(
        "/api/history",
        params={
            "from": (now - dt.timedelta(days=40)).isoformat(),
            "to": now.isoformat(),
            "camera_code": "CAM-B",
        },
        headers=auth_headers(client, "guard"),
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["camera_code"] == "CAM-B"
    assert body["items"][0]["floor"] == "B2"


def test_filters_by_slot_id_and_floor(client: TestClient, db: Session, guard: User) -> None:
    now = dt.datetime.now(dt.UTC)
    slots = _seed_history(db, now=now)

    response = client.get(
        "/api/history",
        params={
            "from": (now - dt.timedelta(days=40)).isoformat(),
            "to": now.isoformat(),
            "slot_id": slots["A1"].id,
            "floor": "B1",
        },
        headers=auth_headers(client, "guard"),
    )

    body = response.json()
    assert body["total"] == 2
    assert {item["slot_id"] for item in body["items"]} == {slots["A1"].id}


def test_results_are_ordered_newest_first(
    client: TestClient, db: Session, guard: User
) -> None:
    now = dt.datetime.now(dt.UTC)
    _seed_history(db, now=now)

    response = client.get(
        "/api/history",
        params={"from": (now - dt.timedelta(days=40)).isoformat(), "to": now.isoformat()},
        headers=auth_headers(client, "guard"),
    )

    changed_at_values = [item["changed_at"] for item in response.json()["items"]]
    assert changed_at_values == sorted(changed_at_values, reverse=True)


def test_resident_is_forbidden(client: TestClient, db: Session, resident: User) -> None:
    now = dt.datetime.now(dt.UTC)
    _seed_history(db, now=now)

    response = client.get("/api/history", headers=auth_headers(client, "tenant"))
    assert response.status_code == 403
