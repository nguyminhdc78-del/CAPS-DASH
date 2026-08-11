"""System operations: `/system/info`, `/system/backup`, `/system/purge`.

Backup and purge both run their real work on the shared `db_pool` executor
(the same single-writer thread the camera worker uses - see `lifespan.py`),
never on the request thread directly, and both are guarded by
`AppState.services["system_op_lock"]` so at most one such operation runs at
a time (Security Considerations, phase 13).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session, sessionmaker

from ...app_state import AppState
from ...config.settings import Settings
from ...db.enums import UserRole
from ...db.models import User
from ...db.session import get_session, session_scope
from ...errors.codes import ErrorCode
from ...errors.exceptions import AppError, AuthError, ConflictError
from ...repositories import user_repository
from ...security.current_user import CurrentUser
from ...security.rbac import require_role
from ...services import backup_service, retention_service, system_service
from ..deps import RequestContext, get_app_state, get_request_context, get_settings_dep
from ..schemas.system_schemas import (
    BackupResponse,
    PurgeRequest,
    PurgeResponse,
    SystemInfoResponse,
)

router = APIRouter(prefix="/system", tags=["System"])

AdminOnly = Depends(require_role(UserRole.ADMIN))


def _actor(session: Session, current: CurrentUser) -> User:
    """Load the acting account for the audit row. Mirrors `alert_routes._actor`."""
    user = user_repository.get_by_id(session, current.id)
    if user is None:
        raise AuthError("Account no longer exists", code=ErrorCode.AUTH_INACTIVE_USER)
    return user


def _acquire_op_lock(state: AppState) -> None:
    lock = state.services["system_op_lock"]
    if not lock.acquire(blocking=False):
        raise ConflictError(
            "A backup or purge operation is already running; try again shortly.",
            code=ErrorCode.CONFLICT,
        )


@router.get("/info", response_model=SystemInfoResponse, summary="Operational status snapshot")
def get_system_info(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    _: CurrentUser = AdminOnly,
) -> SystemInfoResponse:
    return system_service.get_system_info(session, settings)


@router.post(
    "/backup",
    response_model=BackupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a database backup",
)
def create_backup(
    session: Session = Depends(get_session),
    state: AppState = Depends(get_app_state),
    current: CurrentUser = AdminOnly,
    context: RequestContext = Depends(get_request_context),
) -> BackupResponse:
    actor = _actor(session, current)
    engine = state.engine
    if engine is None:
        raise AppError(
            "Database is not initialised", code=ErrorCode.INTERNAL_ERROR, status_code=500
        )

    _acquire_op_lock(state)
    try:
        db_pool = state.services["db_pool"]
        future = db_pool.submit(
            backup_service.create_backup_and_audit,
            engine,
            state.require_session_factory(),
            state.settings,
            actor_username=actor.username,
            actor_user_id=actor.id,
            client_ip=context.client_ip,
        )
        result: BackupResponse = future.result()
        return result
    finally:
        state.services["system_op_lock"].release()


@router.post(
    "/purge",
    response_model=PurgeResponse,
    summary="Purge data past the retention window",
)
def purge_data(
    payload: PurgeRequest,
    session: Session = Depends(get_session),
    state: AppState = Depends(get_app_state),
    current: CurrentUser = AdminOnly,
    context: RequestContext = Depends(get_request_context),
) -> PurgeResponse:
    actor = _actor(session, current)

    _acquire_op_lock(state)
    try:
        db_pool = state.services["db_pool"]
        future = db_pool.submit(
            _run_purge,
            state.require_session_factory(),
            state.settings,
            payload,
            actor,
            context.client_ip,
        )
        result: retention_service.PurgeResult = future.result()
    finally:
        state.services["system_op_lock"].release()

    return PurgeResponse(
        deleted_history_rows=result.deleted_history_rows,
        deleted_alert_rows=result.deleted_alert_rows,
        dry_run=payload.dry_run,
    )


def _run_purge(
    factory: sessionmaker[Session],
    settings: Settings,
    payload: PurgeRequest,
    actor: User,
    client_ip: str,
) -> retention_service.PurgeResult:
    """Runs on `db_pool`: opens its own session, same reason
    `export_service.py` and `slot_state_service.py` do - a `Session` is not
    safe to share across threads.
    """
    with session_scope(factory) as session:
        return retention_service.purge(
            session,
            settings=settings,
            older_than_months=payload.older_than_months,
            dry_run=payload.dry_run,
            actor_username=actor.username,
            actor_user_id=actor.id,
            client_ip=client_ip,
        )
