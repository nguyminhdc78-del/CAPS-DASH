#!/usr/bin/env bash
# Local dev loop for the backend: check the venv, bootstrap .env, migrate,
# then serve with autoreload. Mirrors scripts/dev-backend.ps1 - keep both in
# sync.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python="${PYTHON:-.venv/bin/python}"
if [ ! -x "$python" ]; then
    echo "No .venv found at $python - run: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
fi

if [ ! -f .env ]; then
    echo "No .env found - copying .env.example (edit SECRET_KEY before using this for anything but a quick local check)."
    cp .env.example .env
fi

echo "Applying migrations..."
"$python" -m caps_dash.cli.main migrate

echo "Starting the API with autoreload on http://127.0.0.1:8000 ..."
"$python" -m caps_dash.cli.main serve --reload
