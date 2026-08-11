# Local dev loop for the frontend: install if needed, then start Vite.
# Mirrors scripts/dev-frontend.sh - keep both in sync.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $repoRoot 'frontend')

if (-not (Test-Path 'node_modules')) {
    Write-Output 'node_modules missing - running npm install...'
    npm install
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
}

Write-Output 'Starting the Vite dev server on http://localhost:5173 - run scripts/dev-backend.ps1 in another terminal for the API on :8000.'
npm run dev
