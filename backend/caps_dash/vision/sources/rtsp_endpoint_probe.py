"""Finding out WHY an RTSP camera cannot be reached, cheaply.

`cv2.VideoCapture` reports one failure for every cause: it returns a capture
that is not opened. The distinction it throws away is the one an operator
needs, because the two causes have different fixes:

  * connection refused - the host is there and said no. On an action camera
    that means its RTSP server is not running, which is a button on the
    camera, not a fault in this system. Measured: 6-60 ms to find out.
  * timeout / no route - the camera is off, asleep, or off the network.

A plain TCP connect answers that in milliseconds, where letting FFMPEG try
costs the full connect timeout. It is also what lets the reader retry quickly
while a camera is merely idle, instead of backing off as if something were
broken.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

DEFAULT_RTSP_PORT = 554


class EndpointState(StrEnum):
    REACHABLE = "reachable"
    """The port accepted a connection. Whether RTSP works is another matter."""
    REFUSED = "refused"
    """Host answered, nothing is listening. The camera is not streaming."""
    UNREACHABLE = "unreachable"
    """No answer at all - powered off, asleep, or off the network."""
    MALFORMED = "malformed"
    """The configured URL has no host to connect to."""


@dataclass(frozen=True, slots=True)
class ProbeResult:
    state: EndpointState
    detail: str

    @property
    def worth_retrying_soon(self) -> bool:
        """Whether to come straight back rather than back off.

        A refused port is a camera waiting to be switched on: the check costs
        milliseconds and the answer can change at any moment, so backing off
        to half a minute would mean staring at a blank tile long after the
        operator pressed the button. An unreachable one is a real outage and
        polling it hard helps nobody.
        """
        return self.state is EndpointState.REFUSED


def endpoint_label(source_url: str) -> str:
    """`host:port` for an error message, or the raw URL if it cannot be read.

    Never includes the userinfo section, so a URL carrying credentials cannot
    leak into `cameras.last_error` - which the security role can read while
    `source_url` itself is admin-only.
    """
    parts = urlsplit(source_url)
    try:
        port = parts.port or DEFAULT_RTSP_PORT
    except ValueError:
        port = DEFAULT_RTSP_PORT
    return f"{parts.hostname}:{port}" if parts.hostname else "the camera"


def probe(source_url: str, timeout_s: float) -> ProbeResult:
    """TCP-connect to the URL's host and port. Never raises."""
    parts = urlsplit(source_url)
    host = parts.hostname
    if not host:
        return ProbeResult(EndpointState.MALFORMED, "source_url has no host")

    try:
        port = parts.port or DEFAULT_RTSP_PORT
    except ValueError:
        # `urlsplit` defers parsing the port until it is asked for, and raises
        # here rather than at split time for something like `rtsp://cam:abc/`.
        return ProbeResult(EndpointState.MALFORMED, "source_url has an invalid port")

    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return ProbeResult(EndpointState.REACHABLE, "")
    except ConnectionRefusedError:
        return ProbeResult(
            EndpointState.REFUSED,
            f"camera at {host}:{port} refused the connection - "
            "it is on the network but not streaming",
        )
    except (TimeoutError, OSError) as exc:
        return ProbeResult(
            EndpointState.UNREACHABLE, f"cannot reach {host}:{port}: {exc}"
        )
