"""Watch one camera's slot states live, and time how long a change takes to land.

Run it, then move a car. It prints every state change with the seconds since
the previous one, so "I took the car out and it still says occupied" becomes a
number instead of an impression.

    python scripts/watch-slot-transitions.py <host> <camera_id> <username>

The password is read from the CAPS_PASSWORD environment variable, or prompted
for, so it never lands in shell history.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import sys
import time
import urllib.request

try:
    import websockets
except ImportError:  # pragma: no cover - a dev machine without the extra
    sys.exit("pip install websockets")

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.137.37:8000"
CAMERA_ID = sys.argv[2] if len(sys.argv) > 2 else "1"
USERNAME = sys.argv[3] if len(sys.argv) > 3 else "admin"


def login(password: str) -> str:
    request = urllib.request.Request(f"http://{HOST}/api/auth/login", method="POST")
    request.add_header("Content-Type", "application/json")
    body = json.dumps({"username": USERNAME, "password": password}).encode()
    # The URL is built from a host argument this operator typed, on their own
    # LAN, to their own dashboard - not from anything untrusted.
    with urllib.request.urlopen(request, body, timeout=20) as response:  # noqa: S310
        return str(json.loads(response.read())["access_token"])


async def main() -> None:
    password = os.environ.get("CAPS_PASSWORD") or getpass.getpass("password: ")
    token = login(password)

    previous: dict[str, str] = {}
    changed_at = time.monotonic()
    print(f"watching camera {CAMERA_ID} on {HOST} - move a car and watch the timings\n")

    async with websockets.connect(f"ws://{HOST}/ws/cameras/{CAMERA_ID}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token}))
        while True:
            message = await ws.recv()
            if isinstance(message, str):
                continue
            header_len = int.from_bytes(message[:4], "big")
            header = json.loads(message[4:4 + header_len])
            states = {s["code"]: s["state"] for s in header.get("slots", [])}
            if not states or states == previous:
                continue

            now = time.monotonic()
            moved = [
                f"{code}: {previous.get(code, '-')} -> {state}"
                for code, state in states.items()
                if previous.get(code) != state
            ]
            gap = f"{now - changed_at:5.1f}s since last change" if previous else "initial"
            print(f"{gap:>26}   " + " | ".join(moved))
            previous, changed_at = states, now


if __name__ == "__main__":
    with __import__("contextlib").suppress(KeyboardInterrupt):
        asyncio.run(main())
