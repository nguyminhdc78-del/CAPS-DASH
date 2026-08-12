"""Reading and changing an ESP32-CAM's sensor settings.

Consumed from `async def` routes - the same sanctioned exception to the
sync-handler rule as `camera_diagnostics_service`, and for the same reason:
this is pure network I/O to a device, with no ORM work beyond the row that
names its address.

WHY THIS EXISTS AT ALL, in one measurement. With `aec`, `agc` and `awb` on
automatic the sensor hunts continuously and the whole frame shifts brightness
between shots. Measured on the reference camera, that puts frame-to-frame
noise at 7.5 mean absolute difference with peaks of 38 - while a car covering
a sixth of the frame reads about 13. The change gate that keeps YOLO off 89%
of frames cannot separate those, so inference fires constantly and the board
saturates. Locked and settled, noise falls to 0.8. Being able to lock the
exposure from the dashboard is therefore not a convenience feature; it is
what makes the detection pipeline affordable on this hardware.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..config.settings import Settings
from ..db.enums import AuditAction, CameraSourceType
from ..db.models import Camera
from ..errors.codes import ErrorCode
from ..errors.exceptions import UpstreamError, ValidationFailedError
from ..observability.credential_redaction import redact_credentials
from ..security.current_user import CurrentUser
from . import audit_service
from .service_context import ServiceContext

# Only the HTTP-reachable ESP32 sources expose a control endpoint. A folder or
# a video file has no sensor to tune, and saying so plainly beats a timeout.
CONTROLLABLE_SOURCES = frozenset(
    {CameraSourceType.ESP32CAM_HTTP, CameraSourceType.ESP32CAM_STREAM}
)

# Mirrors the firmware's `/control` handler. Ranges come from the esp32-camera
# driver, not from preference: a value outside them is rejected by the sensor
# and would come back as a bare 400 with no explanation.
SETTING_RANGES: dict[str, tuple[int, int]] = {
    "framesize": (0, 13),
    "quality": (4, 63),
    "brightness": (-2, 2),
    "contrast": (-2, 2),
    "saturation": (-2, 2),
    "gainceiling": (0, 6),
    "awb": (0, 1),
    "agc": (0, 1),
    "aec": (0, 1),
    "aec_value": (0, 1200),
    "agc_gain": (0, 30),
    "hmirror": (0, 1),
    "vflip": (0, 1),
    "lenc": (0, 1),
    "wb_mode": (0, 4),
    "led": (0, 1),
}

# Applied together by `lock_exposure`. Three separate calls to the firmware,
# one operator action - nobody should have to remember that "lock the
# exposure" means three different sensor flags.
EXPOSURE_LOCK = {"aec": 0, "agc": 0, "awb": 0}


@dataclass(frozen=True, slots=True)
class SensorSettings:
    """What the camera reports about itself. Shape follows the firmware."""

    values: dict[str, Any]


def device_base(source_type: str, source_url: str, code: str) -> str:
    """`http://host` from the configured frame URL, without its path.

    Takes primitives rather than a `Camera` row: the camera worker holds a
    detached `CameraConfig`, never an ORM instance bound to a session that
    lives in another thread.

    The stored URL points at `/anh` or `/stream`; the control endpoints live
    beside them, so the path is dropped rather than guessed at.
    """
    if source_type not in CONTROLLABLE_SOURCES:
        raise ValidationFailedError(
            f"Camera {code} has no controllable sensor",
            code=ErrorCode.CAMERA_SOURCE_INVALID,
        )
    parts = urlsplit(source_url)
    if not parts.scheme or not parts.netloc:
        raise ValidationFailedError(
            f"Camera {code} has no usable source_url",
            code=ErrorCode.CAMERA_SOURCE_INVALID,
        )
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _device_base(camera: Camera) -> str:
    return device_base(camera.source_type, camera.source_url, camera.code)


async def read_settings(camera: Camera, settings: Settings) -> SensorSettings:
    """Ask the camera what it is currently set to."""
    base = _device_base(camera)
    try:
        async with httpx.AsyncClient(timeout=settings.camera_timeout_s) as client:
            response = await client.get(f"{base}/status")
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpstreamError(
            redact_credentials(f"Camera did not report its settings: {exc}"),
            code=ErrorCode.CAMERA_UNREACHABLE,
        ) from exc
    return SensorSettings(values=payload)


def validate(changes: dict[str, int]) -> dict[str, int]:
    """Reject unknown names and out-of-range values before touching the device.

    The firmware answers an unknown `var` with a 404 and an out-of-range value
    with a bare 400; neither tells an operator which of five sliders was
    wrong. Checking here means the error names the field.
    """
    if not changes:
        raise ValidationFailedError("No settings given")
    for name, value in changes.items():
        bounds = SETTING_RANGES.get(name)
        if bounds is None:
            raise ValidationFailedError(f"Unknown camera setting: {name!r}")
        low, high = bounds
        if not low <= value <= high:
            raise ValidationFailedError(
                f"{name} must be between {low} and {high}, got {value}"
            )
    return changes


async def apply_settings(
    camera: Camera, changes: dict[str, int], settings: Settings
) -> dict[str, bool]:
    """Send each change to the device. Returns which ones it accepted.

    Sequential, not concurrent: the firmware's WebServer is single-threaded,
    and firing five requests at once at a module that is also streaming makes
    them queue anyway - with the added risk of one timing out and leaving the
    sensor half-configured.
    """
    return await apply_to(_device_base(camera), changes, settings)


async def apply_to(
    base: str, changes: dict[str, int], settings: Settings
) -> dict[str, bool]:
    """The primitive form, for callers that have no ORM row."""
    applied: dict[str, bool] = {}
    async with httpx.AsyncClient(timeout=settings.camera_timeout_s) as client:
        for name, value in changes.items():
            try:
                response = await client.get(
                    f"{base}/control", params={"var": name, "val": value}
                )
                applied[name] = response.status_code == 200
            except httpx.HTTPError as exc:
                raise UpstreamError(
                    redact_credentials(f"Camera refused {name}: {exc}"),
                    code=ErrorCode.CAMERA_UNREACHABLE,
                ) from exc
    return applied


async def reapply_remembered(
    *, source_type: str, source_url: str, code: str,
    remembered: dict[str, int], settings: Settings,
) -> dict[str, bool]:
    """Push remembered settings back onto a camera that has just restarted.

    Called when a worker builds its context - on startup and on every reload.
    Best-effort by design: a camera that does not answer is already reported
    through its own fail-streak, and failing to restore a brightness value
    must not stop the loop from running.
    """
    if not remembered or source_type not in CONTROLLABLE_SOURCES:
        return {}
    base = device_base(source_type, source_url, code)
    return await apply_to(base, validate(dict(remembered)), settings)


async def update(
    session: Any,
    *,
    camera: Camera,
    changes: dict[str, int],
    actor: CurrentUser,
    ctx: ServiceContext,
) -> dict[str, bool]:
    """Validate, apply, and record who changed the camera's optics.

    Audited like any other mutation: a slot that starts reading wrong after
    somebody dropped the exposure to zero should be traceable to that change,
    the same way a redrawn slot map is.
    """
    validate(changes)
    applied = await apply_settings(camera, changes, ctx.settings)

    # Remember the intent, not just the effect. The device forgets on every
    # power cycle; this row is what lets the worker put it back.
    camera.sensor_settings_json = {**dict(camera.sensor_settings_json or {}), **changes}

    audit_service.record(
        session,
        action=AuditAction.CAMERA_UPDATED,
        username=actor.username,
        user_id=actor.id,
        entity_type="camera_sensor",
        entity_id=str(camera.id),
        after={"changes": changes, "applied": applied},
        client_ip=ctx.client_ip,
    )
    await asyncio.to_thread(session.commit)
    return applied
