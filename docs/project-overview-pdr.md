# Project Overview & PDR (Product Development Requirements)

## The Problem

Car parks (particularly basement facilities) are difficult to navigate when half-full. Residents and visitors waste time circling to find free spaces; security guards cannot give reliable guidance; and management lacks visibility into occupancy patterns for sizing and pricing.

**CAPS-DASH** automates occupancy detection via YOLO vehicle detection and slot-polygon mapping, giving residents real-time counts (never which slot is occupied—privacy first), security actionable live views, and management historical trends.

## User Tiers & Workflows

### Resident
- **Access**: Lobby kiosk or mobile; read-only dashboard showing floor-level free counts.
- **Actions**: View free-space counts, check occupancy trends (last 7 days).
- **Constraints**: Never sees which slot holds which car. Cannot access camera streams or configuration.
- **Value**: Reduces search time, improves experience.

### Security Officer
- **Access**: Desktop or tablet; full read-only access to live feeds and history.
- **Actions**: Live-view individual cameras with detected boxes overlaid, check floor-level occupancy, review alerts (offline cameras, overstays), check audit log.
- **Constraints**: Cannot modify cameras or create users; cannot acknowledge or dismiss alerts on behalf of others.
- **Value**: Situational awareness, incident response (car double-parked?), training (who is here at midnight?).

### Administrator
- **Access**: Desktop; full read-write access.
- **Actions**: 
  - **Cameras**: Add/edit/delete cameras, test connection, adjust per-camera tuning (poll interval, vote threshold, confidence).
  - **ROI**: Draw and edit parking-slot polygons for each camera without stopping the system.
  - **Users**: Create, disable users; rotate their passwords.
  - **Operations**: Manually back up, restore from backup, purge old data, monitor system health (disk, clock).
  - **Audit**: Review all state changes (who logged in, what camera was deleted, when).
- **Constraints**: Only one admin at a time can perform a system operation (backup/restore/purge).
- **Value**: System ownership, operational control, incident investigation.

## Scope

### In Scope
- Greenfield web application (no legacy integration).
- Vehicle occupancy detection via YOLO (pre-trained model).
- Per-camera parking-slot polygon ROI.
- Real-time WebSocket stream for live view.
- 6 months of history with CSV export.
- Automated alerts: offline camera, overstay (> 12h), low disk.
- Bilingual UI (Vietnamese default, English provided).
- Deployment: Linux arm64 (Arduino UNO Q, QRB2210 SoC).

### Out of Scope
- Licence-plate recognition (business case unconfirmed).
- Smoke or fire detection (separate risk domain).
- Multi-site federation or cloud sync (single-building only).
- Mobile app native builds (web responsive on mobile).
- Entry/exit barrier integration (occupancy detection only).
- Predictive pricing or dynamic slot assignment algorithms.

### Explicitly Not Now
- Performance tuning beyond the 1-6 camera design target.
- QNN/NPU acceleration on QRB2210 (CPU baseline sufficient; profiling data not available).
- Multi-process architecture (if scale required, split capture/inference into separate process).

## Privacy Position

**Camera images never leave the building.** ONNX inference runs on the server inside the locked facility. Residents see occupancy counts (X free slots on Floor B1) and occupancy trends (historical charts), never which slot holds which car. Security and admin see live camera streams with overlays, but images are not exported or transmitted outside the physical network.

**Audit trail**: All user actions logged to database (login, logout, configuration changes). Audit logs are kept for 6 months and never exported.

**Credentials**: Stored hashed (argon2). Session tokens are short-lived (15 min access, 7 day refresh); refresh tokens are rotated per device with reuse detection to catch compromised tokens.

## Success Criteria

### Functional
Ticked items are implemented and covered by the automated suite. Nothing in
this list has been exercised against real camera hardware.

1. ✅ Real-time slot occupancy visible on the dashboard. The end-to-end latency
   target of a few seconds is unmeasured.
2. ✅ Live camera view with detected boxes and ROI overlay (no server-side encoding, JPEG passed through).
3. ✅ ROI editor allows on-the-fly polygon changes without stopping the system.
4. ✅ Multiple cameras run simultaneously against simulated frame sources.
5. ✅ 6 months of occupancy history queryable and exportable as CSV.
6. ✅ Alerts triggered correctly: offline, overstay, disk low.
7. ✅ Authentication enforced; audit trail complete.
8. ✅ Bilingual UI with consistent term usage.

### Non-Functional (targets, not yet confirmed on the board)
1. CI runs in < 10 minutes.
2. Backend test coverage ≥ 80%; domain 100%; security ≥ 90%.
3. Frontend test coverage ≥ 60%.
4. Docker image builds for arm64 and runs on an Arduino UNO Q.
5. Graceful shutdown on SIGTERM within 20 seconds.
6. No ultralytics (AGPL-3.0) in the deployment image; onnxruntime (Apache-2.0) only.

### Operational (as designed; not yet exercised on the board)
1. Deployment: `git clone` → `docker compose up` → migrations run → app serves SPA at `:8000`.
2. Backups: SQLite online backup API; backup files are valid databases (restore by copying).
3. Logs: Structured, machine-readable (JSON); request IDs correlate logs across layers.
4. Healthcheck: `/api/health` responds 200 when all cameras have been contacted at least once.

## Assumptions & Constraints

### Hardware
- **Deployment target**: Arduino UNO Q (QRB2210 SoC, aarch64 Linux, ~2 GB RAM, ~32 GB flash).
- **Network**: WiFi-connected ESP32-CAM modules inside the facility; JPEG over HTTP.
- **Scale**: Designed for a demo-scale site of 1-6 cameras. No load test has
  been run, on simulated sources or real ones.

### Performance (Unmeasured)
- Latency: Frame capture to state change visible on dashboard (no number recorded until soak test).
- CPU: Peak and sustained utilization under 6-camera load (no baseline).
- Memory: RSS growth rate during 8-hour soak (target < 5%; actual unknown).
- Storage: Docker image size (target < 700 MB; actual post-build unknown).

### Standards
- **Python**: 3.12+ (type hints, match statements, positional-only parameters).
- **JavaScript**: ES2021+, strict TypeScript, React 19.
- **Database**: SQLite 3 (single-file, embedded, no separate DB server).
- **Inference**: ONNX Runtime (Apache-2.0); YOLO v8 model pre-trained on COCO.

## Architecture Summary

```
┌─ ESP32-CAM (ceiling)
│      ↓ JPEG over HTTP
│ ┌──────────────────────────────┐
│ │   CAPS-DASH Server           │
│ │  (one uvicorn worker)        │
│ │                              │
│ │ ┌─ Camera Loop ──┐           │
│ │ │  YOLO Detection│→ vote     │
│ │ │                │→ SQLite   │
│ │ └────────────────┘           │
│ │                              │
│ │ ├─ REST API (34 endpoints)   │
│ │ ├─ WebSocket (live stream)   │
│ │ └─ SPA (React + Ant Design)  │
│ └──────────────────────────────┘
│           ↓
└─→  Browser (desktop/tablet/kiosk)
```

**One process, one worker, one model in memory.** N workers = N loops per camera → N vote filters → N SQLite writers = incorrect results. Constraint encoded in CLI, Dockerfile, and systemd.

## Data Model (8 Tables)

| Table | Purpose |
|-------|---------|
| `users` | Admin, security, resident accounts with hashed passwords. |
| `refresh_sessions` | Multi-device session tracking with rotation and reuse detection. |
| `cameras` | Network addresses, per-camera tuning, last-seen timestamp. |
| `parking_slots` | ROI polygons per camera, current state, last-changed timestamp. |
| `slot_state_history` | Timestamped occupancy changes for history queries. |
| `hourly_stat` | Pre-aggregated 1-hour occupancy summaries (expensive to compute live). |
| `alert` | Offline, overstay, disk-space, overlap, clock-unsync alerts with severity. |
| `audit_log` | All state-changing operations (login, camera created, etc.) with actor and timestamp. |

## Risk Assessment

| Risk | Mitigation | Status |
|------|-----------|--------|
| One worker not enforced at deploy time | Encoded in Dockerfile CMD, compose, systemd; runtime guard on startup | ✅ |
| Flaky vote filter from incorrect windowing | Vote-filter unit tests at 100% coverage; integration tests with fixtures | ✅ |
| Image bloat from onnxruntime + opencv | `opencv-python-headless`, slim base, no build toolchain in runtime stage | ⚠️ Unmeasured |
| UNKNOWN mistakenly folded into FREE count | Type annotation (`SlotState.UNKNOWN`) distinct in domain; tests assert separation | ✅ |
| Camera credentials hardcoded in source | Source URL in database, env-based override per camera; no source-code constants | ✅ |
| Graceful shutdown doesn't complete | SIGTERM test verifies exit code 0 within timeout; no "Task was destroyed" logs | ✅ |
| Soak reveals slow leak late in project | Memory profiling planned for phase 14 step 13; < 5% growth target | ⏳ Pending |

## Acceptance Criteria

Project is complete when:

1. All 14 phases implemented and reviewed.
2. CI pipeline green on a clean clone; total runtime < 10 min.
3. Coverage gates met: domain 100%, security ≥90%, backend ≥80%, frontend ≥60%.
4. `docker compose up` → app serves SPA → login works → camera created → state observed → WS frame sent → shutdown clean.
5. SIGTERM test passes (Linux); Windows variant skipped with documented reason.
6. Soak test 8 hours: RSS growth < 5%; no objectURL leaks; no subscriber queue buildup.
7. All 8 documentation files exist, cross-linked, and non-empty.
8. README includes quickstart, layout, architecture, licence note.
9. `pip freeze` inside image has no ultralytics; `git ls-files` has no `.onnx` or `.pt`.

## Definitions

- **Slot**: A single parking space, identified by camera and ROI polygon.
- **Occupancy**: State of a slot (UNKNOWN, FREE, OCCUPIED); determined by YOLO detection + vote filter.
- **Vote filter**: N-of-M window to suppress transient detections (e.g., 4-of-5 frames must agree).
- **ROI**: Region of Interest; admin-drawn polygon on camera frame defining a parking slot.
- **Soak test**: 8-hour continuous run with 4 fake cameras + 1 browser live view; measure memory growth.
- **Audit log**: Complete record of user actions (login, create camera, update ROI, etc.).
- **Flash-wear**: Concern specific to embedded devices with limited write-cycle budget (Arduino UNO Q); 6-month retention is a tradeoff between history depth and device longevity.
