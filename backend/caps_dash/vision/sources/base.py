"""Camera frame source contract.

READ() MUST NEVER RAISE. Every implementation returns `Frame(ok=False, ...)`
instead of letting an exception escape - a dead or misconfigured camera must
not take down the worker loop for the other cameras. This is the single most
violated rule in this kind of code, so it is stated here in capitals rather
than trusted to a comment nobody reads.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from ...db.types import utc_now


@dataclass(frozen=True, slots=True)
class Frame:
    """One frame pulled from a camera source.

    `jpeg_bytes` is the ORIGINAL encoded bytes the source received or
    produced - Phase 08 streams this exact byte string to the browser with no
    re-encoding (the overlay is drawn client-side from JSON), so the image a
    viewer sees and the frame the detector ran against can never disagree
    about which moment they describe. Re-encoding every frame would also burn
    CPU nobody would ever see the benefit of on the aarch64 board.

    `image` is the array decoded from those same bytes - what the detector
    actually runs against. Carrying both together, instead of decoding twice
    downstream, is what keeps them in sync.
    """

    camera_id: int
    timestamp: datetime
    image: np.ndarray | None
    jpeg_bytes: bytes | None
    ok: bool
    error: str | None = None


def failed_frame(camera_id: int, error: str) -> Frame:
    """Build the `ok=False` result every source returns instead of raising."""
    return Frame(
        camera_id=camera_id,
        timestamp=utc_now(),
        image=None,
        jpeg_bytes=None,
        ok=False,
        error=error,
    )


class FrameSource(ABC):
    """Pulls frames for one camera. See the module docstring: `read()` never raises."""

    @property
    @abstractmethod
    def camera_id(self) -> int: ...

    @property
    @abstractmethod
    def fail_streak(self) -> int:
        """Consecutive failed reads. Resets to 0 on the next success.

        A worker loop (phase 06) compares this against
        `settings.camera_fail_streak_offline` to decide when a camera counts
        as down; this class only counts, it does not judge.
        """

    @abstractmethod
    def read(self) -> Frame: ...

    @abstractmethod
    def close(self) -> None: ...
