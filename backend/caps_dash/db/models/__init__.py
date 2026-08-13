"""Every model, imported so Alembic autogenerate can see the full metadata.

A model missing from this list is invisible to autogenerate: its table simply
never appears in a migration, and the omission only surfaces at runtime.
"""

from __future__ import annotations

from ..base import Base
from .alert import Alert
from .audit_log import AuditLog
from .camera import Camera
from .hourly_stat import HourlyStat
from .parking_slot import ParkingSlot
from .plate_read import PlateRead
from .refresh_session import RefreshSession
from .slot_state_history import SlotStateHistory
from .user import User

__all__ = [
    "Alert",
    "AuditLog",
    "Base",
    "Camera",
    "HourlyStat",
    "ParkingSlot",
    "PlateRead",
    "RefreshSession",
    "SlotStateHistory",
    "User",
]
