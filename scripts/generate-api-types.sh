#!/usr/bin/env bash
# Regenerate the frontend's API types from the backend contract.
#
# Two steps, in this order: refresh docs/openapi.json from the app, then
# generate TypeScript from that file. Generating from the committed document
# rather than from a running server means this works offline, in CI, and
# without a database.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python="${PYTHON:-.venv/bin/python}"
[ -x "$python" ] || python="python3"

"$python" scripts/dump_openapi_snapshot.py

cd frontend
npx openapi-typescript ../docs/openapi.json -o src/core/types/api-schema.d.ts
echo "wrote frontend/src/core/types/api-schema.d.ts"
