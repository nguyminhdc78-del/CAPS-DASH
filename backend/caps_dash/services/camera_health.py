"""Composing `CameraWithHealth` from a DB row plus the running worker.

Split out of `camera_service.py` to keep that module under the 200-line cap.
Kept separate because it is read-only composition (no session mutation, no
audit, no commit) - a different shape of code from the CRUD functions next to
it, and one `list_cameras`/`get_camera` both need.
"""

from __future__ import annotations

from ..api.schemas.camera_schemas import CameraHealth, CameraResponse, CameraWithHealth
from ..db.models import Camera
from .service_context import ServiceContext


def with_health(camera: Camera, slot_count: int, ctx: ServiceContext) -> CameraWithHealth:
    base = CameraResponse.model_validate(camera).model_dump()
    return CameraWithHealth(**base, slot_count=slot_count, health=_build_health(camera.id, ctx))


def _build_health(camera_id: int, ctx: ServiceContext) -> CameraHealth | None:
    """Live counters from the running worker - never the database.

    `None` when no loop is running for this camera (disabled, or nobody has
    started the supervisor - every test). In-memory dict lookups only, no
    query, so composing this for a whole page of cameras costs nothing extra.
    """
    if ctx.supervisor is None:
        return None
    context = ctx.supervisor.context_for(camera_id)
    if context is None:
        return None
    metrics = context.metrics
    viewers = ctx.hub.viewer_count(camera_id) if ctx.hub is not None else 0
    return CameraHealth(
        online=metrics.is_online(ctx.settings.camera_fail_streak_offline),
        frames_ok=metrics.frames_ok,
        frames_failed=metrics.frames_failed,
        fail_streak=metrics.fail_streak,
        errors=metrics.errors,
        process_ms=metrics.last_process_ms,
        average_process_ms=metrics.average_process_ms,
        viewers=viewers,
    )
