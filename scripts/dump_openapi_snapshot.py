"""Write the OpenAPI document to `docs/openapi.json`.

The committed document is the contract between this backend and the SPA: the
frontend's TypeScript types are generated from it, and a test diffs the live
schema against it. So a contract change is never silent - it shows up as a diff
in this file, in the same commit as the code that caused it.

Built from the app object rather than by curling a running server, so it works
in CI and on a machine with no database.

    python scripts/dump_openapi_snapshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

SNAPSHOT_PATH = REPO_ROOT / "docs" / "openapi.json"


def build_snapshot() -> dict[str, object]:
    from caps_dash.app_factory import create_app
    from caps_dash.config.settings import Settings

    # Dev settings on purpose: `openapi_url` is disabled in prod, and the
    # document must not depend on the machine it was generated on.
    settings = Settings(
        app_env="dev",
        secret_key="snapshot-generation-key-not-used-for-signing",
        database_url="sqlite:///:memory:",
    )
    document: dict[str, object] = create_app(settings).openapi()
    return document


def main() -> int:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = build_snapshot()
    # Sorted keys and a trailing newline so the diff of a real change is
    # readable rather than a reordering of the whole file.
    #
    # `newline="\n"` is what makes this file the same on every machine. Without
    # it, Python translates "\n" to the platform separator on write, so a
    # Windows developer commits CRLF and CI - which regenerates the file on
    # Linux and diffs it - sees all 8446 lines change and calls the contract
    # stale. The diff is unreadable and says nothing about what actually
    # changed. `.gitattributes` pins the same rule on git's side.
    SNAPSHOT_PATH.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paths = len(document.get("paths", {}))  # type: ignore[arg-type]
    print(f"wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)} ({paths} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
