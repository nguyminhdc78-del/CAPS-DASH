"""Connection probing and snapshot retrieval - the two operations that reach
outside the process instead of only touching the database.

Both are consumed from `async def` routes (the one sanctioned exception to
the sync-handler rule; see `camera_diagnostics_routes.py`), so every blocking
call here runs through `asyncio.to_thread` and is bounded by
`settings.camera_timeout_s` via `asyncio.wait_for`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from ..config.settings import Settings
from ..db.enums import CameraSourceType
from ..db.models import Camera
from ..db.types import utc_now
from ..errors.codes import ErrorCode
from ..errors.exceptions import AppError, UpstreamError
from ..vision.sources.base import FrameSource
from ..vision.sources.source_factory import build_source
from .service_context import ServiceContext


@dataclass(frozen=True)
class ConnectionProbeResult:
    """Mirrors `ConnectionTestResponse` field for field - a diagnostic result,
    never a raised exception, because a dead camera answering the probe is
    the expected case this endpoint exists to report."""

    ok: bool
    latency_ms: float
    frame_width: int = 0
    frame_height: int = 0
    error: str = ""
    error_code: str = ""


class _DraftCameraRow:
    """Stand-in for a `Camera` row, for building a source from unsaved input.

    `build_source` only reads `id`/`code`/`source_type`/`source_url` - the
    same trick `workers/camera_context.py::_build_source_for` uses to test a
    row that was never a real `Camera` instance.
    """

    def __init__(self, camera_id: int, code: str, source_type: str, source_url: str) -> None:
        self.id = camera_id
        self.code = code
        self.source_type = source_type
        self.source_url = source_url


async def test_connection(
    *, camera_id: int, code: str, source_type: CameraSourceType, source_url: str, settings: Settings
) -> ConnectionProbeResult:
    """One-shot fetch through a throwaway `FrameSource`. Always closes it."""
    row = _DraftCameraRow(camera_id, code, source_type, source_url)
    try:
        source: FrameSource = build_source(row, settings)  # type: ignore[arg-type]
    except AppError as exc:
        # A bad source_type/source_url is a failed diagnostic, not a 4xx -
        # the installer is precisely here to find that out before saving.
        return ConnectionProbeResult(False, 0.0, error=exc.message, error_code=str(exc.code))

    start = time.monotonic()
    try:
        frame = await asyncio.wait_for(
            asyncio.to_thread(source.read), timeout=settings.camera_timeout_s
        )
    except TimeoutError:
        latency_ms = (time.monotonic() - start) * 1000
        return ConnectionProbeResult(
            False, latency_ms, error="timed out", error_code=str(ErrorCode.CAMERA_UNREACHABLE)
        )
    finally:
        await asyncio.to_thread(source.close)

    latency_ms = (time.monotonic() - start) * 1000
    if not frame.ok or frame.image is None:
        return ConnectionProbeResult(
            False, latency_ms, error=frame.error or "no frame",
            error_code=str(ErrorCode.CAMERA_UNREACHABLE),
        )

    height, width = frame.image.shape[:2]
    return ConnectionProbeResult(True, latency_ms, frame_width=width, frame_height=height)


async def get_snapshot(*, camera: Camera, ctx: ServiceContext) -> bytes:
    """Prefer the worker's cached still; fall back to one live read.

    The ROI editor polls this endpoint repeatedly while an installer draws
    polygons - serving the cache whenever it is fresh enough keeps that from
    turning into a live request to the ESP32 on every keystroke.
    """
    context = ctx.supervisor.context_for(camera.id) if ctx.supervisor is not None else None
    if context is not None and context.last_jpeg is not None and context.last_frame_at is not None:
        age_s = (utc_now() - context.last_frame_at).total_seconds()
        if age_s <= ctx.settings.snapshot_max_age_s:
            # `ctx.supervisor` is `Any` by design (see `ServiceContext`); pin
            # the type here so the cached-frame path returns `bytes`, not `Any`.
            cached: bytes = context.last_jpeg
            return cached

    jpeg = await _fetch_live(camera, ctx.settings)
    if jpeg is None:
        raise UpstreamError(
            "Camera did not return a usable frame", code=ErrorCode.SNAPSHOT_UNAVAILABLE
        )
    return jpeg


async def _fetch_live(camera: Camera, settings: Settings) -> bytes | None:
    """A throwaway source, not the worker's - its own may be mid-read on
    another thread, and this must never block that loop's next tick."""
    source = build_source(camera, settings)
    try:
        frame = await asyncio.wait_for(
            asyncio.to_thread(source.read), timeout=settings.camera_timeout_s
        )
    except TimeoutError:
        return None
    finally:
        await asyncio.to_thread(source.close)
    return frame.jpeg_bytes if frame.ok else None
