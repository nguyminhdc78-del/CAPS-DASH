"""`export_service.csv_safe` and the streamed CSV it feeds.

The single most important behaviour in the whole export endpoint: a slot or
camera code shaped like a spreadsheet formula must never reach a cell
unescaped, or opening the export in Excel/Sheets executes it (OWASP
CWE-1236, "CSV injection").
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from caps_dash.config.settings import Settings
from caps_dash.db.engine_factory import create_db_engine
from caps_dash.db.enums import CameraSourceType, SlotState
from caps_dash.db.models import Base, Camera, ParkingSlot, SlotStateHistory
from caps_dash.db.session import create_session_factory
from caps_dash.services import export_service
from caps_dash.services.export_service import csv_safe

# --- csv_safe: the escaping rule itself -------------------------------------


def test_a_leading_equals_is_escaped() -> None:
    assert csv_safe("=cmd()") == "'=cmd()"


def test_a_leading_plus_is_escaped() -> None:
    assert csv_safe("+1+1") == "'+1+1"


def test_a_leading_minus_is_escaped() -> None:
    assert csv_safe("-2+3") == "'-2+3"


def test_a_leading_at_sign_is_escaped() -> None:
    assert csv_safe("@SUM(A1:A9)") == "'@SUM(A1:A9)"


def test_a_leading_tab_or_carriage_return_is_escaped() -> None:
    assert csv_safe("\t=evil()") == "'\t=evil()"
    assert csv_safe("\r=evil()") == "'\r=evil()"


def test_ordinary_text_passes_through_unescaped() -> None:
    assert csv_safe("A1") == "A1"
    assert csv_safe("CAM-01") == "CAM-01"


def test_none_becomes_empty_string() -> None:
    assert csv_safe(None) == ""


def test_non_string_values_are_stringified_first() -> None:
    assert csv_safe(True) == "True"
    assert csv_safe(42) == "42"


# --- end to end: a malicious slot code survives the whole export path -------


def _build_factory(tmp_path: Path) -> tuple[sessionmaker[Session], Engine]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'export.db'}")
    Base.metadata.create_all(engine)
    return create_session_factory(engine), engine


def test_a_formula_shaped_slot_code_is_escaped_in_the_streamed_csv(tmp_path: Path) -> None:
    factory, engine = _build_factory(tmp_path)
    try:
        session = factory()
        camera = Camera(
            code="CAM-A", name="Deck A", floor="B1", source_type=CameraSourceType.FAKE
        )
        # An operator-entered slot code shaped exactly like a spreadsheet
        # formula - the scenario `csv_safe` exists to defuse.
        slot = ParkingSlot(code="=cmd()", floor="B1")
        camera.slots = [slot]
        session.add(camera)
        session.commit()
        session.add(
            SlotStateHistory(
                slot_id=slot.id, camera_code="=cmd()", slot_code="=cmd()", floor="B1",
                previous_state=SlotState.FREE, new_state=SlotState.OCCUPIED,
                changed_at=dt.datetime(2026, 8, 11, 8, 0, tzinfo=dt.UTC),
            )
        )
        session.commit()
        session.close()

        settings = Settings(
            app_env="dev",
            secret_key="test-secret-not-used-in-prod-0123456789",
            database_url=f"sqlite:///{tmp_path / 'export.db'}",
        )
        lines = list(
            export_service.stream_history_csv(
                factory, settings, since=None, until=None, slot_id=None, camera_code=None,
                floor=None,
            )
        )
        body = "".join(lines)

        # The raw, unescaped formula must never appear as its own cell -
        # only ever preceded by the defusing apostrophe.
        assert "'=cmd()" in body
        assert ",=cmd()," not in body
    finally:
        engine.dispose()
