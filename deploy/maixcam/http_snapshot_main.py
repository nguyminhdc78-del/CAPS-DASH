"""MaixCam HTTP snapshot server: one GET, one JPEG.

A background thread holds the sensor open and keeps the newest encoded frame
in a single `bytes` slot; the HTTP handler serves whatever is in that slot.
Capture rate and poll rate are deliberately unequal - the consumer polls every
2 s and must never wait for a capture to finish.

Deployed to `/maixapp/apps/http_snapshot/main.py`. This file in the repository
is the source of truth; the copy on the camera is a copy. See README.md beside
it for install and rollback.

Requires CPython 3.11 with the standard library, which the probe of 2026-08-12
confirmed is present on the device (3.11.6, `http.server` importable).
"""

from __future__ import annotations

import contextlib
import socket
import sys
import threading
import time
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from maix import camera, display, image

WIDTH, HEIGHT = 640, 480
PORT = 8080
# The consumer polls at 0.5 Hz. Capturing faster than that means a GET is
# always answered from a warm cache with no capture latency in the response -
# which matters more than it sounds. Measured on this device 2026-08-12:
# opening the sensor costs 1034 ms, and the first frame back is unconverged
# (5.4 KB of flat grey, against ~37 KB once AE/AWB settle). Capture-on-request
# would serve exactly that frame, every time.
#
# This value is chosen for FRESHNESS, not for CPU. An earlier comment here
# reasoned that capture + encode measures 25 ms, so each frame per second must
# cost ~2.5% of this single-core board. That arithmetic is wrong, and the
# device says so - measured 2026-08-12:
#
#     CAPTURE_FPS   app CPU
#     2.0           53-55%
#     0.5           53-54%
#
# Four times fewer captures, same CPU. The cost is holding the sensor open at
# all: the MaixPy pipeline runs the ISP at the sensor's own frame rate whether
# or not anyone calls `read()`. So lowering this buys nothing but staler
# frames, and raising it costs nothing but allocation churn.
#
# 2 fps then, simply because a GET is at most 500 ms stale against a 2 s poll -
# well inside the 45-134 ms of WiFi jitter, and undetectable in a car park.
# **If the camera's CPU ever matters, this is not the lever** - the sensor's
# own resolution and frame rate are.
CAPTURE_FPS = 2.0

# Where to listen. This endpoint has no authentication, so this line decides
# who can reach a live camera feed - read the README's security section before
# changing it.
#
# NOT the USB-C gadget IP, which is what this said first. Measured on the
# device 2026-08-12: `usb0` does exist and does hold 10.22.120.1, but it is
# NO-CARRIER/DOWN, because the USB-C cable goes to a charger. The camera
# reaches the backend over `wlan0` on a DHCP address from the hotspot
# (192.168.137.90 on the day). Binding 10.22.120.1 would therefore have
# *succeeded* and served nobody - worse than crashing, because the camera
# looks up and simply answers no one.
#
# 0.0.0.0 because that DHCP address moves. The startup banner prints where it
# actually landed, so the exposure is something someone saw rather than
# something someone assumed. Pin this to one address if the camera is ever on
# a network you do not control.
BIND_HOST = "0.0.0.0"  # noqa: S104 - deliberate, see above

# 5x the 2 s poll interval, so a healthy server never trips it. Past this a
# GET answers 503 rather than serving a frozen picture - see `do_GET`.
MAX_FRAME_AGE_S = 10.0

# The sensor may still be held by the app this one replaces when the launcher
# starts us at boot. Retry rather than die: a capture thread that gives up on
# the first failure leaves a server that answers 503 forever and needs a human.
CAMERA_OPEN_RETRY_S = 2.0
# ...and one every this many attempts is logged, not all of them. A line every
# 2 s is 43k lines a day onto flash, which is what silencing `log_message`
# below exists to avoid.
CAMERA_OPEN_LOG_EVERY = 15

# Pin exposure and gain once the sensor has settled, instead of leaving it
# hunting. Measured on the reference ESP32-CAM and recorded in
# `docs/deployment-guide.md`: with automatic exposure the whole frame shifts
# brightness between shots, noise reaches 7.5 mean absolute difference with
# peaks of 38, and a car covering a sixth of the frame only reads about 13 -
# so the change gate cannot separate them. Locked and settled, noise falls to
# 0.8. The same instability shows up in detection: over one static scene the
# small model found all three cars on 8 of 8 frames in one burst and only 4 of
# 8 in the next.
#
# White balance is deliberately left automatic. Locking it moved measured
# noise by 0.1 against a threshold of 8 - nothing - while tinting every frame
# green, and the detector was trained on normally-coloured images.
LOCK_EXPOSURE = True
# Wait for auto-exposure to CONVERGE, do not just count frames. A fixed count
# was tried first and locked too early: 20 frames left the scene pinned at
# roughly half the brightness the sensor eventually settled on. The sensor
# reports its own exposure, so wait until that number stops moving.
EXPOSURE_STABLE_READS = 4  # consecutive steady reads that count as converged
EXPOSURE_SETTLE_TIMEOUT_S = 15.0  # ...but never wait forever to start serving
EXPOSURE_STABLE_TOLERANCE = 0.03  # 3% - sensor values jitter slightly forever

# Consecutive capture failures before the handle is assumed dead and re-opened.
# Retrying the same handle forever survives a bad frame but not a sensor that
# went away (USB re-enumeration, driver reset), and that needs a power cycle to
# clear otherwise - the process stays up, so even restart-on-crash cannot help.
CAPTURE_FAILS_BEFORE_REOPEN = 10

# Draw the live picture and the serving state onto the device's own screen.
#
# Not decoration. Without it this app draws nothing at all, so the screen keeps
# showing whatever the launcher last painted - and a working camera is then
# indistinguishable, to anyone standing in front of it, from one that hung at
# boot. That was reported twice as "the camera is stuck on the waiting screen"
# when it was in fact serving frames the whole time.
#
# Every Nth captured frame, so the draw rate is tunable apart from the capture
# rate. Drawing is best-effort: a board with no screen must not lose its
# capture thread over it.
DISPLAY_EVERY_N_FRAMES = 1

# Where diagnostics go. `print` alone is not enough: the MaixPy launcher
# discards an autostarted app's stdout, so the encode path it chose, the
# exposure it locked and any capture failure were all invisible on exactly the
# runs that matter - the unattended ones.
#
# Truncated at startup rather than rotated. This app writes a handful of lines
# per boot and throttles the repeating ones, so the file cannot grow without
# something already being wrong, and flash endurance is a stated constraint.
LOG_PATH = "/tmp/http_snapshot.log"  # noqa: S108 - a fixed path on a single-user embedded box, by design

JPEG_MAGIC = b"\xff\xd8\xff"

_latest: bytes | None = None
_latest_at = 0.0
_lock = threading.Lock()
# Requests answered 200. Shown on screen because it is the one number that
# proves the *backend* is actually polling, not just that this app is alive.
_served = 0
# Filled once in `main()`; the on-screen line would otherwise re-resolve the
# hostname twice a second to print something that never changes.
_ADDRESSES: list[str] = []
# Why the capture thread stopped, if it did. Served in the 503 body: the
# thread is a daemon, so its death does not stop `serve_forever`, and without
# this every failure looks identical on the wire to a server in its first
# second. Diagnosing it would otherwise mean a second trip to the hardware.
_fatal: str | None = None


def say(message: str) -> None:
    """Print, and also leave it somewhere an SSH session can find it."""
    print(message)
    try:
        with open(LOG_PATH, "a") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")
    except OSError:
        pass  # a read-only /tmp must not stop the camera serving


def _encode_candidates(img: Any) -> Sequence[tuple[str, Callable[[], Any]]]:
    """The encode paths worth trying, best first.

    `to_jpeg().to_bytes()` is what the API reads like it should do, but it was
    never confirmed on a real frame that it returns JPEG bytes rather than raw
    pixels - the probe could not open the sensor. Rather than assume, try each
    path once at startup and keep the first that produces something starting
    with the JPEG magic. Each is a callable so a path this firmware does not
    have raises where it is caught, not at import.
    """
    return (
        ("to_jpeg", lambda: img.to_jpeg().to_bytes()),
        ("compress", lambda: img.compress(85).to_bytes()),
        ("to_bytes", lambda: img.to_bytes()),
    )


def choose_encoder(img: Any) -> str | None:
    """Pick the encode path on evidence, once, and say which one won.

    Returns the winning path's name, or None if no route on this firmware
    produces JPEG bytes - which `capture_loop` turns into a 503 that says so,
    since a daemon thread cannot fail loudly enough to be noticed otherwise.
    """
    for name, encode in _encode_candidates(img):
        try:
            data = encode()
            # Inside the try on purpose: `data` may be any object this
            # firmware chose to return, and describing it must not be what
            # kills the capture thread before the server ever starts.
            ok = isinstance(data, (bytes, bytearray)) and bytes(data[:3]) == JPEG_MAGIC
            described = f"{type(data).__name__}, {len(data)} bytes"
        except Exception as exc:
            say(f"encode path {name} unavailable: {exc}")
            continue
        if ok:
            say(f"encode path: {name} ({described} at {WIDTH}x{HEIGHT})")
            return name
        say(f"encode path {name} rejected: {described}")
    return None


def encode_with(img: Any, name: str) -> Any:
    for candidate, encode in _encode_candidates(img):
        if candidate == name:
            return encode()
    raise RuntimeError(f"unknown encode path: {name}")


def open_camera() -> Any:
    """Block until the sensor is ours."""
    attempt = 0
    while True:
        try:
            return camera.Camera(WIDTH, HEIGHT)
        except Exception as exc:
            if attempt % CAMERA_OPEN_LOG_EVERY == 0:
                say(f"camera open failed, still retrying: {exc}")
            attempt += 1
            time.sleep(CAMERA_OPEN_RETRY_S)


def open_display() -> Any:
    """The device's screen, or None if it has not got one.

    Best effort by design: a camera with no display, or a firmware that will
    not give one up, must keep serving frames rather than lose its capture
    thread to a cosmetic feature.
    """
    try:
        return display.Display()
    except Exception as exc:
        say(f"no display, running headless: {exc}")
        return None


def show_status(screen: Any, frame: Any, captured: int) -> None:
    """Paint the live picture plus enough state to judge it from across a room.

    The request count is the useful number: it distinguishes "this app is
    alive" from "the backend is actually polling it", which is the question
    someone standing at the camera usually has.
    """
    try:
        frame.draw_string(4, 4, f"HTTP snapshot :{PORT}", image.COLOR_WHITE, 1.2)
        # Resolved once at startup, not per frame: this is a hostname lookup,
        # and it would run twice a second here for a line that never changes.
        for index, address in enumerate(_ADDRESSES[:3]):
            frame.draw_string(4, 26 + index * 18, address, image.COLOR_GREEN, 1.0)
        frame.draw_string(
            4, frame.height() - 22, f"frames {captured}  served {_served}", image.COLOR_WHITE, 1.0
        )
        screen.show(frame)
    except Exception as exc:
        say(f"display failed: {exc}")


def lock_exposure(cam: Any) -> None:
    """Freeze exposure and gain at whatever auto-exposure converged on.

    Not a fixed pair of numbers: the right exposure depends on where the
    camera is pointed and how the room is lit, and only the sensor knows that.
    So let it decide, then stop it changing its mind.

    Best effort. A firmware without these controls, or one that rejects manual
    mode, must keep serving frames - a hunting sensor is worse than a locked
    one, but far better than no camera at all.
    """
    if not LOCK_EXPOSURE:
        return
    try:
        exposure_us, steady, deadline = 0, 0, time.monotonic() + EXPOSURE_SETTLE_TIMEOUT_S
        while time.monotonic() < deadline and steady < EXPOSURE_STABLE_READS:
            cam.read()  # auto-exposure only advances on frames actually taken
            time.sleep(0.1)
            current = cam.exposure(-1)
            drift = abs(current - exposure_us) / max(current, 1)
            steady = steady + 1 if drift <= EXPOSURE_STABLE_TOLERANCE else 0
            exposure_us = current

        gain = cam.gain(-1)
        cam.exp_mode(1)  # 1 = manual
        cam.exposure(exposure_us)
        cam.gain(gain)
        settled = "converged" if steady >= EXPOSURE_STABLE_READS else "TIMED OUT, may be dark"
        say(f"exposure locked ({settled}): {exposure_us} us, gain {gain}")
    except Exception as exc:
        say(f"exposure lock failed, leaving it automatic: {exc}")


def capture_loop() -> None:
    """Run the capture forever, and leave a reason behind if it cannot.

    This thread is a daemon: an exception here ends the thread and prints to
    stderr, but `serve_forever()` carries on in the main thread. Recording why
    is the difference between a 503 that names the fault and a 503 that looks
    exactly like a server which has simply not captured its first frame yet.
    """
    global _fatal
    try:
        _capture_forever()
    except Exception as exc:
        _fatal = f"capture thread stopped: {type(exc).__name__}: {exc}"
        raise


def _capture_forever() -> None:
    global _latest, _latest_at, _fatal

    cam = open_camera()  # opened once, held open across frames
    lock_exposure(cam)
    encoder = choose_encoder(cam.read())
    if encoder is None:
        _fatal = "no encode path on this firmware yields JPEG bytes"
        return

    screen = open_display()
    interval = 1.0 / CAPTURE_FPS
    failures = 0
    captured = 0
    while True:
        try:
            frame = cam.read()
            # `bytes(...)` rather than the raw return: an immutable copy is
            # what lets a handler read the frame after releasing the lock. If
            # the firmware hands back a buffer it reuses, sharing it would let
            # the next capture rewrite a response mid-send.
            #
            # Encoded BEFORE anything is drawn on `frame`, so the JPEG the
            # backend receives never carries the on-screen overlay.
            jpg = bytes(encode_with(frame, encoder))
            with _lock:
                _latest = jpg
                _latest_at = time.monotonic()
            failures = 0
            captured += 1
            if screen is not None and captured % DISPLAY_EVERY_N_FRAMES == 0:
                show_status(screen, frame, captured)
        except Exception as exc:
            # One bad frame must not end the thread and silently freeze the
            # feed at the last good picture forever. The staleness guard turns
            # a persistent failure into a 503 the backend can act on.
            failures += 1
            say(f"capture failed ({failures}): {exc}")
            if failures >= CAPTURE_FAILS_BEFORE_REOPEN:
                say("re-opening the camera")
                cam = open_camera()
                # A fresh handle comes back on automatic; re-lock it, or the
                # scene silently starts hunting again after a recovery.
                lock_exposure(cam)
                failures = 0
            time.sleep(0.5)
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    # Load-bearing: the stdlib default is HTTP/1.0, which closes the
    # connection after every response and would cost the client a TCP
    # handshake on every poll. (`send_error` still closes, so the 503 and 404
    # paths pay one - they are meant to be rare.)
    protocol_version = "HTTP/1.1"
    # And keep-alive needs a bound. Without it a connection that dies without
    # a FIN - which a USB gadget link can do - parks a server thread in
    # `readline()` forever, one per glitch, on a board with finite RAM.
    timeout = 30

    # `do_GET` is the name BaseHTTPRequestHandler dispatches to; not ours to pick.
    def do_GET(self) -> None:
        if self.path != "/snapshot":
            self.send_error(404)
            return

        with _lock:
            body = _latest
            age = time.monotonic() - _latest_at

        if body is None:
            self.send_error(503, _fatal or "no frame captured yet")
            return
        if age > MAX_FRAME_AGE_S:
            # The capture thread has stopped producing. Answering 200 with
            # this frame would be a lie the backend cannot detect: it would go
            # on reporting the camera healthy off a frozen picture.
            stale = f"stale frame: {age:.1f}s old"
            self.send_error(503, f"{stale} ({_fatal})" if _fatal else stale)
            return

        global _served
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
            _served += 1  # after the write, so it counts frames delivered
        except OSError:
            # The client hung up mid-transfer. Its problem, not ours, and not
            # worth a stack trace on a board with finite flash.
            self.close_connection = True

    def log_message(self, format: str, *args: Any) -> None:
        # The default writes one stderr line per request; at 0.5 Hz that is
        # tens of thousands of lines a day onto flash. No.
        pass


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """Same server, minus a stack trace every time a client vanishes.

    `socketserver` prints a full traceback for any exception escaping a
    handler thread, and a keep-alive connection that dies while the handler
    waits in `readline()` raises `ConnectionResetError` there - which is not
    an error, it is the backend restarting or the USB link blinking. Observed
    for real: one restart of the consumer produced two tracebacks, ~15 lines
    each, onto a board whose flash endurance is a stated constraint. That is
    the same cost that silenced `log_message`.

    Anything that is not a dead connection still gets its traceback, because
    that one is worth reading.
    """

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def reachable_addresses() -> list[str]:
    """Every IPv4 address this camera can be reached on, best effort.

    Printed at startup because `BIND_HOST` is `0.0.0.0`: the operator needs to
    know which networks an unauthenticated camera feed just appeared on, and
    on the device that answer changes with the cable.
    """
    addresses = set()

    # Ask the routing table which source address would reach the outside
    # world. No packet is sent - `connect` on UDP only fixes the local end -
    # and this is the address that actually matters, the one the backend will
    # be talking to.
    #
    # `gethostname()` was tried first and was useless here: this box resolves
    # its own name to 127.0.1.1, so the startup banner and the on-screen
    # status both advertised the loopback alias instead of the WiFi address
    # an operator needs.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, guaranteed unroutable
        addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass

    # Loopback last: real, but never the answer to "where do I point the
    # backend".
    return sorted(addresses, key=lambda a: (a.startswith("127."), a))


def main() -> None:
    global _ADDRESSES
    with contextlib.suppress(OSError):
        open(LOG_PATH, "w").close()  # a fresh log per boot

    _ADDRESSES = reachable_addresses()

    threading.Thread(target=capture_loop, daemon=True).start()
    say(f"listening on {BIND_HOST}:{PORT} - NO AUTHENTICATION")
    for address in _ADDRESSES or ["<could not resolve local addresses>"]:
        say(f"  reachable at http://{address}:{PORT}/snapshot")
    QuietThreadingHTTPServer((BIND_HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
