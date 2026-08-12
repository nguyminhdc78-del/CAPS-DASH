"""Telling "the camera is not streaming" apart from "the camera is gone".

The reachable case uses a real loopback socket. The failure cases inject the
exception instead, because which one the OS raises is not portable: a connect
to a closed loopback port is refused on the Linux board this runs on, and
times out on Windows. Pinning the test to either would make it a test of the
machine rather than of the mapping this module actually owns.
"""

from __future__ import annotations

import socket

import pytest

from caps_dash.vision.sources import rtsp_endpoint_probe
from caps_dash.vision.sources.rtsp_endpoint_probe import (
    DEFAULT_RTSP_PORT,
    EndpointState,
    probe,
)


@pytest.fixture
def listening_port() -> int:
    """A port with something accepting on it, closed after the test."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        yield server.getsockname()[1]
    finally:
        server.close()


def raise_on_connect(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(rtsp_endpoint_probe.socket, "create_connection", boom)


def test_a_listening_port_is_reachable(listening_port: int) -> None:
    result = probe(f"rtsp://127.0.0.1:{listening_port}/live", 2.0)

    assert result.state is EndpointState.REACHABLE
    assert not result.worth_retrying_soon


def test_a_refused_connection_is_not_reported_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The distinction that matters: the host answered. On an action camera
    that means its stream is switched off - a button to press, not a fault."""
    raise_on_connect(monkeypatch, ConnectionRefusedError(111, "refused"))

    result = probe("rtsp://127.0.0.1:8554/live", 2.0)

    assert result.state is EndpointState.REFUSED
    assert "not streaming" in result.detail
    # Cheap to check and can change at any moment, so the reader comes
    # straight back instead of backing off to half a minute.
    assert result.worth_retrying_soon


def test_a_url_without_a_host_is_rejected_before_any_socket() -> None:
    result = probe("rtsp:///live", 2.0)

    assert result.state is EndpointState.MALFORMED
    assert not result.worth_retrying_soon


def test_an_invalid_port_is_rejected_rather_than_raising() -> None:
    """`urlsplit` defers parsing the port until it is read, so this raises
    from the attribute access rather than from the split."""
    result = probe("rtsp://camera:not-a-port/live", 2.0)

    assert result.state is EndpointState.MALFORMED


def test_the_default_rtsp_port_is_used_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A URL with no port must reach the socket layer at 554, not be rejected
    as malformed before anything is tried."""
    assert DEFAULT_RTSP_PORT == 554
    seen: list[tuple[str, int]] = []

    def record(address: tuple[str, int], **_kwargs: object) -> None:
        seen.append(address)
        raise ConnectionRefusedError(111, "refused")

    monkeypatch.setattr(rtsp_endpoint_probe.socket, "create_connection", record)

    probe("rtsp://camera.invalid/live", 2.0)

    assert seen == [("camera.invalid", DEFAULT_RTSP_PORT)]


def test_a_timeout_is_reported_as_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A camera that is off, asleep, or off the network."""
    raise_on_connect(monkeypatch, TimeoutError("timed out"))

    result = probe("rtsp://192.0.2.1:8554/live", 0.25)

    assert result.state is EndpointState.UNREACHABLE
    # A real outage; hammering it helps nobody.
    assert not result.worth_retrying_soon
