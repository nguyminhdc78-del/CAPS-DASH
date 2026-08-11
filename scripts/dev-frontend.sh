#!/usr/bin/env bash
# Local dev loop for the frontend: install if needed, then start Vite.
# Mirrors scripts/dev-frontend.ps1 - keep both in sync.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root/frontend"

if [ ! -d node_modules ]; then
    echo "node_modules missing - running npm install..."
    npm install
fi

echo "Starting the Vite dev server on http://localhost:5173 - run scripts/dev-backend.sh in another terminal for the API on :8000."
npm run dev
