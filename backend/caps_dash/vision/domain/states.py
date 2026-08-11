"""The three states a parking slot may hold."""

from __future__ import annotations

from enum import StrEnum


class SlotState(StrEnum):
    """Occupancy of a single slot.

    UNKNOWN is a real answer, not a placeholder for FREE. Before the vote
    filter has seen a full window the system has not established what is in
    the slot, and saying "free" would send a driver to a space nobody has
    actually looked at. Consumers must never fold UNKNOWN into a free count.
    """

    UNKNOWN = "UNKNOWN"
    FREE = "FREE"
    OCCUPIED = "OCCUPIED"
