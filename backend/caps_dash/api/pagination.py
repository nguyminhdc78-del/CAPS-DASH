"""Offset pagination.

One helper rather than `limit`/`offset` parameters copied into a dozen route
signatures, because the server-side cap is the point: without it a client can
ask for the whole `slot_state_history` table and the board spends a minute
serialising it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(slots=True, frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Rows per page"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> PageParams:
    """FastAPI dependency. The `le=MAX_LIMIT` is the cap, enforced by validation."""
    return PageParams(limit=limit, offset=offset)


def count_rows(session: Session, statement: Select[Any]) -> int:
    """Total matching rows, ignoring limit/offset.

    Ordering is stripped: it changes nothing about a count, and SQLite refuses
    an ORDER BY over a column the subquery does not select.
    """
    subquery = statement.order_by(None).subquery()
    return int(session.execute(select(func.count()).select_from(subquery)).scalar_one())


def apply_page(statement: Select[Any], params: PageParams) -> Select[Any]:
    return statement.limit(params.limit).offset(params.offset)
