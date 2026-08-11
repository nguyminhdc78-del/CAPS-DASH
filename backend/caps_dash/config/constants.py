"""Domain constants that are not user-tunable.

Anything an operator might reasonably want to change belongs in `settings.py`.
What lives here is fixed by the problem, not by preference - changing these
changes the meaning of the data, so they are not exposed as configuration.
"""

from __future__ import annotations

from enum import StrEnum

# SlotState is deliberately NOT defined here. It belongs to the vision domain
# (`caps_dash.vision.domain.states`), which is a dependency-free leaf package.
# Anything outside the domain imports it from there; the DB layer keeps its own
# copy with a parity test, because the domain must never import the ORM.


class Role(StrEnum):
    """Roles, ranked. See `ROLE_RANK` - comparison is by rank, not equality."""

    RESIDENT = "resident"
    SECURITY = "security"
    ADMIN = "admin"


# Higher rank includes every permission of the ranks below it, so routes
# declare a minimum instead of enumerating every role that qualifies.
ROLE_RANK: dict[str, int] = {
    Role.RESIDENT: 1,
    Role.SECURITY: 2,
    Role.ADMIN: 3,
}


class AlertKind(StrEnum):
    CAMERA_OFFLINE = "camera_offline"
    OVERSTAY = "overstay"
    DISK_LOW = "disk_low"
    SLOT_OVERLAP = "slot_overlap"
    CLOCK_UNSYNCED = "clock_unsynced"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Fraction of the bounding box's bottom-band sample points that must fall
# inside a polygon for the fallback assignment step to accept it.
# 0.40 tolerates a slot drawn ~20% of a vehicle height short while still
# rejecting a car that merely clips the edge. Raising it to 0.60 makes hits
# hard to earn; dropping to 0.20 starts claiming neighbours' cars.
MIN_BOTTOM_BAND_OVERLAP = 0.40

# Bottom fraction of a bounding box used for that fallback sampling. The upper
# portion is roof and body, which overhang the row behind under the oblique
# ceiling-mounted view this system is built for.
BOTTOM_BAND_FRACTION = 0.30
BOTTOM_BAND_COLS = 5
BOTTOM_BAND_ROWS = 5

# Consecutive capture failures before a camera is reported offline.
DEFAULT_FAIL_STREAK_OFFLINE = 3

# WebSocket close codes (RFC 6455 plus our policy usage).
WS_CLOSE_POLICY_VIOLATION = 1008
WS_CLOSE_INTERNAL_ERROR = 1011
WS_CLOSE_TRY_AGAIN_LATER = 1013
