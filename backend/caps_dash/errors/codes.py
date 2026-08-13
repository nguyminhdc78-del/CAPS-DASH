"""Machine-readable error codes.

These strings are a public contract: the frontend maps each one to a
Vietnamese and an English message. Add freely, but **never rename or reuse**
an existing value - a renamed code silently degrades into an untranslated
error on every client that has not shipped a matching update.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    # Generic
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"

    # Authentication and authorisation
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_SESSION_REVOKED = "AUTH_SESSION_REVOKED"
    AUTH_SESSION_REUSED = "AUTH_SESSION_REUSED"
    AUTH_INACTIVE_USER = "AUTH_INACTIVE_USER"
    AUTH_TOKEN_TYPE_MISMATCH = "AUTH_TOKEN_TYPE_MISMATCH"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"

    # Users
    USER_LAST_ADMIN = "USER_LAST_ADMIN"
    USER_NAME_TAKEN = "USER_NAME_TAKEN"

    # Cameras and the vision pipeline
    CAMERA_UNREACHABLE = "CAMERA_UNREACHABLE"
    CAMERA_BUSY = "CAMERA_BUSY"
    CAMERA_DISABLED = "CAMERA_DISABLED"
    CAMERA_CODE_TAKEN = "CAMERA_CODE_TAKEN"
    CAMERA_SOURCE_INVALID = "CAMERA_SOURCE_INVALID"
    SLOT_CODE_TAKEN = "SLOT_CODE_TAKEN"
    SLOT_MAP_INVALID = "SLOT_MAP_INVALID"
    SLOT_MAP_FRAME_MISMATCH = "SLOT_MAP_FRAME_MISMATCH"
    POLYGON_DEGENERATE = "POLYGON_DEGENERATE"
    SNAPSHOT_UNAVAILABLE = "SNAPSHOT_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    VIEWER_LIMIT_REACHED = "VIEWER_LIMIT_REACHED"

    # Realtime. Sent as WebSocket close reasons, not response bodies.
    WS_AUTH_TIMEOUT = "WS_AUTH_TIMEOUT"
    WS_TOKEN_EXPIRED = "WS_TOKEN_EXPIRED"
    WS_FORBIDDEN = "WS_FORBIDDEN"
    WS_CAMERA_UNKNOWN = "WS_CAMERA_UNKNOWN"
    WS_TOO_MANY_CONNECTIONS = "WS_TOO_MANY_CONNECTIONS"

    # Reporting
    RANGE_TOO_WIDE = "RANGE_TOO_WIDE"
    RANGE_INVALID = "RANGE_INVALID"

    # Operations
    BACKUP_FAILED = "BACKUP_FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

    # Public kiosk
    # 404: raised when the public surface is off (PUBLIC_KIOSK_ENABLED=false)
    # or when a plate search is requested while PLATE_READING_ENABLED is off
    # (nothing to search - the search affordance should be hidden by the
    # frontend before this is ever reached, but the backend refuses either
    # way rather than trusting that it was).
    PUBLIC_KIOSK_DISABLED = "PUBLIC_KIOSK_DISABLED"
