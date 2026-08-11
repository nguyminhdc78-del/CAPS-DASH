"""Camera CRUD and the paginated/single read paths with live health attached.

Mutation template (create/update/delete/runtime) matches the one in the
phase-07 plan: repository read, snapshot, mutate, flush, audit, commit, THEN
signal the worker - never before `commit()`, or the reload races the write
and the loop reads pre-commit rows, which looks like the save silently
failing. Validation (`camera_validation.py`) and health composition
(`camera_health.py`) are split out to keep this file under the 200-line cap.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..api.pagination import PageParams
from ..api.schemas.camera_schemas import (
    CameraWithHealth,
    CreateCameraRequest,
    RuntimeTuningRequest,
    UpdateCameraRequest,
    sanitize_source_url,
)
from ..db.enums import AuditAction, CameraSourceType
from ..db.models import Camera
from ..errors.codes import ErrorCode
from ..errors.exceptions import ConflictError
from ..repositories import camera_repository
from ..security.current_user import CurrentUser
from . import audit_service
from .camera_health import with_health
from .camera_validation import validate_source_url, validate_vote_thresholds
from .service_context import ServiceContext

# The detector's own working range - values outside this are technically
# valid floats but never produce a useful vote, so the endpoint clamps rather
# than lets an installer set 0.001 and wonder why every slot reads UNKNOWN.
RUNTIME_CONFIDENCE_MIN = 0.01
RUNTIME_CONFIDENCE_MAX = 0.95


def list_cameras(
    session: Session, ctx: ServiceContext, params: PageParams
) -> tuple[list[CameraWithHealth], int]:
    rows, total = camera_repository.list_page_with_slot_counts(
        session, limit=params.limit, offset=params.offset
    )
    return [with_health(camera, slot_count, ctx) for camera, slot_count in rows], total


def get_camera(session: Session, camera_id: int, ctx: ServiceContext) -> CameraWithHealth:
    camera = camera_repository.get_or_raise(session, camera_id)
    slot_count = camera_repository.count_slots(session, camera_id)
    return with_health(camera, slot_count, ctx)


def create_camera(
    session: Session, *, actor: CurrentUser, payload: CreateCameraRequest, ctx: ServiceContext
) -> Camera:
    code = payload.code.strip()
    validate_source_url(payload.source_type, payload.source_url)
    validate_vote_thresholds(payload.vote_window, payload.vote_threshold)
    if camera_repository.get_by_code(session, code) is not None:
        raise ConflictError(
            f"Camera code {code!r} is already taken", code=ErrorCode.CAMERA_CODE_TAKEN
        )

    camera = Camera(code=code, **payload.model_dump(exclude={"code"}))
    session.add(camera)
    session.flush()  # assign the id before the audit row references it

    _audit(session, AuditAction.CAMERA_CREATED, actor, camera.id, ctx, after=_snapshot(camera))
    session.commit()
    # A brand-new camera has no running loop yet; reconcile is what spawns
    # one - `request_reload` would target an event nobody is listening to.
    ctx.request_reconcile()
    return camera


def update_camera(
    session: Session,
    *,
    actor: CurrentUser,
    camera_id: int,
    payload: UpdateCameraRequest,
    ctx: ServiceContext,
) -> Camera:
    camera = camera_repository.get_or_raise(session, camera_id)
    before = _snapshot(camera)
    was_enabled = camera.is_enabled

    _validate_partial_update(camera, payload)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(camera, field, value)
    session.flush()

    _audit(session, AuditAction.CAMERA_UPDATED, actor, camera.id, ctx, before, _snapshot(camera))
    session.commit()

    ctx.request_reload(camera.id)
    if payload.is_enabled is not None and payload.is_enabled != was_enabled:
        # Enabling or disabling changes which loops should be running at all,
        # not just this camera's own configuration.
        ctx.request_reconcile()
    return camera


def delete_camera(
    session: Session, *, actor: CurrentUser, camera_id: int, ctx: ServiceContext
) -> None:
    camera = camera_repository.get_or_raise(session, camera_id)
    before = _snapshot(camera)
    camera_repository.delete(session, camera)

    _audit(session, AuditAction.CAMERA_DELETED, actor, camera_id, ctx, before=before)
    session.commit()
    ctx.request_reconcile()
    # Drop the cached still too. `Camera.id` is a SQLite rowid alias, and
    # rowids are reused - so without this the next camera created would be
    # handed the deleted camera's last frame as its first paint, complete with
    # a header naming the old camera.
    if ctx.hub is not None:
        ctx.hub.forget(camera_id)


def update_runtime(
    session: Session,
    *,
    actor: CurrentUser,
    camera_id: int,
    payload: RuntimeTuningRequest,
    ctx: ServiceContext,
) -> Camera:
    camera = camera_repository.get_or_raise(session, camera_id)
    clamped = min(max(payload.confidence, RUNTIME_CONFIDENCE_MIN), RUNTIME_CONFIDENCE_MAX)
    before = {"confidence": camera.confidence}
    camera.confidence = clamped
    session.flush()

    _audit(
        session, AuditAction.CONFIDENCE_CHANGED, actor, camera.id, ctx,
        before, {"confidence": clamped},
    )
    session.commit()
    ctx.request_reload(camera.id)  # tuning only - no restart, no reconcile
    return camera


def _validate_partial_update(camera: Camera, payload: UpdateCameraRequest) -> None:
    effective_type = payload.source_type or CameraSourceType(camera.source_type)
    effective_url = payload.source_url if payload.source_url is not None else camera.source_url
    if payload.source_type is not None or payload.source_url is not None:
        validate_source_url(effective_type, effective_url)

    effective_window = (
        payload.vote_window if payload.vote_window is not None else camera.vote_window
    )
    effective_threshold = (
        payload.vote_threshold if payload.vote_threshold is not None else camera.vote_threshold
    )
    validate_vote_thresholds(effective_window, effective_threshold)


def _audit(
    session: Session,
    action: AuditAction,
    actor: CurrentUser,
    camera_id: int,
    ctx: ServiceContext,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    audit_service.record(
        session,
        action=action,
        username=actor.username,
        user_id=actor.id,
        entity_type="camera",
        entity_id=str(camera_id),
        before=before,
        after=after,
        client_ip=ctx.client_ip,
    )


def _snapshot(camera: Camera) -> dict[str, Any]:
    """Audit before/after payload. `source_url` is sanitised - an audit log is
    read by more people than the database itself."""
    return {
        "code": camera.code,
        "name": camera.name,
        "floor": camera.floor,
        "source_type": camera.source_type,
        "source_url": sanitize_source_url(camera.source_url),
        "poll_interval_s": camera.poll_interval_s,
        "vote_window": camera.vote_window,
        "vote_threshold": camera.vote_threshold,
        "confidence": camera.confidence,
        "is_enabled": camera.is_enabled,
    }
