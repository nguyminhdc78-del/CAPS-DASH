# Runs the same gate chain as .github/workflows/ci.yml, locally, so a
# developer sees exactly what CI would catch before pushing. Mirrors
# scripts/check-all.sh - keep both in sync; CI itself runs the .sh path.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

Write-Output '==> ruff'
& $python -m ruff check backend tests
if ($LASTEXITCODE -ne 0) { throw 'ruff failed' }

Write-Output '==> mypy'
& $python -m mypy backend
if ($LASTEXITCODE -ne 0) { throw 'mypy failed' }

Write-Output '==> pytest (with coverage)'
& $python -m pytest --cov=caps_dash --cov-report=term-missing
if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }

Set-Location (Join-Path $repoRoot 'frontend')

Write-Output '==> npm ci'
npm ci
if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }

Write-Output '==> frontend typecheck'
npm run typecheck
if ($LASTEXITCODE -ne 0) { throw 'frontend typecheck failed' }

Write-Output '==> frontend lint'
npm run lint
if ($LASTEXITCODE -ne 0) { throw 'frontend lint failed' }

Write-Output '==> frontend test'
npm run test
if ($LASTEXITCODE -ne 0) { throw 'frontend test failed' }

Write-Output '==> frontend build'
npm run build
if ($LASTEXITCODE -ne 0) { throw 'frontend build failed' }

Set-Location $repoRoot
Write-Output 'All checks passed.'
