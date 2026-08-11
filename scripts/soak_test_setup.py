"""Soak-test SETUP: N fake cameras, one persistent WebSocket viewer standing
in for a browser live-view tab, and RSS sampled on an interval to a CSV.

This SETS UP a soak run. It is not itself an 8-hour measurement, and no
number here is "the" soak-test result until someone actually runs it for the
real duration, on the real board, and records what came out in
docs/deployment-guide.md. This phase wrote the harness; it did not run it -
an unattended multi-hour run is outside what an implementation session can
honestly claim to have measured.

    python scripts/soak_test_setup.py --duration-s 28800 --cameras 4

Stop early with Ctrl+C - the server is still shut down cleanly and whatever
samples were collected so far remain in the CSV.

--- How to read the CSV afterwards -----------------------------------------
Plot (or eyeball) rss_kb against elapsed_s. A healthy run is flat, or a small
one-time step up (buffer pools warming, caches filling) that then plateaus.
The plan's bar is growth under 5% between the first and last sample.
Sustained, roughly linear growth across the WHOLE run - not a plateau - is
the signature of a real leak (an unclosed WebSocket subscriber, a growing
dict, an unbounded queue) and is worth a `tracemalloc` session before being
dismissed as noise.

Why a live viewer matters: the camera loop only encodes and publishes a
frame while someone is watching (see workers/camera_loop.py) - a soak with
nobody connected would never exercise the encode/broadcast path, which is
exactly the part most likely to leak a buffer or a stale subscriber
reference.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import time
from pathlib import Path

from soak_test_harness import (
    REPO_ROOT,
    hold_one_viewer_open,
    sample_rss_kb,
    seed_database,
    start_server,
    wait_until_ready,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-s", type=int, default=28_800, help="default: 8 hours")
    parser.add_argument("--cameras", type=int, default=4, help="default: 4, matching the soak plan")
    parser.add_argument("--sample-interval-s", type=int, default=300, help="default: 5 minutes")
    parser.add_argument("--port", type=int, default=18_400)
    parser.add_argument("--output-csv", type=Path, default=REPO_ROOT / "soak-rss.csv")
    return parser.parse_args()


async def _run(args: argparse.Namespace, work_dir: Path) -> None:
    db_path = work_dir / "soak.db"
    seed_database(db_path, args.cameras)

    server = start_server(db_path, work_dir, args.port)
    stop_viewer = asyncio.Event()
    viewer_task: asyncio.Task[None] | None = None
    try:
        wait_until_ready(args.port)
        # Camera id 1 - the seed above inserts cameras in order starting at 1
        # on a fresh database.
        viewer_task = asyncio.create_task(hold_one_viewer_open(args.port, 1, stop_viewer))

        args.output_csv.write_text("elapsed_s,rss_kb\n", encoding="utf-8")
        started = time.monotonic()
        end = started + args.duration_s
        print(
            f"sampling every {args.sample_interval_s}s for {args.duration_s}s "
            f"-> {args.output_csv}"
        )

        while time.monotonic() < end:
            if server.poll() is not None:
                log_path = work_dir / "server.log"
                print(f"server exited early (code {server.returncode}); see {log_path}")
                break
            rss_kb = sample_rss_kb(server.pid)
            elapsed = int(time.monotonic() - started)
            with args.output_csv.open("a", encoding="utf-8") as handle:
                handle.write(f"{elapsed},{rss_kb if rss_kb is not None else ''}\n")
            await asyncio.sleep(args.sample_interval_s)
    finally:
        stop_viewer.set()
        if viewer_task is not None:
            viewer_task.cancel()
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        print(f"server log: {work_dir / 'server.log'}")


def main() -> int:
    args = parse_args()
    work_dir = REPO_ROOT / ".soak-work"
    work_dir.mkdir(exist_ok=True)
    try:
        asyncio.run(_run(args, work_dir))
    except KeyboardInterrupt:
        print("stopped early by the operator")
    print(f"done. wrote {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
