"""A camera password must not escape through any field, including error text.

The leak this guards against was real and subtle: `source_url` was carefully
redacted, but an httpx failure stringifies the request URL, so the same
password reappeared verbatim inside `cameras.last_error` - a field every
security-role user can read, while `source_url` itself is admin-only.
"""

from __future__ import annotations

import httpx
import pytest

from caps_dash.api.schemas.camera_schemas import CameraResponse, ConnectionTestResponse
from caps_dash.observability.credential_redaction import redact_credentials, sanitize_source_url

SECRET = "s3cret"
URL_WITH_CREDENTIALS = f"http://admin:{SECRET}@10.0.0.7/anh"


def test_userinfo_is_stripped_from_a_url():
    assert sanitize_source_url(URL_WITH_CREDENTIALS) == "http://10.0.0.7/anh"


def test_a_port_survives_stripping():
    assert sanitize_source_url(f"http://admin:{SECRET}@10.0.0.7:8080/anh") == (
        "http://10.0.0.7:8080/anh"
    )


def test_a_filesystem_path_containing_an_at_sign_is_left_alone():
    """Not every '@' is userinfo; mangling a valid path would break the source."""
    path = "/media/recordings/cam@ramp/clip.mp4"
    assert sanitize_source_url(path) == path


def test_credentials_inside_a_sentence_are_redacted():
    message = f"Client error '404 Not Found' for url '{URL_WITH_CREDENTIALS}'"
    redacted = redact_credentials(message)

    assert SECRET not in redacted
    assert "404 Not Found" in redacted  # still diagnosable
    assert "10.0.0.7" in redacted


def test_an_httpx_error_message_is_redacted():
    """Verified against the real exception text, not an assumed format."""
    request = httpx.Request("GET", URL_WITH_CREDENTIALS)
    response = httpx.Response(404, request=request)
    error = httpx.HTTPStatusError("404", request=request, response=response)

    assert SECRET not in redact_credentials(f"{type(error).__name__}: {error}")


@pytest.mark.parametrize("field", ["last_error", "source_url"])
def test_camera_response_never_carries_a_password(field: str):
    response = CameraResponse(
        id=1,
        code="C1",
        name="Ramp",
        floor="B1",
        source_type="esp32cam_http",
        source_url=URL_WITH_CREDENTIALS,
        poll_interval_s=3.0,
        vote_window=5,
        vote_threshold=4,
        confidence=0.25,
        is_enabled=True,
        frame_width=640,
        frame_height=480,
        last_seen_at=None,
        last_error=f"HTTPStatusError: 404 for url '{URL_WITH_CREDENTIALS}'",
    )

    assert SECRET not in getattr(response, field)


def test_connection_test_result_never_carries_a_password():
    """The probe URL comes straight from the caller, credentials and all."""
    result = ConnectionTestResponse(
        ok=False,
        latency_ms=12.0,
        error=f"ConnectError: failed to reach {URL_WITH_CREDENTIALS}",
        error_code="CAMERA_UNREACHABLE",
    )

    assert SECRET not in result.error
