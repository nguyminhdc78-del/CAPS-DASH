# Codebase Summary

Module map with originating phase. All Python packages follow `snake_case`; all JavaScript modules follow `kebab-case` except `*.config.js` files.

## Backend: `backend/caps_dash/`

| Package | Purpose | Phase |
|---------|---------|-------|
| `config/` | Settings loader from env; validation; prod safety gates | 01 |
| `observability/` | Structured logging (structlog), request-id correlation, ASGI middleware | 01 |
| `errors/` | Error codes (never renamed or reused), exception hierarchy, response envelope | 01 |
| `db/` | SQLAlchemy models (User, Camera, Slot, History, Alert, AuditLog), migrations (Alembic), session lifecycle | 02 |
| `domain/` | Pure Python geometry, vote filter, state machine — no third-party imports | 04 |
| `vision/` | Detector backends (ONNX, ultralytics, fake), frame sources (HTTP snapshot, MJPEG stream, RTSP, folder, video, fake) | 05 |
| `security/` | Auth (JWT, refresh tokens, per-device sessions), RBAC, rate limiting | 03 |
| `services/` | Business logic: camera, slot, user, audit, history, stats, alert, system operations | 07 |
| `api/` | FastAPI routers (34 endpoints), request/response schemas, OpenAPI spec generation | 07 |
| `realtime/` | WebSocket hub, framing (`[len][header][JPEG]`), authentication, heartbeat | 08 |
| `web/` | SPA static mount at `/` | 01 |
| `workers/` | Camera supervisor, loop runtime, hot reload for polygon changes | 06 |

### `workers/` — the per-tick split

| Module | Responsibility |
|---|---|
| `camera_supervisor.py` | One asyncio task per enabled camera; restart with backoff; reconcile against the DB |
| `camera_start_stagger.py` | Pure arithmetic: how long each camera waits before its first tick, so N loops do not fire together |
| `camera_loop.py` | The tick — read, publish, decide, start a detection without awaiting it |
| `frame_publisher.py` | Encodes frame + state as one binary message and hands it to the hub |
| `inference_scheduler.py` | At most one in-flight detection per camera; invalidates results across a config reload |
| `inference_outcome_applier.py` | Applies a detection result once it lands: vote filter, state diff, DB write |
| `camera_tick_policy.py` | The change gate and the health-touch interval |
| `camera_metrics.py` | Per-camera counters; `average_process_ms` is averaged over detector runs, not ticks |
| `jobs/` | Background: aggregation, overstay/disk alerts, retention purge, rate-limit sweep | 13 |
| `cli/` | CLI: `serve` (with reload flag), `migrate` (runs at deploy, never at startup) | 01 |

## Frontend: `frontend/src/`

| Directory | Purpose | Phase |
|-----------|---------|-------|
| `app/` | Route definitions (one array drives router and sidebar); `layout.tsx` | 09 |
| `core/` | Queries (React Query), auth (login/logout/refresh), role ranking | 09 |
| `features/` | Pages: dashboard, slots, cameras, live view, ROI editor, history, stats, alerts, users, system | 09–13 |
| `shared/` | UI atoms: buttons, forms, tables, locale provider, state-tag component | 09 |
| `i18n/` | Locale files (VI/EN); bilingual copy rules (VI default) | 09 |

## Data: `data/`

| Item | Purpose |
|------|---------|
| `caps.db` | SQLite 3, live and backup targets | 02 |
| `backups/` | Incremental `.backup()` files; retained per `backup_keep_count` | 13 |
| `models/` | ONNX weights committed to repo; copied into image at build; never fetched at runtime | 05 |

## CI/CD: `.github/workflows/`

| Workflow | Trigger | Gates | Phase |
|----------|---------|-------|-------|
| `ci.yml` | push/PR | ruff → mypy → pytest (cov gates) → npm ci → tsc → oxlint → vitest → build | 14 |
| `docker.yml` | push to main, tags | multi-arch image build (arm64 for Arduino UNO Q) | 14 |

## Testing

| Suite | Scope | Coverage | Phase |
|-------|-------|----------|-------|
| `tests/unit/` | domain, geometry, vote, codec, security | 100% (domain), ≥90% (security) | Each |
| `tests/integration/` | API + temp DB | ≥80% (backend) | Each |
| `tests/workers/` | Camera loop, reload, shutdown | Graceful SIGTERM, no leaks | 14 |
| `tests/e2e/` | smoke: login → camera → WS stream → cleanup | ≥60% (frontend) | 14 |

## Infrastructure

| Item | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage: node build SPA → slim arm64 runtime, non-root user, healthcheck | 14 |
| `docker-compose.yml` | One service; named volume for `data/`; read-only mount for `models/` | 14 |
| `deploy/` | systemd unit (one worker), entrypoint (migrate then exec), env example, nginx example | 14 |
| `scripts/` | Dev loop: `.ps1` and `.sh` pairs (Windows/Linux); check-all gate script | 14 |

## Documentation

| File | Audience | Phase |
|------|----------|-------|
| `README.md` | Users; quickstart, architecture, licence | 14 |
| `project-overview-pdr.md` | Stakeholders; problem, users, scope, privacy | 14 |
| `system-architecture.md` | Developers; physical flow, concurrency model, framing spec, data model | 14 |
| `code-standards.md` | Developers; naming, file size, sync vs async, error contracts | 14 |
| `design-guidelines.md` | Frontend devs; tokens, colors, copy, accessibility | 14 |
| `deployment-guide.md` | Ops; install, Docker, systemd, secrets, backup, migration | 14 |
| `project-roadmap.md` | Team; 14 phases, future work (deferred) | 14 |
| `project-changelog.md` | Users; version history | 14 |

## Key Design Constraints

- **One worker**: N workers = N loops per camera, N vote filters, N SQLite writers → incorrect results.
- **Sync handlers**: REST routes are `def`, not `async def`; event loop stays available for workers and WebSocket tasks.
- **UNKNOWN ≠ FREE**: Before vote filter consensus, occupancy is unknown, not free.
- **Camera images never encoded by server**: ESP32 JPEG passed through; overlays drawn client-side.
- **No module-global mutable state**: Everything lives in `AppState` (lifespan-scoped).
- **ONNX at runtime, ultralytics dev-only**: Runtime is Apache-2.0 compatible; AGPL confined to export step.
