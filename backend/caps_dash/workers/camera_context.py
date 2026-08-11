"""Everything one camera loop needs, rebuilt whenever its config changes."""

from __future__ import annotations

import asyncio
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import Settings
from ..db.models import Camera, ParkingSlot
from ..db.session import session_scope
from ..db.types import utc_now
from ..errors.exceptions import NotFoundError
from ..realtime.broadcast_hub import BroadcastHub
from ..realtime.frame_header import build_frame_header
from ..vision.domain import Slot, SlotMap, SlotMapFilter, build_filter
from ..vision.frame_change_gate import FrameChangeGate
from ..vision.sources.base import FrameSource
from ..vision.sources.source_factory import build_source
from .camera_metrics import CameraMetrics
from .inference_runner import InferenceOutcome
from .reload_signals import ReloadSignals
from .state_tracker import StateTracker


@dataclass(slots=True)
class CameraConfig:
    """A snapshot of the database row, so the loop never holds an ORM object.

    Detached values only: an ORM instance belongs to the session that loaded
    it, and the loop runs on the event loop while sessions live in worker
    threads.
    """

    id: int
    code: str
    floor: str
    poll_interval_s: float
    vote_window: int
    vote_threshold: int
    confidence: float
    source_type: str
    source_url: str


@dataclass(slots=True)
class CameraContext:
    """One camera's live state."""

    config: CameraConfig
    settings: Settings
    session_factory: sessionmaker[Session]
    loop: asyncio.AbstractEventLoop
    inference_pool: ThreadPoolExecutor
    db_pool: ThreadPoolExecutor
    hub: BroadcastHub
    reload_signals: ReloadSignals

    source: FrameSource
    slot_map: SlotMap
    vote_filter: SlotMapFilter
    state_tracker: StateTracker = field(default_factory=StateTracker)
    change_gate: FrameChangeGate = field(
        default_factory=lambda: FrameChangeGate(threshold=3.0, force_interval_s=10.0)
    )
    metrics: CameraMetrics = field(default_factory=CameraMetrics)

    # The most recent frame, kept so the ROI editor's snapshot endpoint can be
    # served without a second request to the camera. One JPEG per camera - a
    # few tens of kilobytes - and it saves the ESP32 a round trip every time an
    # installer opens the editor.
    last_jpeg: bytes | None = None
    last_frame_size: tuple[int, int] = (0, 0)
    last_frame_at: dt.datetime | None = None

    # The last real inference, kept so a frame the change gate skipped can
    # still be published with results that describe it. The scene did not
    # change - that is why it was skipped - so these are current, not stale.
    last_outcome: InferenceOutcome | None = None
    last_states: dict[str, Any] = field(default_factory=dict)
    last_fitted: SlotMap | None = None

    @property
    def camera_id(self) -> int:
        return self.config.id

    def remember_frame(self, jpeg: bytes, width: int, height: int) -> None:
        self.last_jpeg = jpeg
        self.last_frame_size = (width, height)
        self.last_frame_at = utc_now()

    def remember_result(
        self, outcome: InferenceOutcome, states: dict[str, Any], fitted: SlotMap
    ) -> None:
        """Keep the last real detection, for frames the change gate skips."""
        self.last_outcome = outcome
        self.last_states = dict(states)
        self.last_fitted = fitted

    def close(self) -> None:
        self.source.close()

    def build_header(
        self, outcome: InferenceOutcome, states: dict[str, Any], seq: int, fitted: SlotMap
    ) -> dict[str, Any]:
        """The JSON half of a realtime message.

        `fitted` is passed in rather than recomputed: the loop has already
        scaled the map to this frame to run assignment against it, and fitting
        twice per tick is pure waste on a board with no CPU to spare.
        """
        return build_frame_header(
            camera_id=self.config.id,
            camera_code=self.config.code,
            seq=seq,
            outcome=outcome,
            states=states,
            fitted=fitted,
        )


def load_camera_config(session: Session, camera_id: int) -> CameraConfig:
    camera = session.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError(f"No camera with id {camera_id}")
    return CameraConfig(
        id=camera.id,
        code=camera.code,
        floor=camera.floor,
        poll_interval_s=camera.poll_interval_s,
        vote_window=camera.vote_window,
        vote_threshold=camera.vote_threshold,
        confidence=camera.confidence,
        source_type=camera.source_type,
        source_url=camera.source_url,
    )


def load_slot_map(session: Session, config: CameraConfig) -> SlotMap:
    rows = list(
        session.execute(
            select(ParkingSlot)
            .where(ParkingSlot.camera_id == config.id, ParkingSlot.is_active.is_(True))
            .order_by(ParkingSlot.code)
        ).scalars()
    )
    slots = [
        Slot(row.code, [(float(x), float(y)) for x, y in row.polygon_json])
        for row in rows
        if len(row.polygon_json) >= 3
    ]
    # Frame dimensions come from the slot rows, which record the size of the
    # still the polygons were drawn on. Without them the two axis scale
    # factors cannot be computed independently.
    first = rows[0] if rows else None
    return SlotMap(
        slots=slots,
        width=first.src_frame_width if first else 640,
        height=first.src_frame_height if first else 480,
        camera_id=config.code,
    )


def build_context(
    *,
    camera_id: int,
    settings: Settings,
    session_factory: sessionmaker[Session],
    loop: asyncio.AbstractEventLoop,
    inference_pool: ThreadPoolExecutor,
    db_pool: ThreadPoolExecutor,
    hub: BroadcastHub,
    reload_signals: ReloadSignals,
) -> CameraContext:
    """Load a camera from the database and assemble its runtime context.

    The vote filter is built FRESH here, every time. Reusing one across a
    reload lets a newly drawn slot inherit the votes of whatever slot happened
    to share its code - wrong, and completely silent.
    """
    with session_scope(session_factory) as session:
        config = load_camera_config(session, camera_id)
        slot_map = load_slot_map(session, config)

    source = _build_source_for(config, settings)

    return CameraContext(
        config=config,
        settings=settings,
        session_factory=session_factory,
        loop=loop,
        inference_pool=inference_pool,
        db_pool=db_pool,
        hub=hub,
        reload_signals=reload_signals,
        source=source,
        slot_map=slot_map,
        vote_filter=build_filter(
            slot_map.slot_ids, config.vote_window, config.vote_threshold
        ),
        # Fresh per context: a rebuilt camera has a new slot map, so the
        # reference frame from the old one describes a layout that no longer
        # applies and must not gate the first frame under the new one.
        change_gate=FrameChangeGate(
            threshold=settings.motion_change_threshold,
            force_interval_s=settings.motion_force_interval_s,
        ),
    )


def _build_source_for(config: CameraConfig, settings: Settings) -> FrameSource:
    """`build_source` wants a Camera row; give it a stand-in carrying the same fields."""

    class _Row:
        id = config.id
        code = config.code
        source_type = config.source_type
        source_url = config.source_url

    return build_source(_Row(), settings)  # type: ignore[arg-type]
