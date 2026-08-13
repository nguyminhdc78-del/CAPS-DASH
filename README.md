# CAPS-DASH — Car-Park Administration Dashboard

**Automated occupancy detection for parking facilities.** One FastAPI server runs the AI detection loop, serves a React dashboard, and streams live camera feeds. Images never leave the building.

Qualcomm Hack Challenge 2026 · Nhóm Mặt Trời Nhỏ

---

## What It Is

```
MaixCam (ceiling)
    ↓ one JPEG per GET /snapshot, polled every 2 s
CAPS-DASH Server
    ├─ YOLO v8 inference (onnxruntime)
    ├─ N-of-M vote filter (suppress noise)
    ├─ REST API (34 endpoints)
    ├─ WebSocket live stream (framed JPEG + state)
    └─ SQLite (config, history, audit)
    ↓
Browser Dashboard (React + Ant Design)
    ├─ Resident: free slot counts (privacy-preserving)
    ├─ Security: live camera view, alerts, audit trail
    └─ Admin: camera config, ROI polygons, backups
```

**Three user tiers**: resident (authenticated, read counts only) < security (live view + alerts, search by plate) < admin (full control).

**Public surface**: `/kiosk` is unauthenticated (no login). It shows free bay codes and allows partial-match licence-plate search, both behind a rate limit and kill-switch. See [Privacy Position](docs/project-overview-pdr.md#privacy-position) for the trade-off.

**Privacy**: Camera images are processed and discarded locally; no images leave the building. The authenticated dashboard ensures residents never see which slot is occupied. The public kiosk deliberately shows which bay is free and allows plate search.

## Quick Start

### Windows Development

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
cp .env.example .env
# Edit .env: set SECRET_KEY to any string (dev only)

# Terminal 1: Backend
scripts\dev-backend.ps1

# Terminal 2: Frontend
cd frontend && npm install && npm run dev

# Browser: http://localhost:5173 (Vite dev server)
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### Linux Production (Docker)

```bash
git clone <repo> /opt/caps-dash
cd /opt/caps-dash

cp deploy/caps-dash.env.example /etc/caps-dash/caps-dash.env
# Edit /etc/caps-dash/caps-dash.env:
#   SECRET_KEY = <generated 48-byte secret>
#   CORS_ORIGINS = https://parking.local
#   APP_ENV = prod

docker compose up -d

# Wait for migrations and app startup (10 s)
curl http://localhost:8000/api/health
```

**Create admin account** (first login):
- Username: `admin` · Password: `change-me` (change immediately in UI).
- Add cameras, draw slot polygons, set thresholds.

### Linux Production (Systemd)

See [`docs/deployment-guide.md`](docs/deployment-guide.md) for manual installation.

## Two Things Worth Knowing

### 1. **One Worker Only**

The app runs with exactly one uvicorn worker (hardcoded in Dockerfile, systemd, and enforced at startup). This is not a default; it is a correctness requirement.

**Why?** N workers = N camera loops per camera, N vote filters disagreeing about the same slot, N writers contending on one SQLite file. The vote filter becomes an oracle of conflicting opinions. Incorrect results.

**Encoded in**: CLI, Dockerfile CMD, systemd ExecStart, and a runtime guard that refuses to start if `WEB_CONCURRENCY` > 1 in prod.

### 2. **UNKNOWN ≠ FREE**

Until the vote filter has seen a full window of frames, the system does not know if a slot is occupied. It reports `UNKNOWN`, not `FREE`.

**Why?** Reporting it as free sends a driver to a space nobody has actually looked at. Transient misdetections (hand, shadow, bird) are filtered by voting; until consensus is reached, the slot is unknown.

**Rule**: Never add UNKNOWN counts to FREE counts. Show three separate numbers: "X free • Y occupied • Z unknown".

---

## Architecture (10-Line Summary)

One Linux process (arm64 for Arduino UNO Q) runs:
- **Event loop** (async): Manages N concurrent camera tasks + WebSocket subscribers.
- **Camera task** (per enabled camera): Polls the camera over HTTP (2 s interval), downloads one JPEG, publishes it, then starts a detection without waiting for it. Cameras start staggered across the interval so they do not all queue on the single inference worker at once. RTSP is still supported for IP cameras.
- **Inference pool** (1 worker, thread): Runs YOLO v8 on CPU-bound ONNX session; blocks event loop briefly.
- **DB-write pool** (1 worker, thread): Serializes all SQLite writes (only one connection anyway).
- **REST API** (sync handlers): Read/write via SQLAlchemy ORM; never async (lets event loop time-slice).
- **WebSocket hub**: Fan-out live frames to up to 16 concurrent viewers (4 per camera max).
- **Background jobs** (5 scheduled): Aggregation, overstay alerts, disk alerts, retention purge, rate-limit sweep.

**Data**: SQLite 3 (8 tables, 6-month retention, backups via online snapshot).

**Frontend**: React 19 + TypeScript (strict) + Ant Design v6, bilingual (VI default, EN provided).

---

## Layout

```
backend/caps_dash/
├── config/          Settings validation; prod safety gates
├── db/              SQLAlchemy ORM models, migrations (Alembic)
├── domain/          Pure Python: geometry, voting, state machine (no 3rd-party imports)
├── vision/          Detector backends (ONNX, ultralytics, fake), frame sources
├── security/        JWT auth, RBAC (3 roles), rate limiting, session management
├── services/        Business logic layer
├── api/             FastAPI routers (34 endpoints) + request/response schemas
├── realtime/        WebSocket hub, binary framing, heartbeat
├── workers/         Camera supervisor, loop runtime, hot reload
├── jobs/            Background jobs (aggregation, alerts, retention, cleanup)
├── observability/   Structured logging, request-id middleware
├── errors/          Error codes, exception hierarchy, envelope contract
├── web/             SPA static mount
└── cli/             Command-line interface

frontend/src/
├── app/             Route definitions, layout
├── core/            Queries (React Query), auth, role checking
├── features/        Pages (dashboard, cameras, live, ROI, history, stats, alerts, users, system)
├── shared/          UI atoms, state-tag component, locale provider
└── i18n/            Locale files (vi.json, en.json)

tests/               Unit, integration, worker, E2E (coverage gates: domain 100%, security 90%, backend 80%, frontend 60%)

docs/                Architecture, standards, deployment, roadmap, changelog
```

**Key rule**: `domain/` imports nothing outside the standard library. That is what makes it testable without hardware and portable to constrained devices.

---

## Features

### For Residents (Authenticated Dashboard)
- **Real-time counts**: Free slot counts per floor (read-only).
- **History**: 7-day occupancy trend chart.
- **Privacy**: Never sees which slot holds which car.

### For Customers (Public Lobby Kiosk — Unauthenticated)
- **Free bay codes**: List of unoccupied spaces per floor (no login needed).
- **Plate search**: Find your car by licence plate (partial match, rate-limited, behind a kill-switch).
- **Audit**: Every search is logged anonymously with client IP for rate limiting.

### For Security
- **Live view**: Camera stream with detected boxes overlaid; ROI polygons visible.
- **Alerts**: Offline cameras, vehicles overstayed > 12h, low disk space.
- **Audit trail**: Who logged in, when cameras were added/modified.

### For Administrators
- **Camera management**: Add, edit, delete; per-camera tuning (poll interval, vote threshold, confidence).
- **ROI editor**: Draw and redraw parking-slot polygons in the browser; changes apply without restart (hot reload).
- **Backup/restore**: SQLite online backup; restore from any backup file.
- **Data retention**: Purge occupancy history older than 6 months (tunable per site).
- **System operations**: Monitor disk space, check system health, view logs.

---

## API Surface

**34 endpoints** covering cameras, slots, history, statistics, alerts, audit, system operations.

### Sample Endpoints
```
GET  /api/health
POST /api/auth/login
GET  /api/cameras
POST /api/cameras
GET  /api/cameras/{id}/slot-map
PUT  /api/cameras/{id}/slot-map (triggers hot reload)
GET  /api/slots/current
GET  /api/summary
GET  /api/history?start_date=2026-08-01&end_date=2026-08-11
GET  /api/history/export.csv
POST /api/alerts/acknowledge/{id}
GET  /api/system/backup
POST /api/system/restore
```

**WebSocket**: `GET /ws/cameras/{id}` — Live frames (binary: `[header_len][JSON state][JPEG]`), heartbeat, 4 viewers per camera max.

Full OpenAPI spec at `/openapi.json` (dev only; disabled in prod).

---

## Dependencies & Licences

### Runtime (Deployed)
- **Apache-2.0**: onnxruntime (vehicle detection inference).
- **MIT**: FastAPI, Pydantic, SQLAlchemy, React, Ant Design, Vite, and others.

### Development-Only (Never Deployed)
- **AGPL-3.0**: ultralytics — used only to export the ONNX model on a dev machine, then discarded.

Install dev dependencies with:
```bash
pip install -e ".[dev,vision-dev]"
```

Production image contains no AGPL code (CI asserts this).

---

## Testing & CI

### Test Suites
- **Unit**: Domain logic, geometry, voting, security (100% domain, ≥90% security).
- **Integration**: API endpoints + temp SQLite DB.
- **Worker**: Camera loop end-to-end, hot reload, graceful shutdown.
- **E2E Smoke**: Login → camera creation → state change → WS frame → clean exit.

### Run Locally
```bash
# Python
pytest              # All tests
pytest --cov        # Coverage report

# JavaScript
npm run test        # Vitest
npm run test:coverage   # Coverage

# All checks
scripts/check-all.ps1  # Windows
scripts/check-all.sh   # Linux (ruff → mypy → pytest → npm checks → build)
```

### CI/CD
GitHub Actions: `ruff lint` → `mypy` → `pytest --cov` → `npm ci` → `tsc` → `oxlint` → `vitest` → `npm run build` → `docker build`.
- Total runtime: < 10 min.
- Coverage gates enforced (domain, security, backend, frontend).
- Assertions: no ultralytics in `pip freeze`, no `.onnx` tracked in git, prod config rejects wildcard CORS.
- Multi-architecture Docker build (arm64 for Arduino UNO Q).

---

## Deployment

### Target: Arduino UNO Q (aarch64 Linux, glibc 2.28+)

**Docker** (recommended):
```bash
docker compose up -d
```

**Systemd**:
```bash
sudo systemctl start caps-dash
```

**Environment**: All configuration via env vars; `.env.example` is the contract.

See [`docs/deployment-guide.md`](docs/deployment-guide.md) for:
- Detailed installation (manual, systemd, Docker).
- Environment variable reference.
- Backup & restore procedures.
- Reverse proxy (nginx) configuration.
- Upgrading and migrations.
- Soak-test procedure (8h, measure memory growth).

---

## Configuration

Copy `.env.example` to `.env` (dev) or `/etc/caps-dash/caps-dash.env` (prod) and adjust:

```bash
# Core
APP_ENV=prod                                    # dev or prod
SECRET_KEY=<48-byte-random-secret>              # Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
CORS_ORIGINS=https://parking.local              # Comma-separated; prod rejects "*" or empty

# Storage
DATABASE_URL=sqlite:////var/lib/caps-dash/caps.db
BACKUP_DIR=/var/backups/caps-dash
RETENTION_MONTHS=6

# Vision
DETECTOR_BACKEND=onnx                           # onnx, ultralytics (dev), fake (testing)
INFERENCE_POOL_SIZE=1                           # MUST be 1 (correctness constraint)
DETECTOR_CONFIDENCE=0.25                        # YOLO threshold (0–1)
DEFAULT_POLL_INTERVAL_S=3.0                     # Camera poll cadence

# Alerts
OVERSTAY_HOURS=12.0
DISK_LOW_PERCENT=0.10
```

See [`docs/deployment-guide.md`](docs/deployment-guide.md) for the full reference.

---

## Documentation

| Document | Audience | Purpose |
|----------|----------|---------|
| [`docs/project-overview-pdr.md`](docs/project-overview-pdr.md) | Stakeholders | Problem statement, users, scope, privacy, success criteria, non-goals |
| [`docs/system-architecture.md`](docs/system-architecture.md) | Developers | Physical flow, process model, concurrency, framing spec, data model, hot reload |
| [`docs/code-standards.md`](docs/code-standards.md) | Developers | Naming, file size, sync/async rules, error contracts, testing strategy |
| [`docs/design-guidelines.md`](docs/design-guidelines.md) | Frontend devs | Ant Design tokens, colors, bilingual copy, accessibility, responsive layout |
| [`docs/deployment-guide.md`](docs/deployment-guide.md) | Operators | Install, configure, backup, restore, upgrade, soak test, troubleshooting |
| [`docs/codebase-summary.md`](docs/codebase-summary.md) | Developers | Module map, originating phases, key constraints |
| [`docs/project-roadmap.md`](docs/project-roadmap.md) | Team | 14 phases, status, effort, critical path, future work (deferred) |
| [`docs/project-changelog.md`](docs/project-changelog.md) | Users | Release notes, features, known limitations |

---

## Performance & Capacity

**Measured on the target board** (Arduino UNO Q, aarch64, 4 cores): a median
616 ms per inference at 640x640. Inference is serialised, so the default 3 s
poll supports roughly three cameras with headroom; six needs a 5 s poll. See
`docs/deployment-guide.md`.

**The live view is 1 frame every 2 seconds** on a polled camera. That is
intended, not a fault: the poll interval is both the live-view frame rate and
the inference cadence, and 2 s is what the camera and the detector budget
together support. Three cameras × 616 ms is 1.85 s against a 2.0 s tick — tight
enough that if a measurement on the board shows it does not fit, the response
is to *raise* the tick to 2.5–3.0 s, which slows the live view with it.

No end-to-end soak test has been run, and no accuracy figure has been measured.

**Limits**:
- Up to 4 WebSocket viewers per camera, 16 total concurrent.
- One YOLO inference at a time (one model in memory).
- One SQLite writer (single thread serializes all writes).

**Unmeasured on Target** (Arduino UNO Q):
- Latency (frame capture → state change visible).
- CPU and memory usage (baseline and under load).
- Storage growth rate.
- Image size post-build.

All figures to be recorded after soak test (phase 14, step 13).

**To scale beyond 6 cameras**: Split into a multi-process architecture (future work). Capture worker → queue → inference workers → single DB writer.

---

## Troubleshooting

### App won't start
- Check logs: `docker compose logs app` or `journalctl -u caps-dash`.
- Prod validates strictly; invalid `SECRET_KEY`? Generate a new one.
- Port 8000 in use? `ss -tlnp | grep 8000`.

### Camera offline
- Network reachable? `curl http://<camera-ip>:8080/snapshot` (a MaixCam answers
  `503` rather than a stale frame if its capture thread has stopped).
- Source URL correct in the UI?
- Check camera `last_error` field.

### WebSocket not streaming
- Browser console errors?
- Nginx reverse proxy: `Upgrade` and `Connection` headers set?
- Firewall blocking WebSocket traffic?

### Disk filling up
- Check backup directory size: `du -sh /var/backups/caps-dash/`.
- Delete old backups manually or trigger admin backup (respects `BACKUP_KEEP_COUNT`).
- Purge old data: Admin → System → Purge (delete records older than retention window).

See [`docs/deployment-guide.md`](docs/deployment-guide.md) for detailed troubleshooting.

---

## Contributing

All work in branches. CI must pass before merging to main:
```bash
scripts/check-all.ps1  # Windows dev
scripts/check-all.sh   # Linux dev
```

Follow [`docs/code-standards.md`](docs/code-standards.md) (naming, file size, testing).

Conventional commit format: `feat(scope): subject`, `fix(scope): subject`, etc.

---

## Licence

**Source**: Published as a condition of the Qualcomm Hack Challenge 2026.

**Runtime**: Apache-2.0 compatible (onnxruntime Apache-2.0, all other deps MIT or similar).

**Development-only**: ultralytics AGPL-3.0 (used only to export ONNX model; never deployed).

---

## Support

- Check logs: Always the first step.
- Backup before manual DB intervention; restore if unsure.
- All configuration is environment-based; no secrets baked into code.
- Issues or questions: See the documentation tree above.

---

**Last updated**: 2026-08-11 · Phase 14 (Testing, CI, Packaging & Docs) complete.
