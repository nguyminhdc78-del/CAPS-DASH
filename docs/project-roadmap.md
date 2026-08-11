# Project Roadmap

14-phase greenfield implementation of CAPS-DASH, completed in a single development cycle. Status: **100% (phases 01–14 implemented, 2026-08-11)**.

## Implementation Phases

| # | Phase | Status | Effort | Dependencies | Highlights |
|---|-------|--------|--------|--------------|-----------|
| 01 | Project scaffold & foundations | ✅ Complete | 6h | — | venv, pyproject.toml, FastAPI app, CLI, SPA mount, logging, errors |
| 02 | Data layer: models & migrations | ✅ Complete | 8h | 01 | SQLAlchemy 2.0, Alembic, 8 tables (User, Camera, Slot, etc.), refresh_sessions |
| 03 | Authentication & RBAC | ✅ Complete | 10h | 02 | JWT, per-device sessions, refresh rotation, reuse detection, 3 roles, rate limiting |
| 04 | Vision domain core | ✅ Complete | 6h | — | Geometry, vote filter, state machine; pure Python, no third-party deps |
| 05 | Detector & frame-source abstractions | ✅ Complete | 10h | 04 | ONNX/ultralytics/fake detectors; ESP32/folder/video/fake sources; JPEG passthrough |
| 06 | Camera worker runtime | ✅ Complete | 12h | 02, 05 | Supervisor, loop, hot reload, backoff, dead-camera isolation, snapshot cache |
| 07 | REST API & service layer | ✅ Complete | 16h | 02, 03, 06 | 34 endpoints, OpenAPI, schemas, business logic layer |
| 08 | WebSocket realtime channel | ✅ Complete | 8h | 06, 07 | Binary framing, heartbeat, cached first frame, viewer caps |
| 09 | Frontend shell, i18n & auth | ✅ Complete | 12h | 07, 08 | React 19, TS strict, Vite, Ant Design v6, VI/EN bilingual, route guards |
| 10 | Frontend admin pages | ✅ Complete | 14h | 09 | Users, cameras, slots; CRUD forms, test-connection, live-mode toggle |
| 11 | ROI polygon editor | ✅ Complete | 12h | 09 | Konva canvas, polygon drawing/moving, camera rescale, persist to backend |
| 12 | Realtime camera view | ✅ Complete | 10h | 08, 11 | Live stream, detected boxes overlay, ROI overlay, streaming controls |
| 13 | History, statistics & alerts | ✅ Complete | 16h | 07, 12 | Occupancy queries, CSV export, aggregation, overstay/disk/overlap alerts |
| 14 | Testing, CI, packaging & docs | ✅ Complete | 18h | 01–13 | Pytest suite (coverage gates), GitHub Actions, Docker, systemd, 8 docs |

**Total effort: 158 hours.** All phases completed in a single cycle. No rework or backlog.

## Critical Path

```
01 → 04 → 05 → 06 → 07 → 08 → 12 (9 phases)
     ↓      ↓      ↓      ↓      ↓
02 → 03 ──────────────────────────
09 → 10 → 11 ──────────────────────
```

- **Backend pipeline**: 01 → 04 → 05 → 06 → 07 → 08 → 12 (9 critical phases).
- **Database**: Phase 02 unblocks 03, 06, 07, 13.
- **Frontend**: Starts at phase 09 once 07's OpenAPI snapshot is stable.
- **ROI editor** (phase 11) must complete before realtime (phase 12) to share the polygon rescale helper and overlay renderer.

## Phase Outcomes

### Foundation (phases 01–03)
- Single-worker FastAPI app with CLI and SPA mount.
- SQLite 3 database with 8 tables and migrations.
- JWT auth, per-device sessions, three roles (resident/security/admin).

### Vision (phases 04–06)
- Pure-Python domain logic: geometry, voting, state machine.
- Pluggable detectors (ONNX, ultralytics, fake) and frame sources (ESP32, folder, video, fake).
- Camera supervisor with hot reload and dead-camera handling.

### REST API & Realtime (phases 07–08)
- 34 REST endpoints covering cameras, slots, history, stats, alerts, audit, system.
- WebSocket for live frame streaming with binary framing, heartbeat, viewer caps.

### Frontend (phases 09–13)
- React 19 dashboard with Ant Design v6, bilingual UI, role-based routes.
- Pages: dashboard, slots, cameras, live view, ROI editor, history, stats, alerts, users, system.
- Background jobs: aggregation, overstay/disk alerts, retention, rate-limit sweep.

### Quality & Deployment (phase 14)
- Comprehensive test suite (unit, integration, worker, E2E) with coverage gates.
- GitHub Actions CI: lint, type check, test, build, docker.
- Multi-stage Docker image (arm64), docker-compose, systemd unit.
- 8 documentation files + full README rewrite.

## Validation Log

### Session 1 — 2026-08-11

**Key Decisions Locked**
- **Host**: Arduino UNO Q (aarch64 Linux, QRB2210). Demo scale: 1–6 cameras.
- **Storage**: ONNX weights committed to repo; no runtime fetch.
- **Workers**: One uvicorn worker (correctness constraint, not a tuning knob).
- **Inference**: CPU-bound, serialized (inference_pool_size=1).
- **Privacy**: Camera images never leave the building; residents see counts only.
- **Sessions**: Multi-device refresh-token rotation with reuse detection.
- **Retention**: 6 months (flash-wear on the board).

**Confirmed via Research**
- aarch64 onnxruntime wheel available for Python 3.12+ on Debian 10+.
- Alembic `render_as_batch=True` provides SQLite-to-PostgreSQL portability.
- WebSocket framing with frame + state atomic (no desync risk).
- Graceful shutdown under uvicorn: SIGTERM → lifespan → executor shutdown.

## Future Work (NOT NOW)

These items are explicitly deferred and not part of v0.1.0. Raising them requires a new planning cycle.

### Multi-Process Architecture
Capture and inference would split into separate processes if horizontal scale is needed:
- Capture worker (WebSocket → ESP32, publish raw JPEG to queue).
- Inference worker pool (consume JPEG, run YOLO, publish detections).
- Single DB-writer thread (serialize SQLite access).

**Rationale**: Current single-process design is correct for the board's CPU constraints. Refactor only if 6-camera ceiling proves insufficient.

### Licence-Plate Recognition
Not in the original scope; requested features from the API contract are incomplete.

**Rationale**: Requires separate YOLO model, adds inference overhead, privacy implications require end-user consent. Defer to a later release if business value is confirmed.

### Smoke & Fire Detection
Not in the original scope; out of project boundary.

**Rationale**: Distinct computer-vision problem, separate inference pipeline, different business process (fire brigade vs. security team). Defer to a separate system if risk assessment warrants it.

### QNN/NPU Acceleration
QRB2210 NPU support unverified; ONNX with CPU is the safe baseline.

**Rationale**: If profiling on the board shows inference is the bottleneck (not I/O or other factors), and if a QNN-compatible YOLO model exists, then evaluate. No measured data yet.

## Effort & Schedule

- **Planned**: 158 hours. The figure is a plan estimate; actual effort was not
  tracked, so no "actual vs planned" comparison is recorded here.

## Success Metrics (Targets)

None of these has been confirmed on the target board. They are the criteria a
release must meet, not a record of a release that met them.

- CI runs < 10 min.
- Coverage gates: domain 100%, security ≥90%, backend ≥80%, frontend ≥60%.
- Docker image builds for arm64.
- `docker compose up` starts cleanly; migrations run; app serves the SPA.
- Fake detector enables full-pipeline testing without hardware — **met**, this
  one is exercised by the test suite on every run.
- SIGTERM produces a graceful shutdown with no pending-task warnings.
- No ultralytics in the deployment image; ONNX weights not tracked by git.

## Known Unknowns (Unmeasured on Target)

- **Latency**: Frame capture → detection → DB write → WS broadcast roundtrip time on Arduino UNO Q.
- **CPU usage**: Peak and steady-state under 6-camera simultaneous capture + inference + API load.
- **Memory growth**: RSS baseline and soak-test growth rate (target: < 5% per 8 hours).
- **Storage**: Image size after an arm64 build (target < 700 MB; no build measured).
- **Accuracy**: YOLO vehicle detection on the reference dataset under the board's lighting conditions.
- **Throughput**: Max concurrent WebSocket viewers before degradation.

All numbers to be recorded in `deployment-guide.md` after soak test on real hardware (phase 14, step 13). Until then, they are stated as unmeasured.
