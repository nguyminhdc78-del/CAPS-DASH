"""Asking an RTSP camera what it is actually offering, when a capture fails.

`cv2.VideoCapture` reports one failure for every cause. The one measured on
the reference camera is worth naming precisely, because it looks like a
network fault and is not:

    RTSP/1.0 200 OK
    Content-Type: application/sdp
    Content-Length: 1

    \\n

The camera answers DESCRIBE, claims to be sending a session description, and
sends an empty one. FFMPEG then has no media track to SETUP, so its PLAY
carries no session and the server answers `454 Session Not Found` - which
reads like a session-management problem and sends whoever is debugging it
looking in the wrong place entirely. A hand-rolled handshake that GUESSES the
track name (`.../live/track1`) completes all four steps against the same
camera in the same second, which is what proves the fault is the empty
description rather than the camera or the link.

The cause is on the camera. Confirmed on the reference unit, which showed
its own dialogs while this was happening:

    APP rtsp_stream Error - app exit with code: 1
    Runtime need upgrade - Please upgrade runtime in 'Settings'

Its RTSP frontend keeps answering after the streaming app behind it has
exited, so the port is open, DESCRIBE succeeds, and there is nothing to
describe. Nothing on this side can fix that, which is exactly why the message
has to point at the camera instead of at the network.

One DESCRIBE, run only when a capture has already failed - never on the
healthy path.
"""

from __future__ import annotations

import re
import socket
from urllib.parse import urlsplit

from .rtsp_endpoint_probe import DEFAULT_RTSP_PORT, endpoint_label

# An SDP that describes anything at all has at least one media line.
_MEDIA_LINE = re.compile(rb"^m=", re.MULTILINE)
_STATUS = re.compile(r"^RTSP/\d\.\d (\d+)")
_CONTENT_LENGTH = re.compile(rb"Content-Length:\s*(\d+)", re.IGNORECASE)


def describe_failure(source_url: str, timeout_s: float) -> str:
    """Why a capture on `source_url` would not open, in one sentence."""
    where = endpoint_label(source_url)
    try:
        head, body = _describe(source_url, timeout_s)
    except OSError as exc:
        return f"camera at {where} stopped answering RTSP: {exc}"

    if not head:
        return f"camera at {where} accepted the connection but sent no RTSP reply"

    status_line = head.splitlines()[0] if head.splitlines() else ""
    status = _STATUS.match(status_line)
    code = status.group(1) if status else ""

    if code == "401":
        return f"camera at {where} needs credentials in its source_url"
    if code and code != "200":
        return f"camera at {where} refused to describe its stream: {status_line}"

    if not _MEDIA_LINE.search(body):
        return (
            f"camera at {where} is not producing video - it answers RTSP but its "
            "stream description is empty, which means its streaming app is not "
            "running. Check the camera's own screen for an error."
        )
    return f"camera at {where} describes a stream but the decoder could not open it"


def _describe(source_url: str, timeout_s: float) -> tuple[str, bytes]:
    parts = urlsplit(source_url)
    host = parts.hostname
    if not host:
        raise OSError("source_url has no host")
    try:
        port = parts.port or DEFAULT_RTSP_PORT
    except ValueError as exc:
        raise OSError("source_url has an invalid port") from exc

    # Rebuilt without the userinfo: it goes on the wire in the request line,
    # and this module's output lands in `cameras.last_error`.
    request = (
        f"DESCRIBE rtsp://{host}:{port}{parts.path or '/'} RTSP/1.0\r\n"
        "CSeq: 1\r\nUser-Agent: caps-dash\r\nAccept: application/sdp\r\n\r\n"
    )

    with socket.create_connection((host, port), timeout=timeout_s) as sock:
        sock.sendall(request.encode())
        sock.settimeout(timeout_s)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")

        declared = _CONTENT_LENGTH.search(head)
        if declared:
            wanted = int(declared.group(1))
            while len(body) < wanted:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                body += chunk
        return head.decode("utf-8", "replace"), body
