#!/bin/sh
# Docker `HEALTHCHECK CMD` and docker-compose's `healthcheck:` block both
# shell out to this one script rather than duplicating the check.
#
# Hits /api/health/ready, not /api/health: liveness ("the process is up")
# would report healthy even when the app cannot reach its own database -
# see `api/routes/health_routes.py` for why the two are split. python3, not
# curl: the runtime image deliberately never installs curl (one less
# package in a security-adjacent container), and python3 is already there
# because the app is.
set -eu

port="${PORT:-8000}"

python3 - "$port" <<'PYEOF'
import json
import sys
import urllib.request

port = sys.argv[1]
url = f"http://127.0.0.1:{port}/api/health/ready"

with urllib.request.urlopen(url, timeout=4) as response:
    ok = response.status == 200
    body = json.loads(response.read())

if not ok or not body.get("ready", False):
    raise SystemExit(1)
PYEOF
