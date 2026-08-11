"""Camera frame source backends behind one ABC."""

from __future__ import annotations

from .base import Frame, FrameSource, failed_frame
from .fake_source import FakeSource
from .source_factory import build_source

__all__ = [
    "FakeSource",
    "Frame",
    "FrameSource",
    "build_source",
    "failed_frame",
]
