"""Naming the reason a capture would not open.

Driven by a fake RTSP server on loopback, because the thing under test is how
a real response is parsed - a mock would only assert that the code matches
whatever the test author imagined the camera sends.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest

from caps_dash.vision.sources.rtsp_media_check import describe_failure

GOOD_SDP = b"v=0\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H265/90000\r\n"
# What the reference camera actually sends: a body of one newline.
EMPTY_SDP = b"\n"


def serve_once(reply: bytes) -> Iterator[int]:
    """A socket that answers one request with `reply`, then closes."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def handle() -> None:
        try:
            conn, _ = server.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(reply)
        except OSError:
            pass
        finally:
            server.close()

    thread = threading.Thread(target=handle, daemon=True)
    thread.start()
    yield port
    thread.join(timeout=2.0)


def rtsp_reply(status: str, body: bytes) -> bytes:
    return (
        f"RTSP/1.0 {status}\r\nCSeq: 1\r\n"
        f"Content-Type: application/sdp\r\nContent-Length: {len(body)}\r\n\r\n"
    ).encode() + body


@pytest.fixture
def empty_sdp_server() -> Iterator[int]:
    yield from serve_once(rtsp_reply("200 OK", EMPTY_SDP))


@pytest.fixture
def good_sdp_server() -> Iterator[int]:
    yield from serve_once(rtsp_reply("200 OK", GOOD_SDP))


@pytest.fixture
def unauthorised_server() -> Iterator[int]:
    yield from serve_once(rtsp_reply("401 Unauthorized", b""))


def test_an_empty_description_is_named_as_such(empty_sdp_server: int) -> None:
    """The measured failure. The camera answers 200 OK with a one-byte body,
    FFMPEG finds no track to set up, and its PLAY comes back `454 Session Not
    Found` - which reads like a session bug and is not one."""
    message = describe_failure(f"rtsp://127.0.0.1:{empty_sdp_server}/live", 3.0)

    assert "not producing video" in message
    assert "Start the live preview on the camera" in message
    assert f"127.0.0.1:{empty_sdp_server}" in message


def test_a_camera_wanting_credentials_says_so(unauthorised_server: int) -> None:
    message = describe_failure(f"rtsp://127.0.0.1:{unauthorised_server}/live", 3.0)

    assert "needs credentials" in message


def test_a_healthy_description_blames_the_decoder_not_the_camera(
    good_sdp_server: int,
) -> None:
    """If the camera describes real media, the fault is downstream of it, and
    saying "start the preview" would send the operator to the wrong device."""
    message = describe_failure(f"rtsp://127.0.0.1:{good_sdp_server}/live", 3.0)

    assert "describes a stream" in message
    assert "not producing video" not in message


def test_a_camera_that_has_gone_away_is_not_reported_as_empty() -> None:
    """192.0.2.0/24 routes nowhere by RFC 5737, so this cannot reach a real
    host on any network the tests run on."""
    message = describe_failure("rtsp://192.0.2.1:8554/live", 0.25)

    assert "stopped answering RTSP" in message
    assert "not producing video" not in message


def test_credentials_never_reach_the_message() -> None:
    """`cameras.last_error` is readable by the security role while
    `source_url` is admin-only."""
    message = describe_failure("rtsp://admin:hunter2@192.0.2.1:8554/live", 0.25)

    assert "hunter2" not in message
    assert "192.0.2.1:8554" in message
