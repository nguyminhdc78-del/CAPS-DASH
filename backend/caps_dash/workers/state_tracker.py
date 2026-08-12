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
    """Remembers what each slot was last reported as.

    Only ever remembers FREE or OCCUPIED. UNKNOWN is not an observation about
    a slot - `SlotVoteFilter` returns it in exactly one situation, before it
    has seen a full window of frames, and never returns to it afterwards
    except through `reset()`. So "became unknown" always means "this process
    started", never "something happened in the car park", and it is kept out
    of the history entirely.
    """

    known: dict[str, SlotState] = field(default_factory=dict)

    def seed(self, states: dict[str, SlotState]) -> None:
        """Prime from the states already persisted for these slots.

        Without this, every restart wrote one phantom `UNKNOWN -> FREE` row
        per slot: the tracker began empty, the filter warmed up, and the first
        real state looked like a change. Restarting the process is not a
        parking event. Seeded, a warm-up that lands on the state the database
        already holds produces nothing, while a car that arrived or left while
        the process was down still produces exactly one row - which is the
        change that genuinely happened, and the row `session_derivation`
        needs to open or close a session.
        """
        self.known.update(
            {
                slot_code: state
                for slot_code, state in states.items()
                if state is not SlotState.UNKNOWN
            }
        )

    def diff(self, states: dict[str, SlotState]) -> list[SlotChange]:
        """Return only the slots whose state differs from last time."""
        changes: list[SlotChange] = []
        for slot_code, new_state in states.items():
            if new_state is SlotState.UNKNOWN:
                continue
            previous = self.known.get(slot_code)
            if previous == new_state:
                continue
            changes.append(
                SlotChange(
                    slot_code=slot_code,
                    # None only for a slot never resolved before - its first
                    # ever reading, once in the slot's lifetime.
                    previous=previous or SlotState.UNKNOWN,
                    new=new_state,
                )
            )
            self.known[slot_code] = new_state
        return changes

    def reset(self) -> None:
        self.known.clear()
