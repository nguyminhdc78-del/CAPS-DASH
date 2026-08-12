"""Camera input validation that is business logic, not schema shape.

Split out of `camera_service.py` to keep that module under the 200-line cap.
Both checks exist because the wrong value would otherwise surface as either a
500 (an `IntegrityError` from the `threshold_within_window` CHECK constraint)
or an SSRF/credential-leak surface (an unvalidated `source_url`) instead of a
422 the caller can act on.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ..db.enums import CameraSourceType
from ..errors.codes import ErrorCode
from ..errors.exceptions import ValidationFailedError

_URL_SCHEMES = {"http", "https"}

# Which schemes each network source accepts. Driven by a table rather than a
# chain of `if`s so that adding a source type cannot quietly land in the
# "unchecked" branch - which is how `esp32cam_stream` went unvalidated after
# it was introduced.
_SCHEMES_BY_SOURCE: dict[CameraSourceType, frozenset[str]] = {
    CameraSourceType.ESP32CAM_HTTP: frozenset({"http", "https"}),
    CameraSourceType.ESP32CAM_STREAM: frozenset({"http", "https"}),
    CameraSourceType.RTSP: frozenset({"rtsp", "rtsps"}),
}

_PATH_SOURCES = (CameraSourceType.IMAGE_FOLDER, CameraSourceType.VIDEO_FILE)


def validate_source_url(source_type: CameraSourceType, source_url: str) -> None:
    """Scheme check for the one input that is also an SSRF/credential surface.

    Empty is allowed: a camera is often created before its source is wired
    up, and the worker already fails loudly (see `source_factory._require_url`)
    if it tries to run one with nothing configured.
    """
    if not source_url:
        return
    parsed = urlsplit(source_url)

    allowed = _SCHEMES_BY_SOURCE.get(source_type)
    if allowed is not None:
        if parsed.scheme not in allowed or not parsed.hostname:
            expected = " or ".join(sorted(allowed))
            raise ValidationFailedError(
                f"source_url must be a {expected} URL for {source_type}",
                code=ErrorCode.CAMERA_SOURCE_INVALID,
            )
        return

    if source_type in _PATH_SOURCES and parsed.scheme in _URL_SCHEMES:
        raise ValidationFailedError(
            f"source_url must be a filesystem path for {source_type}, not a URL",
            code=ErrorCode.CAMERA_SOURCE_INVALID,
        )
    # FAKE: anything goes, including empty - it ignores source_url entirely.


def validate_vote_thresholds(window: int, threshold: int) -> None:
    """Mirrors the `threshold_within_window` CHECK constraint on `cameras`."""
    if threshold > window:
        raise ValidationFailedError("vote_threshold cannot exceed vote_window")
