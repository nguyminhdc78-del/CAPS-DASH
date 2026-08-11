"""What a service needs to know about the caller and the running system.

Bundled into one object so service signatures stay at three or four
parameters. Without it every mutating service would take `request_id`,
`client_ip`, `reload_signals`, `supervisor` and `settings` individually, and
each new cross-cutting concern would mean editing every signature again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config.settings import Settings
from ..workers.reload_signals import ReloadSignals


@dataclass(slots=True, frozen=True)
class ServiceContext:
    """Per-request context handed to services that mutate or signal."""

    settings: Settings
    request_id: str = ""
    client_ip: str = ""
    reload_signals: ReloadSignals | None = None
    supervisor: Any = None
    hub: Any = None

    def request_reload(self, camera_id: int) -> None:
        """Ask a running camera loop to pick up new configuration.

        Call this **after** `session.commit()`. Signalling first lets the loop
        reload and read the pre-commit rows, which looks like the save silently
        failing. No-op when no runtime is attached (tests, CLI).
        """
        if self.reload_signals is not None:
            self.reload_signals.request(camera_id)

    def request_reconcile(self) -> None:
        """A camera was added, removed, enabled or disabled. Also post-commit."""
        if self.reload_signals is not None:
            self.reload_signals.request_reconcile()
