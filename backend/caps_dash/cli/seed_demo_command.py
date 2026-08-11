"""`caps-dash seed-demo` - a working dataset with no hardware attached.

Not a convenience. There is no camera hardware on hand, so a demo camera backed
by sample images is the only way to exercise the pipeline end to end during
development, in CI, and at a competition table.
"""

from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy import select

from ..config.settings import get_settings
from ..db.engine_factory import create_db_engine
from ..db.enums import CameraSourceType
from ..db.models import Camera, ParkingSlot
from ..db.session import create_session_factory, session_scope
from ..observability.logging_setup import get_logger

logger = get_logger(__name__)

DEMO_CAMERA_CODE = "demo-01"

# A 3x1 row of slots across the lower half of a 640x480 frame. Rectangles are
# enough to prove the pipeline; real maps are drawn in the ROI editor.
DEMO_SLOTS: list[tuple[str, list[list[float]]]] = [
    ("A1", [[40, 260], [220, 260], [220, 430], [40, 430]]),
    ("A2", [[230, 260], [410, 260], [410, 430], [230, 430]]),
    ("A3", [[420, 260], [600, 260], [600, 430], [420, 430]]),
]


def add_seed_demo_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "seed-demo", help="Create a demo camera and slots for hardware-free testing"
    )
    parser.add_argument(
        "--source",
        default="",
        help="Image folder or video file to read frames from (default: fake generator)",
    )
    parser.set_defaults(handler=run_seed_demo)


def run_seed_demo(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)

    with session_scope(factory) as session:
        existing = session.execute(
            select(Camera).where(Camera.code == DEMO_CAMERA_CODE)
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("seed_demo_skipped", reason="demo camera already exists")
            return 0

        camera = Camera(
            code=DEMO_CAMERA_CODE,
            name="Demo camera (no hardware)",
            floor="B1",
            source_type=(
                CameraSourceType.IMAGE_FOLDER if args.source else CameraSourceType.FAKE
            ),
            source_url=args.source,
            frame_width=640,
            frame_height=480,
        )
        camera.slots = [
            ParkingSlot(
                code=code,
                floor="B1",
                polygon_json=polygon,
                src_frame_width=640,
                src_frame_height=480,
            )
            for code, polygon in DEMO_SLOTS
        ]
        session.add(camera)

    engine.dispose()
    logger.info("seed_demo_created", camera=DEMO_CAMERA_CODE, slots=len(DEMO_SLOTS))
    return 0
