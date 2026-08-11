"""ASGI entry point: `uvicorn caps_dash.main:app`."""

from __future__ import annotations

from .app_factory import create_app
from .config.settings import get_settings

app = create_app(get_settings())
