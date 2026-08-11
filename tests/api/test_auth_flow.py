"""End-to-end authentication behaviour."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from caps_dash.db.enums import AuditAction
from caps_dash.db.models import AuditLog, RefreshSession, User
from caps_dash.security.refresh_cookie import COOKIE_NAME
from tests.api.conftest import PASSWORD, auth_headers, login, make_user


def test_login_returns_a_token_and_sets_the_refresh_cookie(
    client: TestClient, guard: User
) -> None:
    response = login(client, "guard")

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"] == {
        "username": "guard",
        "display_name": "Guard",
        "role": "security",
    }
    # The refresh token must NOT be in the body - it belongs in an httpOnly
    # cookie the page cannot read.
    assert "refresh_token" not in body
    assert COOKIE_NAME in response.cookies


def test_wrong_password_and_unknown_user_are_indistinguishable(
    client: TestClient, guard: User
) -> None:
    """Any difference here is a free account-enumeration oracle."""
    wrong_password = login(client, "guard", "not-the-password")
    unknown_user = login(client, "nobody-at-all", "not-the-password")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"]["code"] == unknown_user.json()["error"]["code"]
    assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]


def test_inactive_account_cannot_sign_in(client: TestClient, db: Session) -> None:
    make_user(db, "retired", is_active=False)
    response = login(client, "retired")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_protected_route_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_garbage_token_is_rejected(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.json()["error"]["code"] == "AUTH_TOKEN_INVALID"


def test_me_returns_the_signed_in_account(client: TestClient, guard: User) -> None:
    response = client.get("/api/auth/me", headers=auth_headers(client, "guard"))
    assert response.status_code == 200
    assert response.json()["username"] == "guard"


# --- Refresh rotation --------------------------------------------------------


def test_refresh_issues_a_new_access_token(client: TestClient, guard: User) -> None:
    login(client, "guard")
    response = client.post("/api/auth/refresh")
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_refresh_rotates_the_stored_session(
    client: TestClient, guard: User, db: Session
) -> None:
    login(client, "guard")
    client.post("/api/auth/refresh")

    rows = list(db.execute(select(RefreshSession).order_by(RefreshSession.id)).scalars())
    assert len(rows) == 2
    assert rows[0].rotated_at is not None, "the original session should be marked rotated"
    assert rows[1].rotated_at is None


def test_replaying_a_rotated_refresh_token_revokes_everything(
    client: TestClient, guard: User, db: Session
) -> None:
    """The theft case.

    Two parties now hold the same rotated token and there is no way to tell
    the legitimate user from the attacker, so every session is closed.
    """
    login(client, "guard")
    stolen = client.cookies[COOKIE_NAME]

    # Legitimate rotation; the stolen copy is now spent.
    assert client.post("/api/auth/refresh").status_code == 200

    client.cookies.set(COOKIE_NAME, stolen, path="/api/auth")
    replay = client.post("/api/auth/refresh")

    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "AUTH_SESSION_REUSED"

    db.expire_all()
    live = [row for row in db.execute(select(RefreshSession)).scalars() if row.revoked_at is None]
    assert live == [], "every session must be revoked after a replay"


def test_refresh_without_a_cookie_is_rejected(client: TestClient) -> None:
    assert client.post("/api/auth/refresh").status_code == 401


def test_an_access_token_cannot_be_used_as_a_refresh_token(
    client: TestClient, guard: User
) -> None:
    """Token confusion: `typ` is a required claim precisely to stop this."""
    access = login(client, "guard").json()["access_token"]
    client.cookies.set(COOKIE_NAME, access, path="/api/auth")

    response = client.post("/api/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_TYPE_MISMATCH"


# --- Logout ------------------------------------------------------------------


def test_logout_revokes_only_this_session(
    client: TestClient, guard: User, db: Session
) -> None:
    login(client, "guard")
    assert client.post("/api/auth/logout").status_code == 200

    db.expire_all()
    row = db.execute(select(RefreshSession)).scalar_one()
    assert row.revoked_at is not None


def test_logout_without_a_session_still_succeeds(client: TestClient) -> None:
    """The user asked to be signed out; they already are. Not an error."""
    assert client.post("/api/auth/logout").status_code == 200


def test_logout_all_invalidates_outstanding_access_tokens(
    client: TestClient, guard: User
) -> None:
    headers = auth_headers(client, "guard")
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    assert client.post("/api/auth/logout-all", headers=headers).status_code == 200

    # Access tokens are stateless, so only the token_version bump stops them.
    after = client.get("/api/auth/me", headers=headers)
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "AUTH_SESSION_REVOKED"


# --- Rate limiting -----------------------------------------------------------


def test_repeated_failures_are_rate_limited(client: TestClient, guard: User) -> None:
    for _ in range(3):  # login_max_attempts in the test settings
        assert login(client, "guard", "wrong").status_code == 401

    blocked = login(client, "guard", "wrong")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert blocked.headers.get("Retry-After")


def test_a_correct_password_still_works_below_the_limit(
    client: TestClient, guard: User
) -> None:
    login(client, "guard", "wrong")
    assert login(client, "guard").status_code == 200


# --- Password change ---------------------------------------------------------


def test_changing_password_signs_every_device_out(client: TestClient, guard: User) -> None:
    """Someone changing their password because it leaked must not leave the
    other party signed in."""
    headers = auth_headers(client, "guard")

    response = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "a-brand-new-secret"},
    )
    assert response.status_code == 200

    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert login(client, "guard", "a-brand-new-secret").status_code == 200


def test_changing_password_requires_the_current_one(client: TestClient, guard: User) -> None:
    response = client.post(
        "/api/auth/change-password",
        headers=auth_headers(client, "guard"),
        json={"current_password": "wrong", "new_password": "a-brand-new-secret"},
    )
    assert response.status_code == 401


def test_short_passwords_are_refused(client: TestClient, guard: User) -> None:
    response = client.post(
        "/api/auth/change-password",
        headers=auth_headers(client, "guard"),
        json={"current_password": PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422


# --- Sessions ----------------------------------------------------------------


def test_a_user_can_list_and_revoke_their_own_sessions(
    client: TestClient, guard: User
) -> None:
    headers = auth_headers(client, "guard")
    sessions = client.get("/api/auth/sessions", headers=headers).json()
    assert len(sessions) == 1

    revoked = client.delete(f"/api/auth/sessions/{sessions[0]['id']}", headers=headers)
    assert revoked.status_code == 204
    assert client.get("/api/auth/sessions", headers=headers).json() == []


def test_revoking_someone_elses_session_is_a_404(
    client: TestClient, guard: User, db: Session
) -> None:
    """Scoped to the caller's own list, so another user's id cannot be probed."""
    other = make_user(db, "other")
    other_session = RefreshSession(
        user_id=other.id, jti="someone-elses", expires_at=guard.created_at
    )
    db.add(other_session)
    db.commit()

    response = client.delete(
        f"/api/auth/sessions/{other_session.id}", headers=auth_headers(client, "guard")
    )
    assert response.status_code == 404


# --- Audit -------------------------------------------------------------------


def test_login_is_audited_without_recording_the_password(
    client: TestClient, guard: User, db: Session
) -> None:
    login(client, "guard")

    entry = db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.LOGIN)
    ).scalar_one()
    assert entry.username == "guard"
    assert entry.request_id != ""
    serialised = f"{entry.before_json}{entry.after_json}"
    assert PASSWORD not in serialised
