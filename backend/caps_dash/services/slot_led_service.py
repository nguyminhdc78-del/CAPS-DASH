"""Driving a camera node's WS2812B status ring from the states it decided.

The lamp lives on the ESP32-CAM but the answer does not: YOLO and the vote
filter run here, so the state has to be pushed to the device. `GET /ring` on
the firmware takes one character per bay, in sorted bay-code order - see
`firmware/esp32cam/slot-ring-led.h`.

Three rules make this safe to run inside a camera loop:

**Best effort, always.** A ring that will not answer is a lamp problem, never
a detection problem. Nothing in here raises; the worst outcome is a debug line
and a bay lit the wrong colour until the next push.

**Only on a change, plus a slow refresh.** Pushing every tick would put an HTTP
round trip on the detector's path for an answer that changes a few times an
hour. The refresh exists so a module that rebooted - and came up showing
"no data" amber - repairs itself without waiting for a car to move.

**It disables itself against a device that has no ring.** Not every camera row
points at an ESP32 running this firmware; the reference rig is a MaixCam. One
404 is a complete answer to "does this device have a ring?", so the pusher
stops asking rather than logging a failure every fifteen seconds forever. A
context rebuild - a restart, or any config change - tries again.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from ..errors.codes import ErrorCode
from ..errors.exceptions import UpstreamError, ValidationFailedError
from ..observability.credential_redaction import redact_credentials
from ..observability.logging_setup import get_logger
from ..vision.domain import SlotState
from .camera_control_service import CONTROLLABLE_SOURCES, device_base

logger = get_logger(__name__)

# The wire alphabet, mirrored by `ringApply` in the firmware. UNKNOWN gets its
# own character rather than being folded into FREE: the ring breathes amber for
# it, and reporting an unresolved bay as free is the one thing this system is
# not allowed to do - it sends a driver to a space nobody has looked at.
STATE_CHARS: dict[SlotState, str] = {
    SlotState.OCCUPIED: "1",
    SlotState.FREE: "0",
    SlotState.UNKNOWN: "u",
}

# Re-send an unchanged state this often, so a rebooted ring recovers on its own.
# Comfortably under the firmware's 90 s staleness window - it takes three
# missed pushes in a row before the ring gives up and shows amber.
REFRESH_S = 15.0

# Short on purpose, and shorter than `camera_timeout_s`. This runs on the
# detector's task; a wedged lamp must not hold up the next inference for five
# seconds. The device is on the same LAN and answers in single-digit ms.
PUSH_TIMEOUT_S = 2.0

# Mirrors MAX_SLOTS in the firmware. Beyond this each bay is one LED wide and
# the ring means nothing, so the device rejects the push - detect that here
# rather than retrying into a 400 forever.
MAX_SLOTS = 8


async def push_test_pattern(
    *, source_type: str, source_url: str, code: str, slots: str
) -> None:
    """Light one pattern on the ring now, for commissioning.

    The mirror image of `SlotLedRing.push`, and deliberately so: **this one
    raises.** That pusher runs unattended inside a camera loop, where a lamp
    that will not answer must never become a detection problem. Here somebody
    is standing in front of the ring waiting to see it change, and silence
    would tell them nothing about whether the wiring, the pin or the address
    is at fault.

    Nothing is remembered and nothing is locked. The camera loop overwrites
    this within `REFRESH_S` at the latest, which is the whole design: a test
    pattern that outlived the test would be a lamp showing a car that is not
    there. Tell the operator it reverts rather than building a lock to hold it.
    """
    if not slots or len(slots) > MAX_SLOTS:
        raise ValidationFailedError(f"slots must be 1 to {MAX_SLOTS} characters")
    if any(char not in "01u" for char in slots):
        raise ValidationFailedError("slots may only contain 0 (free), 1 (occupied) or u")

    # Raises CAMERA_SOURCE_INVALID for a folder, a video file or an RTSP
    # camera - none of which is a node that could carry a ring.
    base = device_base(source_type, source_url, code)

    try:
        async with httpx.AsyncClient(timeout=PUSH_TIMEOUT_S) as client:
            response = await client.get(f"{base}/ring", params={"slots": slots})
    except httpx.HTTPError as exc:
        raise UpstreamError(
            redact_credentials(f"Camera did not answer: {exc}"),
            code=ErrorCode.CAMERA_UNREACHABLE,
        ) from exc

    if response.status_code == 404:
        # The device is alive and answering - it simply is not running
        # firmware with a ring. Separating that from "unreachable" is the
        # difference between checking the wiring and checking the firmware.
        raise UpstreamError(
            f"Camera {code} answered, but has no LED ring endpoint. "
            "Flash the firmware in firmware/esp32cam/.",
            code=ErrorCode.CAMERA_SOURCE_INVALID,
        )
    if response.status_code != 200:
        raise UpstreamError(
            f"Camera {code} refused the pattern (HTTP {response.status_code})",
            code=ErrorCode.CAMERA_UNREACHABLE,
        )


def encode_states(states: Mapping[str, SlotState]) -> str:
    """One character per bay, ordered by bay code.

    Sorted, not insertion-ordered: the arcs on the ring are physical positions,
    and a bay that moved because a dict happened to be built differently would
    silently relabel the lamp.
    """
    return "".join(STATE_CHARS.get(states[code], "u") for code in sorted(states))


@dataclass(slots=True)
class SlotLedRing:
    """One camera's ring, and what has already been sent to it.

    Held on `CameraContext`, so a reload resets it - which is what makes the
    "no ring on this device" verdict retryable, and what forces a fresh push
    after a slot map is redrawn and the arcs mean something new.
    """

    supported: bool = True
    last_payload: str = ""
    last_sent_at: float = 0.0

    async def push(
        self,
        *,
        source_type: str,
        source_url: str,
        code: str,
        states: Mapping[str, SlotState],
    ) -> None:
        """Send the current states to the device's ring. Never raises."""
        if not self.supported or not states:
            return

        payload = encode_states(states)
        now = time.monotonic()
        if payload == self.last_payload and now - self.last_sent_at < REFRESH_S:
            return

        log = logger.bind(camera_code=code)

        if source_type not in CONTROLLABLE_SOURCES:
            # A folder, a video file or an RTSP camera has no ring to drive.
            self.supported = False
            return
        if len(payload) > MAX_SLOTS:
            self.supported = False
            log.warning("slot_led_too_many_slots", slots=len(payload), max=MAX_SLOTS)
            return

        try:
            base = device_base(source_type, source_url, code)
        except ValidationFailedError:
            self.supported = False
            return

        try:
            async with httpx.AsyncClient(timeout=PUSH_TIMEOUT_S) as client:
                response = await client.get(f"{base}/ring", params={"slots": payload})
        except httpx.HTTPError as exc:
            # Debug, not warning: the camera's own fail streak already reports
            # an unreachable device, and repeating it here would double every
            # offline camera's log volume for no new information.
            log.debug("slot_led_push_failed", error=redact_credentials(str(exc)))
            return

        if response.status_code == 404:
            self.supported = False
            log.info("slot_led_absent", detail="device has no /ring endpoint")
            return
        if response.status_code != 200:
            log.debug("slot_led_rejected", status=response.status_code, slots=payload)
            return

        if payload != self.last_payload:
            log.info("slot_led_updated", slots=payload)
        self.last_payload = payload
        self.last_sent_at = now
