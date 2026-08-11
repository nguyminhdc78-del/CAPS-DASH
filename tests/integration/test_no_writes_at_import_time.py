"""Guards against the reference project's worst habit: a key file written the
moment a module is imported, before any deliberate `caps-dash` command has
run. If this regresses, a stray `python -c "import caps_dash"` on a fresh
clone - or simply collecting this test suite - would leave files on disk that
nobody asked for.

Run as a subprocess, in a fresh interpreter, rather than reloading modules
in-process: `caps_dash.config.settings.get_settings` is `lru_cache`d, and
several modules hold module-level references to classes from
`caps_dash.db.models` (SQLAlchemy's declarative registry). Reloading those in
the same process as the rest of the suite would either mask the very cache
this test needs to bypass, or corrupt other tests' ORM state. A subprocess
sidesteps both problems and is also a more honest simulation of "a fresh
clone, a fresh interpreter" than any in-process trick.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# Alembic's `env.py` is exec'd by Alembic's own runner inside a
# `MigrationContext` it configures first; imported bare it either raises
# immediately (no active context) or, worse, would run real migrations
# against the *default* database path (outside this test's tmp_path) if it
# somehow proceeded. It is exercised by `caps-dash migrate` and by
# `tests/db/test_schema_consistency.py` instead, and (like mypy/ruff already
# do for this project) is deliberately excluded here.
_EXCLUDED_PREFIX = "caps_dash.db.migrations"

_IMPORT_EVERYTHING = f"""
import pkgutil
import caps_dash

excluded = {_EXCLUDED_PREFIX!r}
for module_info in pkgutil.walk_packages(caps_dash.__path__, prefix="caps_dash."):
    name = module_info.name
    if name == excluded or name.startswith(excluded + "."):
        continue
    __import__(name)
"""


def test_importing_every_module_creates_nothing_in_an_empty_cwd(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("WEB_CONCURRENCY", None)  # must not trip the single-worker guard

    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, test-only subprocess
        [sys.executable, "-c", _IMPORT_EVERYTHING],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"importing every caps_dash module failed:\n{result.stdout}\n{result.stderr}"
    )
    created = list(tmp_path.iterdir())
    assert created == [], f"import created unexpected files/directories: {created}"
