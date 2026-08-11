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
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"

    # Cameras and the vision pipeline
    CAMERA_UNREACHABLE = "CAMERA_UNREACHABLE"
    CAMERA_BUSY = "CAMERA_BUSY"
    CAMERA_DISABLED = "CAMERA_DISABLED"
    SLOT_MAP_INVALID = "SLOT_MAP_INVALID"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    VIEWER_LIMIT_REACHED = "VIEWER_LIMIT_REACHED"

    # Operations
    BACKUP_FAILED = "BACKUP_FAILED"
