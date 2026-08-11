"""Periodic job: sweep idle login rate-limiter keys and expired
`refresh_sessions` rows.

Two unrelated cleanups sharing one schedule slot (hourly) because both are
"drop rows/keys nobody can use productively again" and both are cheap:
- `SlidingWindowLimiter.sweep_idle()` - an in-process dict that otherwise
  grows one entry per distinct username ever attempted (`security/
  rate_limiter.py`).
- Expired/revoked/rotated `refresh_sessions` rows (validation session 1:
  otherwise this table also grows without bound).
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from ..db.session import session_scope
from ..observability.logging_setup import get_logger
from ..security.rate_limiter import SlidingWindowLimiter
from ..services import retention_service

logger = get_logger(__name__)


def run(factory: sessionmaker[Session], login_limiter: SlidingWindowLimiter) -> None:
    idle_keys_removed = login_limiter.sweep_idle()
    with session_scope(factory) as session:
        refresh_sessions_purged = retention_service.purge_expired_refresh_sessions(session)
    logger.info(
        "rate_limiter_sweep_job_ran",
        idle_keys_removed=idle_keys_removed,
        refresh_sessions_purged=refresh_sessions_purged,
    )
