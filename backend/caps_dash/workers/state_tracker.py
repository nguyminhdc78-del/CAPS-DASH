"""Turning a stream of slot states into the changes worth recording.

History is written ONLY when a state changes. Writing every scan for a
100-slot site at one second per scan is 8.6 million rows a day - it fills the
disk and wears out the flash the target board boots from, while adding no
information the change rows do not already carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..vision.domain import SlotState


@dataclass(frozen=True, slots=True)
class SlotChange:
    slot_code: str
    previous: SlotState
    new: SlotState


@dataclass(slots=True)
class StateTracker:
    """Remembers what each slot was last reported as."""

    known: dict[str, SlotState] = field(default_factory=dict)

    def diff(self, states: dict[str, SlotState]) -> list[SlotChange]:
        """Return only the slots whose state differs from last time.

        The first observation of a slot counts as a change only when it is no
        longer UNKNOWN: the vote filter reports UNKNOWN during warm-up, and
        recording "became unknown" for every slot at every restart would fill
        the history with noise that means nothing.
        """
        changes: list[SlotChange] = []
        for slot_code, new_state in states.items():
            previous = self.known.get(slot_code)
            if previous == new_state:
                continue
            if previous is None and new_state is SlotState.UNKNOWN:
                self.known[slot_code] = new_state
                continue
            changes.append(
                SlotChange(
                    slot_code=slot_code,
                    previous=previous or SlotState.UNKNOWN,
                    new=new_state,
                )
            )
            self.known[slot_code] = new_state
        return changes

    def reset(self) -> None:
        self.known.clear()
