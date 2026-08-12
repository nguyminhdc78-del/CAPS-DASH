"""Scheme validation per source type.

`source_url` is the one camera field that is also an SSRF and credential
surface, so the wrong scheme has to be a 422 the caller can act on rather
than a timeout hours later in a worker nobody is watching.
"""

from __future__ import annotations

import pytest

from caps_dash.db.enums import CameraSourceType
from caps_dash.errors.exceptions import ValidationFailedError
from caps_dash.services.camera_validation import validate_source_url


@pytest.mark.parametrize(
    ("source_type", "url"),
    [
        (CameraSourceType.ESP32CAM_HTTP, "http://192.168.137.50/anh"),
        (CameraSourceType.ESP32CAM_STREAM, "http://192.168.137.50/stream"),
        (CameraSourceType.RTSP, "rtsp://192.168.137.227:8554/live"),
        (CameraSourceType.RTSP, "rtsps://cam.example/live"),
        (CameraSourceType.IMAGE_FOLDER, "/var/lib/caps/frames"),
        (CameraSourceType.VIDEO_FILE, "C:/clips/demo.mp4"),
        (CameraSourceType.FAKE, "anything at all"),
    ],
)
def test_accepts_the_right_shape_for_each_source(
    source_type: CameraSourceType, url: str
) -> None:
    validate_source_url(source_type, url)


@pytest.mark.parametrize(
    ("source_type", "url"),
    [
        # An RTSP URL on a polling source would be fetched as HTTP and fail
        # forever with an error that names none of this.
        (CameraSourceType.ESP32CAM_HTTP, "rtsp://cam/live"),
        (CameraSourceType.ESP32CAM_STREAM, "rtsp://cam/live"),
        # And the reverse: an HTTP URL handed to the RTSP decoder.
        (CameraSourceType.RTSP, "http://cam/anh"),
        (CameraSourceType.RTSP, "/var/lib/caps/frames"),
        # A scheme with no host is not a usable address either.
        (CameraSourceType.RTSP, "rtsp://"),
        (CameraSourceType.IMAGE_FOLDER, "http://cam/anh"),
    ],
)
def test_rejects_a_url_the_source_cannot_use(
    source_type: CameraSourceType, url: str
) -> None:
    with pytest.raises(ValidationFailedError):
        validate_source_url(source_type, url)


@pytest.mark.parametrize("source_type", list(CameraSourceType))
def test_empty_is_allowed_for_every_source(source_type: CameraSourceType) -> None:
    """A camera is often created before its source is wired up; the worker
    fails loudly later if one is enabled with nothing configured."""
    validate_source_url(source_type, "")


def test_every_source_type_is_covered_by_one_rule_or_the_other() -> None:
    """The regression this guards: `esp32cam_stream` was added to the enum and
    silently landed in the unvalidated branch, so any string was accepted for
    it until this table replaced the chain of ifs."""
    from caps_dash.services.camera_validation import _PATH_SOURCES, _SCHEMES_BY_SOURCE

    classified = set(_SCHEMES_BY_SOURCE) | set(_PATH_SOURCES) | {CameraSourceType.FAKE}

    assert classified == set(CameraSourceType)
