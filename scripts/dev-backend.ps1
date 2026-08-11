# Local dev loop for the backend: check the venv, bootstrap .env, migrate,
# then serve with autoreload. Mirrors scripts/dev-backend.sh - keep both in
# sync; Windows is a supported development environment even though the
# deployment target is Linux only.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "No .venv found at $python - run: python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
}

$envFile = Join-Path $repoRoot '.env'
if (-not (Test-Path $envFile)) {
    Write-Output 'No .env found - copying .env.example (edit SECRET_KEY before using this for anything but a quick local check).'
    Copy-Item (Join-Path $repoRoot '.env.example') $envFile
}

Write-Output 'Applying migrations...'
& $python -m caps_dash.cli.main migrate
if ($LASTEXITCODE -ne 0) { throw 'migration failed' }

Write-Output 'Starting the API with autoreload on http://127.0.0.1:8000 ...'
& $python -m caps_dash.cli.main serve --reload
