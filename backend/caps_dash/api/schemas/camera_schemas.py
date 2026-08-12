"""Camera and slot-map schemas."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...db.enums import CameraSourceType
from ...observability.credential_redaction import redact_credentials, sanitize_source_url
from .polygon_schemas import PolygonModel

# Re-exported: `camera_service` redacts its audit snapshots with this, and a
# service importing from `api.schemas` would point the dependency arrow the
# wrong way. The function itself lives in `observability`, which both the API
# layer and the vision layer can reach.
__all__ = [
    "CameraHealth",
    "CameraResponse",
    "CameraSettingsResponse",
    "CameraWithHealth",
    "ConnectionTestRequest",
    "ConnectionTestResponse",
    "CreateCameraRequest",
    "RuntimeTuningRequest",
    "SlotMapEntry",
    "SlotMapRequest",
    "SlotMapResponse",
    "UpdateCameraRequest",
    "UpdateCameraSettingsRequest",
    "sanitize_source_url",
]


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    floor: str
    source_type: str
    source_url: str
    poll_interval_s: float
    vote_window: int
    vote_threshold: int
    confidence: float
    is_enabled: bool
    frame_width: int
    frame_height: int
    last_seen_at: dt.datetime | None
    last_error: str

    @field_validator("source_url", mode="before")
    @classmethod
    def _strip_credentials(cls, value: str) -> str:
        return sanitize_source_url(value)

    @field_validator("last_error", mode="before")
    @classmethod
    def _redact_error(cls, value: str) -> str:
        """Defence in depth.

        The worker already redacts before persisting, but this field carries
        whatever text a device driver produced, and it is readable by every
        security-role user while `source_url` above is admin-only. One missed
        redaction upstream would leak a camera password to a wider audience
        than the URL itself ever had.
        """
        return redact_credentials(value)


class CameraHealth(BaseModel):
    """Live counters from the running worker, not from the database.

    `slot_count` deliberately lives on `CameraWithHealth`, not here: it comes
    from a database aggregate and is known even when no worker is running,
    whereas every field below is `None`-if-absent together (see `health` on
    `CameraWithHealth`) because they describe a live process, not a row.
    """

    online: bool
    frames_ok: int
    frames_failed: int
    fail_streak: int
    errors: int
    process_ms: float
    average_process_ms: float
    viewers: int


class CameraWithHealth(CameraResponse):
    slot_count: int = 0
    # None when no worker is running for this camera (disabled, or a test) -
    # never fabricated zeros, which would read as "online with nothing to
    # report" instead of "we don't know".
    health: CameraHealth | None = None


class CreateCameraRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(default="", max_length=120)
    floor: str = Field(default="B1", max_length=16)
    source_type: CameraSourceType = CameraSourceType.ESP32CAM_HTTP
    source_url: str = Field(default="", max_length=255)
    poll_interval_s: float = Field(default=3.0, gt=0, le=300)
    vote_window: int = Field(default=5, ge=1, le=60)
    vote_threshold: int = Field(default=4, ge=1, le=60)
    confidence: float = Field(default=0.25, gt=0, lt=1)
    is_enabled: bool = True


class UpdateCameraRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    floor: str | None = Field(default=None, max_length=16)
    source_type: CameraSourceType | None = None
    source_url: str | None = Field(default=None, max_length=255)
    poll_interval_s: float | None = Field(default=None, gt=0, le=300)
    vote_window: int | None = Field(default=None, ge=1, le=60)
    vote_threshold: int | None = Field(default=None, ge=1, le=60)
    confidence: float | None = Field(default=None, gt=0, lt=1)
    is_enabled: bool | None = None


class RuntimeTuningRequest(BaseModel):
    """Live adjustment that must NOT restart the worker.

    The right confidence depends on the lighting in front of that particular
    camera, and finding out it is wrong during a demo is too late to fix by
    editing a file and restarting.
    """

    confidence: float = Field(gt=0, lt=1)


class ConnectionTestRequest(BaseModel):
    """Try an unsaved camera, so an installer can check before committing it."""

    source_type: CameraSourceType
    source_url: str = Field(default="", max_length=255)


class ConnectionTestResponse(BaseModel):
    ok: bool
    latency_ms: float
    frame_width: int = 0
    frame_height: int = 0
    error: str = ""
    error_code: str = ""

    @field_validator("error", mode="before")
    @classmethod
    def _redact_error(cls, value: str) -> str:
        """The probe URL comes straight from the caller, credentials and all."""
        return redact_credentials(value)


class UpdateCameraSettingsRequest(BaseModel):
    """Sensor settings, all optional - only what is sent gets changed.

    `lock_exposure` expands to `aec` and `agc` together - the two that make
    the change gate usable. Left automatic they hunt, the whole frame shifts
    brightness between shots, and that reads as motion.

    White balance is deliberately excluded. Measured, locking it too changes
    noise by 0.1 against a threshold of 8, while costing colour accuracy on a
    detector trained against normally-coloured images.
    """

    brightness: int | None = Field(default=None, ge=-2, le=2)
    contrast: int | None = Field(default=None, ge=-2, le=2)
    saturation: int | None = Field(default=None, ge=-2, le=2)
    quality: int | None = Field(default=None, ge=4, le=63, description="Lower is better")
    framesize: int | None = Field(default=None, ge=0, le=13)
    aec: int | None = Field(default=None, ge=0, le=1, description="Auto exposure")
    agc: int | None = Field(default=None, ge=0, le=1, description="Auto gain")
    awb: int | None = Field(default=None, ge=0, le=1, description="Auto white balance")
    aec_value: int | None = Field(default=None, ge=0, le=1200)
    agc_gain: int | None = Field(default=None, ge=0, le=30)
    hmirror: int | None = Field(default=None, ge=0, le=1)
    vflip: int | None = Field(default=None, ge=0, le=1)
    led: int | None = Field(default=None, ge=0, le=1, description="Flash LED")
    lock_exposure: bool | None = Field(
        default=None, description="Turn aec, agc and awb off together"
    )

    def to_changes(self) -> dict[str, int]:
        """Flatten to the flat name->value map the firmware understands."""
        changes = {
            name: value
            for name, value in self.model_dump(exclude={"lock_exposure"}).items()
            if value is not None
        }
        if self.lock_exposure is not None:
            locked = 0 if self.lock_exposure else 1
            # Explicit flags win: someone who sends both meant the specific one.
            for flag in ("aec", "agc"):
                changes.setdefault(flag, locked)
        return changes


class CameraSettingsResponse(BaseModel):
    camera_id: int
    # Whatever the firmware reports, passed through rather than modelled
    # field by field: the set grows with the sensor driver, and a strict model
    # here would reject a camera that knows one setting more than this schema.
    settings: dict[str, Any]
    # Present only on a write: which changes the device accepted.
    applied: dict[str, bool] | None = None


class SlotMapEntry(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    floor: str = Field(default="B1", max_length=16)
    polygon: PolygonModel


class SlotMapRequest(BaseModel):
    """Replaces a camera's whole slot map in one transaction.

    Whole-map rather than per-slot edits: the editor works on the map as a
    unit, and a half-applied save would leave the camera matching vehicles
    against a layout nobody drew.
    """

    src_frame_width: int = Field(gt=0, le=8000)
    src_frame_height: int = Field(gt=0, le=8000)
    slots: list[SlotMapEntry] = Field(max_length=200)
    # A code present in the current map but absent from `slots` is normally
    # rejected (see `slot_map_service.replace`): deleting a slot cascades its
    # `slot_state_history`, destroying the audit trail. The editor must set
    # this explicitly to confirm the loss.
    allow_delete: bool = False


class SlotMapResponse(BaseModel):
    camera_id: int
    src_frame_width: int
    src_frame_height: int
    slots: list[SlotMapEntry]
