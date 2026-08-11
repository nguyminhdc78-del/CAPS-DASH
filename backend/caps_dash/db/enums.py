"""Enumerations persisted as strings.

Stored as `String` with a `CheckConstraint` rather than a native database enum:
portable to PostgreSQL later, and free of the migration pain native enums cause
on SQLite, which cannot alter them at all.
"""

from __future__ import annotations

from enum import StrEnum


class SlotState(StrEnum):
    """Mirror of `caps_dash.vision.domain.states.SlotState`.

    Deliberately a second definition. The domain package must not import the
    ORM - that is what keeps it dependency-free and testable without hardware.
    A parity test asserts the two never drift apart.
    """

    UNKNOWN = "UNKNOWN"
    FREE = "FREE"
    OCCUPIED = "OCCUPIED"


class UserRole(StrEnum):
    RESIDENT = "resident"
    SECURITY = "security"
    ADMIN = "admin"


class CameraSourceType(StrEnum):
    """Where a camera's frames come from.

    The non-hardware sources are not test scaffolding - there is no camera
    hardware on hand, so development, the demo and CI all depend on them.
    """

    ESP32CAM_HTTP = "esp32cam_http"
    IMAGE_FOLDER = "image_folder"
    VIDEO_FILE = "video_file"
    FAKE = "fake"


class AlertType(StrEnum):
    CAMERA_OFFLINE = "camera_offline"
    OVERSTAY = "overstay"
    DISK_LOW = "disk_low"
    SLOT_OVERLAP = "slot_overlap"
    CLOCK_UNSYNCED = "clock_unsynced"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ScopeType(StrEnum):
    SLOT = "slot"
    FLOOR = "floor"
    SITE = "site"


class AuditAction(StrEnum):
    LOGIN = "login"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"  # noqa: S105 - an action name, not a secret
    SESSION_REVOKED = "session_revoked"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DISABLED = "user_disabled"
    CAMERA_CREATED = "camera_created"
    CAMERA_UPDATED = "camera_updated"
    CAMERA_DELETED = "camera_deleted"
    SLOT_MAP_UPDATED = "slot_map_updated"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    CONFIDENCE_CHANGED = "confidence_changed"
    BACKUP_CREATED = "backup_created"
    DATA_PURGED = "data_purged"


def values(enum_cls: type[StrEnum]) -> list[str]:
    """Member values, for building a CheckConstraint."""
    return [member.value for member in enum_cls]
