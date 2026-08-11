"""Builds a `FrameSource` from a camera row.

The only place `source_type` / `source_url` are branched on - implementations
never read the DB or settings themselves, matching `detector_factory`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ...config.settings import Settings
from ...db.enums import CameraSourceType
from ...errors.exceptions import ValidationFailedError
from .base import FrameSource
from .esp32cam_http_source import Esp32CamHttpSource
from .fake_source import FakeSource
from .image_folder_source import ImageFolderSource
from .video_file_source import VideoFileSource

if TYPE_CHECKING:
    from ...db.models.camera import Camera


def build_source(camera: Camera, settings: Settings) -> FrameSource:
    try:
        source_type = CameraSourceType(camera.source_type)
    except ValueError as exc:
        raise ValidationFailedError(
            f"Unknown camera source_type: {camera.source_type!r}"
        ) from exc

    match source_type:
        case CameraSourceType.ESP32CAM_HTTP:
            return Esp32CamHttpSource(
                camera.id, _require_url(camera), settings.camera_timeout_s
            )
        case CameraSourceType.IMAGE_FOLDER:
            return ImageFolderSource(camera.id, Path(_require_url(camera)))
        case CameraSourceType.VIDEO_FILE:
            return VideoFileSource(camera.id, Path(_require_url(camera)))
        case CameraSourceType.FAKE:
            return FakeSource(camera.id)
        case _:
            # Unreachable while CameraSourceType keeps exactly these four
            # members; kept as a defensive backstop rather than trusted to
            # the enum never growing without this factory being updated too.
            raise ValidationFailedError(f"Unhandled camera source_type: {source_type!r}")


def _require_url(camera: Camera) -> str:
    if not camera.source_url:
        raise ValidationFailedError(f"Camera {camera.code} has no source_url configured")
    return camera.source_url
