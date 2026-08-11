"""The handshake: nothing is sent to a connection that has not proved itself."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession

from caps_dash.db.enums import UserRole
from caps_dash.db.models import Camera
from caps_dash.realtime import close_codes
from caps_dash.realtime.frame_protocol import decode_frame_message, encode_frame_message

from .conftest import access_token, make_user


@contextlib.contextmanager
def connect(
    client: TestClient, camera_id: int, token: str | None
) -> Iterator[WebSocketTestSession]:
    """Open a stream and send the auth message, if there is one to send."""
    with client.websocket_connect(f"/ws/cameras/{camera_id}") as websocket:
        if token is not None:
            websocket.send_json({"type": "auth", "token": token})
        yield websocket


def expect_close(websocket: WebSocketTestSession) -> tuple[int, str]:
    """Read the close frame the server sent.

    `receive()` rather than `receive_json()`: the raw method hands back the
    close message itself, which is exactly what these tests are about. The
    typed helpers would raise instead, hiding the code and the reason.
    """
    message = websocket.receive()
    assert message["type"] == "websocket.close"
    return message["code"], message.get("reason", "")


def test_security_user_authenticates_and_gets_an_immediate_first_frame(
    client: TestClient, db: Session, camera: Camera
):
    make_user(db, "guard", UserRole.SECURITY)
    # A frame published before anyone connects: the cache is what makes the
    # first paint immediate instead of one poll interval away.
    message = encode_frame_message({"camera_id": camera.id, "seq": 1}, b"\xff\xd8jpeg")
    client.app.state.caps.hub.publish(camera.id, message)

    with connect(client, camera.id, access_token(client, "guard")) as websocket:
        assert websocket.receive_json() == {
            "type": "auth_ok",
            "camera_id": camera.id,
            "role": "security",
        }
        decoded = decode_frame_message(websocket.receive_bytes())
        assert decoded.header["seq"] == 1
        assert decoded.jpeg == b"\xff\xd8jpeg"


def test_resident_is_closed_before_any_bytes_are_sent(
    client: TestClient, db: Session, camera: Camera
):
    """Residents never receive imagery. Enforced here, not in the client UI."""
    make_user(db, "tenant", UserRole.RESIDENT)

    with connect(client, camera.id, access_token(client, "tenant")) as websocket:
        code, reason = expect_close(websocket)

    assert code == close_codes.POLICY_VIOLATION
    assert reason == close_codes.REASON_FORBIDDEN


def test_silence_past_the_deadline_closes_the_connection(
    client: TestClient, db: Session, camera: Camera
):
    """A client that connects and says nothing holds a slot, so it goes."""
    make_user(db, "guard", UserRole.SECURITY)

    with connect(client, camera.id, token=None) as websocket:
        code, reason = expect_close(websocket)

    assert code == close_codes.POLICY_VIOLATION
    assert reason == close_codes.REASON_AUTH_TIMEOUT


def test_garbage_instead_of_a_token_is_refused(
    client: TestClient, db: Session, camera: Camera
):
    make_user(db, "guard", UserRole.SECURITY)

    with client.websocket_connect(f"/ws/cameras/{camera.id}") as websocket:
        websocket.send_text("not json at all")
        code, reason = expect_close(websocket)

    assert code == close_codes.POLICY_VIOLATION
    assert reason == close_codes.REASON_AUTH_INVALID


def test_unknown_camera_is_refused_after_authentication(
    client: TestClient, db: Session, camera: Camera
):
    make_user(db, "guard", UserRole.SECURITY)

    with connect(client, 9999, access_token(client, "guard")) as websocket:
        code, reason = expect_close(websocket)

    assert code == close_codes.POLICY_VIOLATION
    assert reason == close_codes.REASON_CAMERA_UNKNOWN


def test_viewer_cap_refuses_the_extra_connection(
    client: TestClient, db: Session, camera: Camera
):
    """Refusing one viewer is a better outcome than degrading everyone's stream."""
    make_user(db, "guard", UserRole.SECURITY)
    token = access_token(client, "guard")
    cap = client.app.state.caps.settings.ws_max_viewers_per_camera

    with contextlib.ExitStack() as stack:
        for _ in range(cap):
            websocket = stack.enter_context(connect(client, camera.id, token))
            websocket.receive_json()  # auth_ok

        with connect(client, camera.id, token) as extra:
            code, reason = expect_close(extra)

    assert code == close_codes.TRY_AGAIN_LATER
    assert reason == close_codes.REASON_TOO_MANY_VIEWERS


def test_client_ping_is_answered_with_pong(client: TestClient, db: Session, camera: Camera):
    make_user(db, "guard", UserRole.SECURITY)

    with connect(client, camera.id, access_token(client, "guard")) as websocket:
        websocket.receive_json()  # auth_ok
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}


def test_set_confidence_over_the_socket_is_refused(
    client: TestClient, db: Session, camera: Camera
):
    """Tuning goes through the audited REST endpoint, never over the stream."""
    make_user(db, "guard", UserRole.SECURITY)
    before = camera.confidence

    with connect(client, camera.id, access_token(client, "guard")) as websocket:
        websocket.receive_json()  # auth_ok
        websocket.send_json({"type": "set_confidence", "value": 0.9})
        websocket.send_json({"type": "ping"})
        # Still answering, and the setting is untouched.
        assert websocket.receive_json() == {"type": "pong"}

    db.refresh(camera)
    assert camera.confidence == before
