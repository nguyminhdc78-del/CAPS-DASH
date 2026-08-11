"""Role ranking, enforced through real endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from caps_dash.db.enums import UserRole
from caps_dash.db.models import User
from caps_dash.errors.exceptions import ForbiddenError
from caps_dash.security.current_user import CurrentUser
from caps_dash.security.rbac import assert_role, has_at_least, rank_of
from tests.api.conftest import auth_headers


def test_admin_reaches_an_admin_only_route(client: TestClient, admin: User) -> None:
    assert client.get("/api/users", headers=auth_headers(client, "boss")).status_code == 200


def test_guard_is_refused_an_admin_only_route(client: TestClient, guard: User) -> None:
    response = client.get("/api/users", headers=auth_headers(client, "guard"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_resident_is_refused_too(client: TestClient, resident: User) -> None:
    response = client.get("/api/users", headers=auth_headers(client, "tenant"))
    assert response.status_code == 403


def test_ranking_is_inclusive_not_exact() -> None:
    """The reason for ranks: admin inherits everything security can do, without
    every route having to list both roles."""
    assert has_at_least(UserRole.ADMIN, UserRole.SECURITY)
    assert has_at_least(UserRole.ADMIN, UserRole.RESIDENT)
    assert has_at_least(UserRole.SECURITY, UserRole.RESIDENT)
    assert has_at_least(UserRole.SECURITY, UserRole.SECURITY)

    assert not has_at_least(UserRole.RESIDENT, UserRole.SECURITY)
    assert not has_at_least(UserRole.SECURITY, UserRole.ADMIN)


def test_an_unknown_role_has_no_privileges() -> None:
    """A role string that is not in the table must fail closed, not open."""
    assert rank_of("superuser") == 0
    assert not has_at_least("superuser", UserRole.RESIDENT)


def test_assert_role_raises_for_an_insufficient_role() -> None:
    """Shared with the WebSocket layer, which cannot use the HTTP dependency."""
    user = CurrentUser(id=1, username="tenant", role=UserRole.RESIDENT)
    with pytest.raises(ForbiddenError):
        assert_role(user, UserRole.SECURITY)


def test_assert_role_allows_a_sufficient_role() -> None:
    user = CurrentUser(id=1, username="boss", role=UserRole.ADMIN)
    assert_role(user, UserRole.SECURITY)


# --- Admin user management ---------------------------------------------------


def test_admin_can_create_and_update_a_user(client: TestClient, admin: User) -> None:
    headers = auth_headers(client, "boss")

    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "newguard",
            "password": "a-long-enough-password",
            "display_name": "New Guard",
            "role": "security",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert "password" not in created.text
    assert "password_hash" not in created.text

    updated = client.patch(
        f"/api/users/{user_id}", headers=headers, json={"role": "resident"}
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "resident"


def test_duplicate_username_is_a_conflict(client: TestClient, admin: User) -> None:
    headers = auth_headers(client, "boss")
    payload = {"username": "dupe", "password": "a-long-enough-password"}
    assert client.post("/api/users", headers=headers, json=payload).status_code == 201
    assert client.post("/api/users", headers=headers, json=payload).status_code == 409


def test_the_last_administrator_cannot_be_demoted(client: TestClient, admin: User) -> None:
    """Recovering from this needs shell access to a box in a basement."""
    headers = auth_headers(client, "boss")
    response = client.patch(f"/api/users/{admin.id}", headers=headers, json={"role": "security"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "USER_LAST_ADMIN"


def test_the_last_administrator_cannot_be_deactivated(client: TestClient, admin: User) -> None:
    headers = auth_headers(client, "boss")
    response = client.patch(
        f"/api/users/{admin.id}", headers=headers, json={"is_active": False}
    )
    assert response.json()["error"]["code"] == "USER_LAST_ADMIN"


def test_an_admin_can_be_demoted_when_another_one_exists(
    client: TestClient, admin: User
) -> None:
    headers = auth_headers(client, "boss")
    client.post(
        "/api/users",
        headers=headers,
        json={"username": "boss2", "password": "a-long-enough-password", "role": "admin"},
    )

    response = client.patch(f"/api/users/{admin.id}", headers=headers, json={"role": "security"})
    assert response.status_code == 200


def test_deactivating_a_user_ends_their_session_immediately(
    client: TestClient, admin: User, guard: User
) -> None:
    guard_headers = auth_headers(client, "guard")
    assert client.get("/api/auth/me", headers=guard_headers).status_code == 200

    client.patch(
        f"/api/users/{guard.id}", headers=auth_headers(client, "boss"), json={"is_active": False}
    )

    # Not "when the access token happens to expire" - now.
    assert client.get("/api/auth/me", headers=guard_headers).status_code == 401
