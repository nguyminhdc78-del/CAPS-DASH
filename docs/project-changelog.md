# Changelog

All notable changes to CAPS-DASH documented by release. Format follows [Conventional Commits](https://www.conventionalcommits.org/).

## [0.1.0] — 2026-08-11

Initial release. Greenfield implementation of the complete car-park administration dashboard.

### Added

**Core**
- FastAPI application with single uvicorn worker (correctness constraint).
- SQLite database with Alembic migrations (render_as_batch for portability).
- SQLAlchemy 2.0 ORM models: User, Camera, ParkingSlot, SlotStateHistory, HourlyStat, Alert, AuditLog, RefreshSession.
- Request ID correlation middleware for observability.
- Structured logging with structlog.

**Security & Auth**
- JWT authentication (HS256, 15-min access + 7-day refresh tokens).
- RBAC with three roles: resident, security, admin.
- Per-device session tracking with refresh-token rotation and reuse detection.
- Rate limiting on login attempts (5 attempts / 300 s).
- Session revocation and multi-device management.
- Audit log of all state-changing operations.

**Vision Pipeline**
- YOLO v8 vehicle detection via onnxruntime (Apache-2.0).
- Pluggable frame sources: ESP32-CAM (HTTP), image folder, video file, fake (for testing).
- Detector backends: ONNX (runtime), ultralytics (dev-only export), fake (testing).
- N-of-M vote filter to suppress noise in detections.
- Per-camera tuning: poll interval, vote window, confidence threshold.
- Occupancy state machine: UNKNOWN → FREE ↔ OCCUPIED.

**Camera Management**
- Create, read, update, delete cameras from the dashboard.
- Source URL configuration (network address or file path).
- Per-camera ROI polygon editing (hot reload without restart).
- Dead-camera isolation via consecutive-failure streak threshold.
- Snapshot caching (10s) for the ROI editor.

**REST API** (34 endpoints)
- `/health` — liveness probe.
- `/auth/*` — login, logout, refresh, session list/revoke.
- `/users/*` — create, read, update, disable users.
- `/cameras/*` — CRUD + test-connection + snapshot.
- `/cameras/{id}/slot-map` — ROI polygon get/update.
- `/slots/` — current occupancy by slot.
- `/summary/` — floor and site-level counts.
- `/history/` — time-range occupancy queries with CSV export.
- `/stats/` — derived occupancy statistics.
- `/alerts/` — camera offline, overstay, disk space, slot overlap, clock unsync.
- `/system/` — backup, restore, purge retention, version.
- OpenAPI spec at `/openapi.json` (dev only).

**Realtime**
- WebSocket endpoint `/ws/cameras/{id}` — live frames with 4 viewers/camera max, 16 total.
- Binary framing: `[4-byte BE header length][UTF-8 JSON header][JPEG bytes]` (atomic).
- Heartbeat every 20 s to detect dead connections.
- Cached first frame (30 s max age) for instant UI responsiveness.

**Background Jobs**
- Hourly aggregation: derive 1-hour occupancy statistics.
- Overstay detection: alert on vehicles > 12 hours (tunable).
- Disk space monitoring: alert at 10% free / 256 MiB (whichever hits first).
- Retention purge: delete events older than 6 months daily.
- Rate-limit sweep: expire sliding-window login attempt buckets hourly.

**Frontend**
- React 19 + TypeScript (strict) with Vite build.
- Ant Design v6 component library with theme tokens.
- Bilingual: Vietnamese default, English provided; all UI strings in locale files.
- Role-based access control (one route array drives both sidebar and router).
- Lazy loading of large dependencies (Konva for ROI editor).

**Frontend Pages**
- **Dashboard** — site and floor-level occupancy summary, kiosk view.
- **Slots** — detailed per-slot state with last-seen timestamp.
- **Cameras** — admin CRUD, source type, test-connection button.
- **Live View** — real-time frame stream with detected boxes and ROI overlay.
- **ROI Editor** — polygon drawing, per-camera tuning (poll, vote, confidence).
- **History** — date-range queries, CSV export, session derivation.
- **Statistics** — occupancy trends, peak hours, dwell-time distribution.
- **Alerts** — active and historical, with acknowledge action.
- **Users** — admin account management, audit log.
- **System** — backup/restore, retention purge, log access.

**Testing**
- Unit tests: domain logic (100%), security (≥90%), codec, geometry, vote filter.
- Integration tests: API endpoints against temp DB; fixtures for frames and history.
- Worker tests: camera loop end-to-end, hot reload, dead-camera isolation, graceful shutdown (SIGTERM).
- E2E smoke: login → create camera → observe state change → WS frame → clean exit.
- Coverage gates: domain 100%, security ≥90%, backend ≥80%, frontend ≥60%.

**CI/CD**
- GitHub Actions: ruff (lint) → mypy (types) → pytest (backend) → npm ci → tsc → oxlint → vitest (frontend) → npm run build.
- Assertions: no ultralytics in pip freeze, no `.onnx` tracked in git, prod config rejects wildcard CORS.
- Multi-architecture Docker build (arm64 for Arduino UNO Q).
- CI runs < 10 min.

**Deployment**
- Multi-stage Dockerfile: node build SPA → slim arm64 runtime, non-root user.
- Docker Compose with named volume and read-only model mount.
- systemd unit with single-worker guarantee, systemd hardening, graceful shutdown (20 s timeout).
- Environment-based configuration; no secrets in image.
- Online backup API (`.backup()`) produces valid databases for restore.
- Deployment target: aarch64 Linux (glibc 2.28+), e.g. Arduino UNO Q (QRB2210).

**Documentation**
- Architecture: physical flow, concurrency model, data model, WebSocket framing.
- Code standards: naming, file size caps, sync/async rules, error contracts, domain purity.
- Design guidelines: Ant Design tokens, slot-state colors, bilingual copy, accessibility.
- Deployment guide: Linux install, Docker, systemd, secrets, backup/restore, migration, soak test.
- Project roadmap: 14 phases with status; future work deferred.
- README: quickstart (Windows dev, Linux prod), layout tree, two key constraints.

### Known Limitations & Future Work

- **Performance unmeasured**: No latency, accuracy, or capacity numbers recorded until run on Arduino UNO Q.
- **No load test has been run**: the 1-6 camera figure is a design target, not a measured ceiling.
- **Licence-plate recognition**: Deferred; not part of current scope.
- **Smoke/fire detection**: Deferred; not part of current scope.
- **Multi-process architecture**: Deferred; one process, one worker. If horizontal scale needed in future, capture/inference would split into separate process fed by a queue.
- **QNN/NPU execution**: Deferred; QRB2210 NPU support unverified.

### Notes

- Ultralytics (AGPL-3.0) is a dev-only extra, never deployed. Runtime inference uses onnxruntime (Apache-2.0).
- ONNX weights are committed to the repo to avoid runtime fetch/manifest complexity.
- Source image encoding never performed by the server; JPEG passed through, overlays drawn client-side.
- `UNKNOWN` is a distinct state from `FREE`; consumers must never merge them.
- One uvicorn worker is a correctness constraint, not a default; encoded in CLI, Dockerfile, systemd.
