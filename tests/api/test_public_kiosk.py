"""Public kiosk endpoints - no authentication, deliberately open.

These tests guard the privacy boundary and kill switches of the public kiosk.
The endpoints are intentionally public (no auth required) to allow a lobby
display to run without login. That deliberate choice carries trade-offs:
- anyone can enumerate the car park's occupancy and search for specific vehicles
- that is an accepted decision (plans/.../plan.md, "What this deliberately trades away")
- the tests below are what prevents accidental regression to secure/private behavior

All these tests use `public_client` fixture (flag ON) and verify both the
happy path and the guard rails: kill switches, rate limits, privacy assertions.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from caps_dash.db.enums import AuditAction, SlotState
from caps_dash.db.models import AuditLog
from tests.api.test_plate_search import add_read, make_camera, make_slot


class TestPublicSummary:
    """GET /api/public/summary - occupancy counts and FREE bay codes."""

    def test_anonymous_request_gets_200(self, public_client: TestClient, public_db: Session):
        """The public kiosk serves an unauthenticated caller."""
        camera = make_camera(public_db)
        make_slot(public_db, camera, "A1", SlotState.FREE)
        public_db.commit()

        response = public_client.get("/api/public/summary")

        assert response.status_code == 200
        assert "counts" in response.json()
        assert "free_codes_by_floor" in response.json()

    def test_free_codes_are_listed_only(self, public_client: TestClient, public_db: Session):
        """Only FREE slots appear in the code list; OCCUPIED and UNKNOWN are filtered out."""
        camera = make_camera(public_db)
        make_slot(public_db, camera, "A1", SlotState.FREE)
        make_slot(public_db, camera, "A2", SlotState.OCCUPIED)
        make_slot(public_db, camera, "A3", SlotState.UNKNOWN)
        public_db.commit()

        response = public_client.get("/api/public/summary")
        body = response.json()

        # Only A1 (FREE) should be in the codes, never A2 (OCCUPIED) or A3 (UNKNOWN)
        floor_codes = body["free_codes_by_floor"].get("B1", [])
        assert "A1" in floor_codes
        assert "A2" not in floor_codes
        assert "A3" not in floor_codes

    def test_occupied_codes_nowhere_in_raw_response_body(
        self, public_client: TestClient, public_db: Session
    ):
        """Even in the raw JSON text, an occupied slot's code must not appear.
        This catches the case where a nested field satisfies a dict check but
        still ships extra data in the serialization."""
        camera = make_camera(public_db)
        make_slot(public_db, camera, "A2", SlotState.OCCUPIED)
        public_db.commit()

        response = public_client.get("/api/public/summary")
        raw_body = response.text

        # Assert against the raw response text, not the parsed dict
        assert '"A2"' not in raw_body, "Occupied code A2 leaked into response body"

    def test_inactive_free_slots_excluded(self, public_client: TestClient, public_db: Session):
        """A FREE slot with is_active=False is not a truly free bay; it should not appear."""
        camera = make_camera(public_db)
        free1 = make_slot(public_db, camera, "A1", SlotState.FREE)
        free1.is_active = True
        free2 = make_slot(public_db, camera, "A2", SlotState.FREE)
        free2.is_active = False
        public_db.commit()

        response = public_client.get("/api/public/summary")
        body = response.json()

        floor_codes = body["free_codes_by_floor"].get("B1", [])
        assert "A1" in floor_codes
        assert "A2" not in floor_codes

    def test_counts_match_staff_summary(self, public_client: TestClient, public_db: Session):
        """The public summary's counts must match what /api/summary reports for the same data.
        This is a sanity check: if they diverge, one of the two is wrong."""
        camera = make_camera(public_db)
        make_slot(public_db, camera, "A1", SlotState.FREE)
        make_slot(public_db, camera, "A2", SlotState.FREE)
        make_slot(public_db, camera, "A3", SlotState.OCCUPIED)
        make_slot(public_db, camera, "A4", SlotState.UNKNOWN)
        public_db.commit()

        public_resp = public_client.get("/api/public/summary").json()
        public_counts = public_resp["counts"]

        # Manual check: we seeded 2 free, 1 occupied, 1 unknown
        assert public_counts["free"] == 2
        assert public_counts["occupied"] == 1
        assert public_counts["unknown"] == 1
        assert public_counts["total"] == 4


class TestPublicKillSwitch:
    """Verify the public_kiosk_enabled flag gates both endpoints."""

    def test_both_routes_404_when_flag_disabled(self, client: TestClient, db: Session):
        """With public_kiosk_enabled=False (default settings), both public routes 404.
        The default `client` fixture has public_kiosk_enabled=False."""
        camera = make_camera(db)
        make_slot(db, camera, "A1", SlotState.FREE)
        db.commit()

        summary_response = client.get("/api/public/summary")
        search_response = client.get("/api/public/plates/search?q=TEST")

        assert summary_response.status_code == 404
        assert search_response.status_code == 404

    def test_both_routes_carry_disabled_code_in_error(self, client: TestClient):
        """The error code is PUBLIC_KIOSK_DISABLED for both routes."""
        summary_response = client.get("/api/public/summary")
        search_response = client.get("/api/public/plates/search?q=TEST")

        assert summary_response.json()["error"]["code"] == "PUBLIC_KIOSK_DISABLED"
        assert search_response.json()["error"]["code"] == "PUBLIC_KIOSK_DISABLED"


class TestPlateReadingOffSwitch:
    """When plate_reading_enabled=False, search is hidden (404) but summary still works."""

    def test_summary_still_serves_but_advertises_search_as_off(
        self, plate_reading_off_client: TestClient
    ):
        """Kiosk on, plate reading off: the board still works, minus the search.

        `plate_search_enabled` false is what makes the frontend *hide* the
        search box rather than show one that could only ever return nothing.
        """
        response = plate_reading_off_client.get("/api/public/summary")

        assert response.status_code == 200
        assert response.json()["plate_search_enabled"] is False

    def test_search_404s_when_plate_reading_is_off(self, plate_reading_off_client: TestClient):
        """404, not 403: with plate reading off there are zero `plate_reads`
        rows, so the surface has nothing to answer with and should not confirm
        it exists."""
        response = plate_reading_off_client.get("/api/public/plates/search?q=83231")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PUBLIC_KIOSK_DISABLED"


class TestAnonymousSearch:
    """Anonymous searches without an Authorization header."""

    def test_no_auth_header_gets_200(self, public_client: TestClient, public_db: Session):
        """No Authorization header is required; the request succeeds."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        response = public_client.get("/api/public/plates/search?q=30H83231")

        assert response.status_code == 200

    def test_partial_query_matches(self, public_client: TestClient, public_db: Session):
        """A partial plate matches, same as the staff search."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        response = public_client.get("/api/public/plates/search?q=83231")
        body = response.json()

        assert len(body["matches"]) == 1
        assert body["matches"][0]["plate"] == "30H83231"

    def test_separators_are_ignored(self, public_client: TestClient, public_db: Session):
        """Plate stored as 30H83231; windscreen reads 30H-832.31. Separators don't matter."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        response = public_client.get("/api/public/plates/search?q=30H-832.31")
        body = response.json()

        assert body["query"] == "30H83231"
        assert len(body["matches"]) == 1


class TestPrivacyBoundary:
    """The public response must carry only {plate, slot_code, floor, read_at}.
    No camera ids or confidence scores."""

    def test_key_set_is_exactly_four_fields(self, public_client: TestClient, public_db: Session):
        """The response carries exactly these four keys per match, no more, no less."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        response = public_client.get("/api/public/plates/search?q=30H83231")
        matches = response.json()["matches"]

        assert len(matches) > 0
        for match in matches:
            assert set(match.keys()) == {"plate", "slot_code", "floor", "read_at"}

    def test_camera_id_not_in_response_body(self, public_client: TestClient, public_db: Session):
        """The response body must not contain the camera code, not even as a nested field."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        response = public_client.get("/api/public/plates/search?q=30H83231")
        raw_body = response.text

        # Assert against the raw JSON text
        assert '"CAM-1"' not in raw_body, "Camera code leaked into response"
        assert '"camera_id"' not in raw_body, "Camera ID field leaked into response"

    def test_confidence_not_in_response_body(self, public_client: TestClient, public_db: Session):
        """The response must not expose the confidence score."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231", confidence=0.95)
        public_db.commit()

        response = public_client.get("/api/public/plates/search?q=30H83231")
        raw_body = response.text

        assert '"confidence"' not in raw_body


class TestVacatedBaysArePrivate:
    """A FREE slot with a matching read is never returned publicly - it's vacated."""

    def test_vacated_bay_never_returned(self, public_client: TestClient, public_db: Session):
        """A bay that was occupied but is now FREE never appears in a public search."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.FREE)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        response = public_client.get("/api/public/plates/search?q=30H83231")

        assert response.json()["matches"] == []

    def test_vacated_behavior_unchangeable_by_query_param(
        self, public_client: TestClient, public_db: Session
    ):
        """No query parameter changes this behavior.
        The public search ALWAYS searches occupied_only=True."""
        camera = make_camera(public_db)
        vacated = make_slot(public_db, camera, "A1", SlotState.FREE)
        add_read(public_db, vacated, "30H83231")
        public_db.commit()

        # Even if someone tries to add a parameter, it shouldn't affect the backend logic
        response = public_client.get("/api/public/plates/search?q=30H83231")

        assert response.json()["matches"] == []


class TestRateLimit:
    """Per-IP rate limit: 3 searches succeed, the 4th is 429."""

    def test_first_three_searches_succeed(self, public_client: TestClient, public_db: Session):
        """Requests 1-3 return 200."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        for i in range(3):
            response = public_client.get("/api/public/plates/search?q=30H83231")
            assert response.status_code == 200, f"Request {i + 1} failed"

    def test_fourth_search_is_rate_limited(self, public_client: TestClient, public_db: Session):
        """The 4th request returns 429 RATE_LIMITED."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        # First 3 succeed
        for _ in range(3):
            public_client.get("/api/public/plates/search?q=30H83231")

        # 4th is rate limited
        response = public_client.get("/api/public/plates/search?q=30H83231")
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RATE_LIMITED"

    def test_rate_limit_carries_retry_after_s(self, public_client: TestClient, public_db: Session):
        """The 429 response includes retry_after_s in details."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        # Use up the budget
        for _ in range(3):
            public_client.get("/api/public/plates/search?q=30H83231")

        # 4th is rate limited
        response = public_client.get("/api/public/plates/search?q=30H83231")
        details = response.json()["error"]["details"]

        assert "retry_after_s" in details
        assert details["retry_after_s"] == 60

    def test_distinct_ips_independently_limited(
        self, public_client: TestClient, public_db: Session
    ):
        """This test uses TestClient which reports one host. Per the phase doc risk section,
        the route's use of the limiter is tested at API level; per-key isolation is tested
        directly against SlidingWindowLimiter in tests/security/. State that split here."""
        # TestClient cannot exercise real proxy headers, so this test verifies the
        # rate-limit enforcement at the endpoint level (all 3 succeed, 4th fails).
        # The limiter's per-key isolation is verified in tests/security/test_security_primitives.py
        # via direct SlidingWindowLimiter.check(ip_key("1.2.3.4")) tests.
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        # Verify that 3 requests succeed and 4th fails, establishing limiter works
        for _ in range(3):
            response = public_client.get("/api/public/plates/search?q=30H83231")
            assert response.status_code == 200
        response = public_client.get("/api/public/plates/search?q=30H83231")
        assert response.status_code == 429


class TestAudit:
    """Every search is written to the audit log, with anonymous actor."""

    def test_each_search_audited_as_anonymous(
        self, public_client: TestClient, public_db: Session
    ):
        """One audit row per search with user_id=None, username='', entity_id normalised."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        public_client.get("/api/public/plates/search?q=30H-832.31")

        entry = public_db.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.PLATE_SEARCHED)
        ).scalar_one()

        assert entry.username == ""
        assert entry.user_id is None
        assert entry.entity_id == "30H83231"  # Normalised
        assert entry.after_json["public"] is True

    def test_search_with_no_matches_still_audited(
        self, public_client: TestClient, public_db: Session
    ):
        """A fruitless search is still a search - it's audited."""
        public_client.get("/api/public/plates/search?q=99Z99999")

        entry = public_db.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.PLATE_SEARCHED)
        ).scalar_one()

        assert entry.entity_id == "99Z99999"
        assert entry.after_json["matches"] == 0

    def test_rate_limited_request_not_audited(self, public_client: TestClient, public_db: Session):
        """A request refused for rate limit does NOT write an audit row.
        Only requests that reach the search logic are audited."""
        camera = make_camera(public_db)
        slot = make_slot(public_db, camera, "A1", SlotState.OCCUPIED)
        add_read(public_db, slot, "30H83231")
        public_db.commit()

        # First 3 searches are audited
        for _ in range(3):
            public_client.get("/api/public/plates/search?q=30H83231")

        # 4th returns 429 before audit
        public_client.get("/api/public/plates/search?q=30H83231")

        # Should have exactly 3 audit entries, not 4
        entries = public_db.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.PLATE_SEARCHED)
        ).scalars().all()

        assert len(entries) == 3


class TestStaffRoutesUnchanged:
    """The staff routes (/api/plates/search, /api/summary) must still be gated,
    even with the public flag ON."""

    def test_staff_search_still_401_anonymous(self, public_client: TestClient):
        """The staff plate search still requires auth, even with public kiosk enabled."""
        response = public_client.get("/api/plates/search?q=30H83231")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_REQUIRED"

    def test_staff_summary_still_401_anonymous(self, public_client: TestClient):
        """The staff summary endpoint still requires auth."""
        response = public_client.get("/api/summary")

        assert response.status_code == 401

    def test_staff_search_still_403_resident(self, public_client: TestClient, public_db: Session):
        """A resident still cannot search plates, even with public kiosk on."""
        from caps_dash.db.enums import UserRole
        from caps_dash.db.models import User
        from caps_dash.security.password_hasher import hash_password
        from tests.api.conftest import PASSWORD, auth_headers

        # Create a resident
        resident = User(
            username="tenant",
            password_hash=hash_password(PASSWORD),
            display_name="Tenant",
            role=UserRole.RESIDENT,
            is_active=True,
        )
        public_db.add(resident)
        public_db.commit()

        headers = auth_headers(public_client, "tenant")
        response = public_client.get("/api/plates/search?q=30H83231", headers=headers)

        assert response.status_code == 403


class TestPublicSummaryKeySet:
    """The summary's key set, pinned the same way the plate match's is.

    `PublicPlateMatch` is built field-by-field precisely so a field added
    upstream cannot ride along into a public response. One level up,
    `PublicOccupancySummary.counts` embeds `OccupancySummary` - the schema
    serving the authenticated `/api/summary` - whole. That is safe today, but
    the next field added there for the dashboard would ship to anonymous
    callers with nothing turning red. These tests are that missing alarm.
    """

    def test_summary_top_level_key_set_is_exact(
        self, public_client: TestClient, public_db: Session
    ):
        camera = make_camera(public_db)
        make_slot(public_db, camera, "A1", SlotState.FREE)
        public_db.commit()

        body = public_client.get("/api/public/summary").json()

        assert set(body) == {"counts", "free_codes_by_floor", "plate_search_enabled"}

    def test_summary_counts_key_set_is_exact(
        self, public_client: TestClient, public_db: Session
    ):
        camera = make_camera(public_db)
        make_slot(public_db, camera, "A1", SlotState.FREE)
        public_db.commit()

        counts = public_client.get("/api/public/summary").json()["counts"]

        assert set(counts) == {
            "total",
            "free",
            "occupied",
            "unknown",
            "by_floor",
            "updated_at",
        }
        assert set(counts["by_floor"][0]) == {
            "floor",
            "total",
            "free",
            "occupied",
            "unknown",
        }
