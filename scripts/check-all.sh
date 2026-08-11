#!/usr/bin/env bash
# Runs the same gate chain as .github/workflows/ci.yml, locally. Mirrors
# scripts/check-all.ps1 - keep both in sync; CI runs this .sh path.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python="${PYTHON:-.venv/bin/python}"
[ -x "$python" ] || python="python3"

echo "==> ruff"
"$python" -m ruff check backend tests

echo "==> mypy"
"$python" -m mypy backend

echo "==> pytest (with coverage)"
"$python" -m pytest --cov=caps_dash --cov-report=term-missing

cd frontend

echo "==> npm ci"
npm ci

echo "==> frontend typecheck"
npm run typecheck

echo "==> frontend lint"
npm run lint

echo "==> frontend test"
npm run test

echo "==> frontend build"
npm run build

cd "$repo_root"
echo "All checks passed."
