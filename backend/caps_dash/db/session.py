"""Session construction and scoping.

One `Session` class, used identically by request handlers and by the camera
worker's database thread. That uniformity is the payoff of choosing sync
SQLAlchemy throughout: no async/sync bridge, no second engine, no greenlet.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        # Objects stay usable after commit, so a handler can return an entity
        # it just wrote without triggering a fresh SELECT per attribute.
        expire_on_commit=False,
        autoflush=False,
    )


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope for non-request code (worker threads, CLI)."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency.

    Commit is the caller's job: a GET should not be able to write by accident,
    and a service that has already committed should not be committed twice.
    Rollback on exception is automatic.
    """
    factory = request.app.state.caps.require_session_factory()
    session: Session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
