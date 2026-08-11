# Regenerate the frontend's API types from the backend contract.
#
# Two steps, in this order: refresh docs/openapi.json from the app, then
# generate TypeScript from that file. Generating from the committed document
# rather than from a running server means this works offline, in CI, and
# without a database.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

& $python scripts/dump_openapi_snapshot.py
if ($LASTEXITCODE -ne 0) { throw 'failed to dump the OpenAPI snapshot' }

Set-Location (Join-Path $repoRoot 'frontend')
npx openapi-typescript ../docs/openapi.json -o src/core/types/api-schema.d.ts
if ($LASTEXITCODE -ne 0) { throw 'openapi-typescript failed' }

Write-Output 'wrote frontend/src/core/types/api-schema.d.ts'
