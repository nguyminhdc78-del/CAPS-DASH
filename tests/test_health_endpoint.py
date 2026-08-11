"""Phase 01 foundations: health, correlation ids, and the error envelope."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from caps_dash.config.settings import Settings
from caps_dash.observability.request_context import REQUEST_ID_HEADER


def test_health_returns_ok_and_version(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_env"] == "dev"
    assert body["version"]


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.headers.get(REQUEST_ID_HEADER)


def test_supplied_request_id_is_echoed_back(client: TestClient) -> None:
    """Lets a reverse proxy or the SPA correlate its own id with our logs."""
    response = client.get("/api/health", headers={REQUEST_ID_HEADER: "abc123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc123"


def test_unknown_api_path_returns_envelope_not_spa_shell(client: TestClient) -> None:
    """The regression this guards: a static mount at "/" swallowing /api 404s."""
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]
    assert "html" not in response.headers.get("content-type", "")


def test_readiness_names_the_failing_component(client: TestClient) -> None:
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    body = response.json()
    # Phase 01 has no database wired yet, so readiness is honestly false.
    assert body["ready"] is False
    assert body["components"][0]["name"] == "database"


def test_prod_refuses_placeholder_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(app_env="prod", secret_key="change-me", cors_origins=["https://caps.local"])


def test_prod_refuses_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match=r"CORS_ORIGINS contains"):
        Settings(app_env="prod", secret_key="a-real-secret-value", cors_origins=["*"])


def test_prod_accepts_a_sound_configuration() -> None:
    settings = Settings(
        app_env="prod",
        secret_key="a-real-secret-value",
        cors_origins=["https://caps.local"],
    )
    assert settings.is_prod


def test_cors_origins_accept_comma_separated_string() -> None:
    settings = Settings(cors_origins="http://a.local, http://b.local")  # type: ignore[arg-type]
    assert settings.cors_origins == ["http://a.local", "http://b.local"]
