"""Shared runtime state.

Created once in the lifespan and reached through `request.app.state.caps`.
Deliberately NOT module-level globals with setter functions - that pattern
makes the wiring invisible, blocks testing two configurations in one process,
and was one of the reference project's worst habits.

Later phases populate the optional fields; phase 01 leaves them None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config.settings import Settings

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance only
    from sqlalchemy import Engine
    from sqlalchemy.orm import sessionmaker


@dataclass(slots=True)
class AppState:
    """Everything a request handler may need that outlives a single request."""

    settings: Settings

    # Phase 02
    engine: Engine | None = None
    session_factory: sessionmaker[Any] | None = None

    # Phase 06 - camera worker runtime
    supervisor: Any = None

    # Phase 08 - websocket fan-out hub
    hub: Any = None

    # Cross-cutting singletons keyed by name (rate limiter, executors, ...)
    services: dict[str, Any] = field(default_factory=dict)

    def require_session_factory(self) -> sessionmaker[Any]:
        """Fail loudly rather than hand back None into a request handler."""
        if self.session_factory is None:
            raise RuntimeError("Database is not initialised; lifespan did not run")
        return self.session_factory
