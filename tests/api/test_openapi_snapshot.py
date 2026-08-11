"""The API contract is frozen in a committed file.

`docs/openapi.json` is what the frontend generates its TypeScript from. If the
live schema drifts from it, the SPA compiles against a contract the server no
longer honours - and nothing fails until a user clicks the thing. This test
turns that into a red build instead.

A deliberate contract change is fine: run `python
scripts/dump_openapi_snapshot.py` and commit the diff alongside the code that
caused it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI

SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"

REGENERATE = "python scripts/dump_openapi_snapshot.py"


@pytest.fixture
def live_schema(app: FastAPI) -> dict[str, object]:
    schema: dict[str, object] = app.openapi()
    return schema


def test_snapshot_exists():
    assert SNAPSHOT_PATH.exists(), f"missing contract snapshot; run: {REGENERATE}"


def test_every_path_in_the_live_schema_is_in_the_snapshot(live_schema):
    """Paths are checked separately from the rest, because this is the failure
    that matters most: a route added or renamed without the frontend knowing."""
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    live_paths = set(live_schema["paths"])
    snapshot_paths = set(snapshot["paths"])

    assert live_paths == snapshot_paths, (
        f"API paths drifted from the committed contract; run: {REGENERATE}\n"
        f"added: {sorted(live_paths - snapshot_paths)}\n"
        f"removed: {sorted(snapshot_paths - live_paths)}"
    )


def test_operation_ids_are_stable(live_schema):
    """`operation_id` names the generated TypeScript function. Renaming one is
    a breaking change for every caller, so it is asserted explicitly."""
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert _operation_ids(live_schema) == _operation_ids(snapshot), (
        f"operation ids drifted from the committed contract; run: {REGENERATE}"
    )


def test_schemas_match(live_schema):
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    live_components = live_schema.get("components", {}).get("schemas", {})
    snapshot_components = snapshot.get("components", {}).get("schemas", {})

    assert set(live_components) == set(snapshot_components), (
        f"response/request models drifted; run: {REGENERATE}"
    )
    for name, definition in sorted(live_components.items()):
        assert definition == snapshot_components[name], (
            f"schema '{name}' changed shape; run: {REGENERATE}"
        )


def _operation_ids(document: dict[str, object]) -> set[str]:
    paths: dict[str, dict[str, object]] = document["paths"]  # type: ignore[assignment]
    return {
        operation["operationId"]  # type: ignore[index]
        for methods in paths.values()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
