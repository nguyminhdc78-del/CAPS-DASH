"""Building blocks for scripts/soak_test_setup.py: seeding, launching the
server, and holding one WebSocket viewer open. Split out of the setup script
purely to respect this project's 200-line file cap - see that module's
docstring for what a soak test is actually for and how to read its output.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

ADMIN_USERNAME = "soak-admin"
ADMIN_PASSWORD = "soak-test-admin-password-not-for-production-use"  # noqa: S105


def seed_database(db_path: Path, camera_count: int) -> None:
    """One admin user (to open the WebSocket) and N fake, fast-polling cameras."""
    from caps_dash.db.engine_factory import create_db_engine
    from caps_dash.db.enums import UserRole
    from caps_dash.db.models import Base, Camera, User
    from caps_dash.db.session import create_session_factory
    from caps_dash.security.password_hasher import hash_password

    engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        session.add(
            User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                display_name="Soak Admin",
                role=UserRole.ADMIN,
            )
        )
        for index in range(camera_count):
            session.add(
                Camera(
                    code=f"SOAK-{index + 1}", source_type="fake", source_url="", poll_interval_s=1.0
                )
            )
        session.commit()
    engine.dispose()


def start_server(db_path: Path, work_dir: Path, port: int) -> subprocess.Popen[bytes]:
    env = dict(os.environ)
    env.pop("WEB_CONCURRENCY", None)  # must not trip the single-worker guard
    env.update(
        APP_ENV="dev",
        SECRET_KEY="soak-test-signing-key-0123456789ABCDEFGHIJK",  # noqa: S106
        DATABASE_URL=f"sqlite:///{db_path}",
        DETECTOR_BACKEND="fake",
        SPA_DIST_DIR=str(work_dir / "no-frontend"),
        BACKUP_DIR=str(work_dir / "backups"),
        LOG_JSON="true",
    )
    log_file = (work_dir / "server.log").open("wb")
    return subprocess.Popen(  # noqa: S603 - fixed argv, no shell, operator-run harness
        [
            sys.executable,
            "-m",
            "caps_dash.cli.main",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def wait_until_ready(port: int, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
            return
        except OSError:
            time.sleep(1)
    raise TimeoutError(f"server did not become reachable on port {port} within {timeout_s}s")


async def hold_one_viewer_open(port: int, camera_id: int, stop: asyncio.Event) -> None:
    """Log in, open the camera stream, and just keep draining frames.

    Standing in for the one browser live-view tab the original plan calls
    for; a real browser is not available inside a headless harness like this
    one, but the traffic pattern that matters (one persistent authenticated
    subscriber pulling frames) is the same either way.
    """
    import websockets

    login_body = json.dumps({"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/auth/login",
        data=login_body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        token = json.loads(response.read())["access_token"]

    uri = f"ws://127.0.0.1:{port}/ws/cameras/{camera_id}"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({"type": "auth", "token": token}))
        while not stop.is_set():
            try:
                await asyncio.wait_for(websocket.recv(), timeout=5)
            except TimeoutError:
                continue


def sample_rss_kb(pid: int) -> int | None:
    """Resident set size in KiB, via `ps` - Linux/macOS only.

    No `psutil` dependency: this project does not otherwise need one, and
    the one platform this script actually has to work on is the deployment
    target's own family (Linux), where `ps -o rss=` is always present.
    """
    try:
        # "ps" resolved via PATH deliberately - it is a standard system tool,
        # not something this project ships or pins a location for.
        result = subprocess.run(  # noqa: S603
            ["ps", "-o", "rss=", "-p", str(pid)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = result.stdout.strip()
    return int(text) if text.isdigit() else None
