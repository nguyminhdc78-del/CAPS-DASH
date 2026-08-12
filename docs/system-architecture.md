# System Architecture

Physical deployment, process model, concurrency, data flow, and the WebSocket framing spec.

## Physical Flow

```
┌─────────────────┐     ┌──────────────────────────────────────┐
│  MaixCam        │────▶│  CAPS-DASH Server                    │
│  (Ceiling)      │     │  (Linux arm64, one process)          │
│  GET /snapshot  │     │                                      │
│  one JPEG, 2.0s │     │                                      │
└─────────────────┘     │  ┌─────────────────────────────────┐│
                        │  │ Camera Loop (asyncio task)      ││
                        │  │ ├─ Read frame (poll interval)   ││
                        │  │ ├─ Publish frame (WS hub) ◀─ now ││
                        │  │ └─ Start detection, do NOT wait ││
                        │  │      ├─ Run YOLO (inference pool)│
                        │  │      ├─ Vote filter (N-of-M)    ││
                        │  │      └─ Write slot state (db)   ││
                        │  └─────────────────────────────────┘│
                        │                                      │
                        │  ┌─────────────────────────────────┐│
                        │  │ REST API (sync handlers)        ││
                        │  │ (FastAPI threadpool, <10ms)     ││
                        │  └─────────────────────────────────┘│
                        │                                      │
                        │  ┌─────────────────────────────────┐│
                        │  │ WebSocket Hub                   ││
                        │  │ (broadcast frames to viewers)   ││
                        │  └─────────────────────────────────┘│
                        │                                      │
                        │  ┌─────────────────────────────────┐│
                        │  │ SQLite Database                 ││
                        │  │ (config, history, audit)        ││
                        │  └─────────────────────────────────┘│
                        └──────────────────────────────────────┘
                                  ▲
                                  │ HTTP/WebSocket
                                  ▼
                        ┌──────────────────────┐
                        │  Browser             │
                        │  (React + Ant Design)│
                        │  (Dashboard SPA)     │
                        └──────────────────────┘
```

**The primary path is snapshot polling.** The camera holds its sensor open and
caches the newest encoded frame; the backend pulls one JPEG per tick over plain
HTTP through `Esp32CamHttpSource`, decodes it, publishes frame and state to
viewers as **one binary message** so overlays stay aligned with the picture
they describe, and starts a detection without waiting for it.

RTSP remains a supported `source_type` - `CameraSourceType.RTSP`,
`RtspStreamSource` and its tests are all still here, and an operator with an IP
camera should use it. It is no longer the shape the defaults are tuned for. The
reason is CPU and simplicity, not a failure: an in-process four-thread FFMPEG
HEVC decoder cost 325% of 400% available CPU. See *Why RTSP is not the primary
path* in `deployment-guide.md`, which also records why the lag figures there
are specific to the link they were measured on.

**Camera loops start staggered.** Every camera's tick sleeps the remainder of
its own interval from its own start, so N loops spawned in the same millisecond
keep firing together forever and hand N inferences to a one-worker pool at
once - the last one waits (N-1) detections for a result describing a frame that
is already several ticks old. `CameraSupervisor.reconcile()` therefore spreads
first ticks across the interval (`camera_start_stagger.py`): three cameras at
2.0 s start at +0.00, +0.67, +1.33. The offset is applied once, before the
supervise retry loop, so a camera that crashes and backs off does not drift
further from its slot on every restart.

## Process Model (Single Uvicorn Worker)

**Why one worker?** N workers = N camera loops per camera, N vote filters per slot, N SQLite writers on one file.

```
┌─────────────────────────────────────────────────────────────┐
│ One Linux Process (one UNO Q, one venv)                     │
│                                                             │
│  ┌─ Event Loop (asyncio)                                   │
│  │  ├─ Camera Task 1 ─┐                                    │
│  │  ├─ Camera Task 2  │ Concurrent                         │
│  │  ├─ Camera Task 3  │ (I/O overlapped)                   │
│  │  └─ WebSocket Echo ┘                                    │
│  │                                                         │
│  │  Job Scheduler (runs every 10 min, 5 min, daily, etc.) │
│  │                                                         │
│  ├─ Request Handler (sync)                                │
│  │  └─ Delegates to services, reads/writes via session   │
│  │                                                        │
│  ├─ Inference Pool (ThreadPoolExecutor, max_workers=1)   │
│  │  └─ YOLO inference (CPU-bound, blocking)              │
│  │                                                        │
│  └─ DB-Write Pool (ThreadPoolExecutor, max_workers=1)    │
│     └─ SQLite writes only (serialize all contention)     │
│                                                          │
└─────────────────────────────────────────────────────────────┘
```

## Concurrency Table

| Component | Thread | Blocking? | Rationale |
|-----------|--------|-----------|-----------|
| Camera loop (poll, download) | Event loop | No (async) | I/O overlapped; one loop per camera wakes and waits |
| YOLO inference | Inference pool | Yes (CPU) | Serialized; one model in memory |
| Database writes | DB-write pool | Yes (I/O) | Serialized; SQLite can only handle one writer per connection |
| Database reads | Handler thread | No | Sync SQLAlchemy; event loop unused during request |
| WebSocket frames | Event loop | No (async) | Fan-out to subscribers; no blocking I/O |
| Background jobs | DB-write pool | Yes | Run on the same executor as camera writes; serialized |

**Key insight**: The board has one CPU, shared between camera loops and API requests. Serializing inference through one pool and DB writes through one pool keeps contention predictable and measurable.

## WebSocket Framing Spec

**Endpoint**: `/ws/cameras/{camera_id}`

**Authentication**: Bearer token in the initial JSON message (5 s timeout). Role checked; security+ allowed.

**Message format**: Binary frame containing exactly one camera state + JPEG.

```
[4-byte BE uint32: header_length][UTF-8 JSON header][JPEG bytes]
```

**Header example**:
```json
{
  "camera_id": 1,
  "frame_num": 42,
  "timestamp": "2026-08-11T15:23:45Z",
  "state": {
    "slot_1": "FREE",
    "slot_2": "OCCUPIED",
    "slot_3": "UNKNOWN"
  }
}
```

**Why this framing?** Frame and state are atomic. If the socket closes mid-message, the client detects an incomplete frame (header_length tells it how much JSON to read) and discards it. No state without a frame; no frame without state.

**JPEG passthrough**: Server never re-encodes. The frame bytes come directly from the ESP32.

## Data Model

8 tables, normalized to avoid denormalization bugs but denormalized selectively for performance.

```
┌──────────────┐         ┌─────────────────┐
│ users        │◄────────│ refresh_sessions│
├──────────────┤         ├─────────────────┤
│ id (PK)      │         │ id (PK)         │
│ username (U) │         │ user_id (FK)    │
│ password_hash│         │ device_id       │
│ role         │         │ token_version   │
│ is_enabled   │         │ expires_at      │
│ created_at   │         │ created_at      │
└──────────────┘         └─────────────────┘

┌──────────────┐         ┌──────────────────┐
│ cameras      │◄────────│ parking_slots    │
├──────────────┤         ├──────────────────┤
│ id (PK)      │         │ id (PK)          │
│ code (U)     │         │ camera_id (FK)   │
│ name         │         │ slot_index       │
│ floor (IDX)  │         │ polygon (JSON)   │
│ source_type  │         │ state            │
│ source_url   │         │ last_changed_at  │
│ poll_interval│         │ created_at       │
│ vote_window  │         └──────────────────┘
│ confidence   │         
│ is_enabled   │         ┌──────────────────────┐
│ frame_size   │◄────────│ slot_state_history   │
│ last_seen_at │         ├──────────────────────┤
│ last_error   │         │ id (PK)              │
│ created_at   │         │ slot_id (FK, IDX)    │
└──────────────┘         │ state                │
                         │ inferred_at (IDX)    │
                         └──────────────────────┘

┌─────────────────┐      ┌──────────────────┐
│ hourly_stat     │      │ alert            │
├─────────────────┤      ├──────────────────┤
│ id (PK)         │      │ id (PK)          │
│ slot_id (FK)    │      │ type (IDX)       │
│ hour_start (U)  │      │ severity         │
│ free_count      │      │ message          │
│ occupied_count  │      │ entity_type      │
│ unknown_count   │      │ entity_id        │
└─────────────────┘      │ triggered_at     │
                         │ acknowledged_at  │
┌──────────────┐         └──────────────────┘
│ audit_log    │
├──────────────┤
│ id (PK)      │
│ user_id (FK) │
│ action       │
│ entity_type  │
│ entity_id    │
│ details (JSON)
│ created_at   │
└──────────────┘
```

**Indices**: `slot_id` + `inferred_at` on history (range queries); `camera_id` + `is_enabled` on cameras (active camera list); `inferred_at` on history (retention purge).

**Partitioning**: No time-based partitioning (SQLite limitation); range queries capped at 92 days to keep scans bounded.

## HOT-RELOAD Flow (ROI Polygon Changes)

```
1. Admin draws polygon in ROI editor
   └─→ POST /cameras/{id}/slot-map
   
2. Handler validates polygon geometry, commits to DB
   └─→ INSERT/UPDATE parking_slots
   
3. AFTER commit succeeds, signal is sent
   └─→ reload_signals.send(camera_id)
   
4. Camera loop receives signal (select on asyncio.wait)
   └─→ Wakes from sleep; reads new polygon from DB
   
5. Loop applies polygon to next batch of detections
   └─→ Slot assignment re-runs
   └─→ live_view immediately shows new ROI overlay
```

**Critical**: Signal sent AFTER commit. If sent before, and the loop restarts for any reason before the commit lands, the new polygon is lost.

## Slot Assignment Algorithm

Given:
- Bounding boxes from YOLO: [(x1, y1, x2, y2), ...]
- Parking slots with ROI polygons: [polygon_1, polygon_2, ...]

Algorithm (in `caps_dash.vision.domain.assignment`):
1. Compute box centroids.
2. Test each centroid against each polygon (point-in-polygon).
3. Return {slot_id: bounding_box, ...}.

**Vote filter** (in `caps_dash.vision.domain.vote_filter`):
- Maintains a sliding window of size N.
- For each slot, count how many of the last N frames showed it occupied.
- Report occupied if count >= threshold (e.g., 4-of-5).
- Report free if count == 0 for a full window.
- Report UNKNOWN otherwise.

**Why N-of-M?** Transient misdetections (hand moving past camera, shadow) are suppressed. The board is not fast enough to re-detect every frame; voting smooths out noise.

## Background Jobs

Scheduled via `interval_scheduler.py`; all run on the DB-write pool (serialize with camera writes).

| Job | Interval | Action | Triggers |
|-----|----------|--------|----------|
| hourly_aggregation | 10 min | Summarize 1-hour buckets | Stats queries |
| overstay_alert | 5 min | Flag slots occupied > 12h | Admin notification |
| disk_space_alert | 15 min | Check free space; alert if <10% or <256 MiB | System health |
| retention_purge | daily | Delete history older than 6 months | Storage management |
| rate_limiter_sweep | hourly | Expire login attempt buckets | Security cleanup |

All jobs read `settings` for thresholds (overstay_hours, disk_low_percent, etc.) — no hardcoded thresholds.

## Error Handling & Recovery

### Camera Loop Failures
If a camera crashes (network timeout, malformed JPEG, detector crash):
1. Exception caught; error logged.
2. `last_error` field updated on the Camera row.
3. Backoff timer started (1 s, exponential, capped at 60 s).
4. Loop wakes after backoff; retries.
5. After 3 consecutive failures, the camera is marked offline and an alert is triggered.

### Database Failures
- If a write fails, the exception propagates to the camera loop supervisor.
- Supervisor logs the error, cancels the task, and re-launches it after backoff.
- Admin can inspect `last_error` and investigate.

### WebSocket Disconnection
- Client disappears without closing the frame.
- Server detects via heartbeat timeout (20 s).
- Subscriber is removed from the hub; memory is freed.

## Scaling Constraints (Known Limits)

**Measured ceiling** (2026-08-12, on the real board): inference costs a median
616 ms per frame (fastest 502, slowest 1440) for YOLO26-nano at 640x640 on the
UNO Q's four aarch64 cores, via onnxruntime 1.28.0 on the CPU provider.

Inference is serialised through one worker, but the change gate keeps most
frames away from it: measured at **11% of frames inferred** on a static,
exposure-locked car park, with the other 89% costing 2.7 ms to compare and
skip. That is what makes the 1-6 camera target reachable - on inference cost
alone it would be about five cameras at a 3 s poll.

The skip rate is a property of the *scene*, not of the code: a view with
constant through-traffic approaches 100% inferred, and the pessimistic figure
becomes the real one. See `deployment-guide.md` for the arithmetic and for why
the camera's exposure must be locked for any of it to hold.

**The live view is not behind any of this.** A tick reads a frame, publishes
it, and *starts* a detection without waiting for it; the result is applied
whenever it lands, and the frame it describes has usually been on screen for a
while by then. Publishing used to sit after the inference await, which put a
whole detection into the age of every frame a viewer saw - and only on the
ticks where the picture had changed, so the view was smooth while nothing
happened and stalled the moment a car moved. At most one detection runs per
camera at a time; a tick that finds the detector busy just publishes and moves
on. The overlay therefore trails the picture by up to one detection, which the
frame header marks as `inference_skipped`.

### Two settings with similar names

This has already caused one wrong conclusion, so it is worth five lines.

| | `INFERENCE_POOL_SIZE` | `INFERENCE_THREADS` |
|---|---|---|
| Means | How many inferences run **at once** | Threads used **inside one** inference |
| Wired to | `ThreadPoolExecutor(max_workers=...)` | `intra_op_num_threads` on the ONNX session (`inter_op` pinned to 1) |
| Default | **1** | 2 |
| Change it? | **Never.** One detector per worker thread, one model in RAM - a correctness constraint | Yes, on measurement |

Raising `INFERENCE_THREADS` does **not** let two inferences run in parallel. It
makes each one finish sooner, which shrinks the *serialized* worst case - which
is the thing that has to fit the tick. Three cameras at a median 616 ms is
1.85 s against a 2.0 s tick.

If that budget does not fit, the decided response is to **raise the tick** (and
accept that the live view slows with it, since the tick is also the frame
rate), not to raise `INFERENCE_POOL_SIZE`.

- **Viewers per camera**: 4 max (tunable in settings).
- **Total concurrent viewers**: 16 max.
- **Inference pool**: 1 worker (one model in memory; serializes YOLO calls).
- **DB-write pool**: 1 worker (SQLite concurrency).

**Why these limits?** The board shares one CPU. More than 6 cameras means the event loop cannot time-slice between them; some would miss their poll deadline. More than 1 inference worker means multiple models in RAM (not feasible). More than 1 DB writer means SQLite lock contention.

**To scale beyond 6 cameras**: Split into a multi-process architecture (future work, not now). Capture process polls ESP32 cameras and publishes raw JPEG to a queue. Inference workers consume queue, run YOLO, publish detections. One DB-write process serializes all writes.

## Observability & Logging

### Structured Logging
All logs are JSON (via structlog). Each log line includes:
- `timestamp`: ISO 8601 UTC.
- `level`: INFO, WARNING, ERROR.
- `logger`: Module name.
- `message`: Human-readable summary.
- `context`: Additional fields (camera_id, user_id, etc.).
- `request_id`: Correlates across layers (middleware injected).

### Log Output Locations
- **Console**: During development (docker compose logs).
- **Application log**: `/var/log/caps-dash/app.log` (systemd).
- **Never disk**: Logs are ephemeral on the board (not persisted to preserve flash wear).

### Healthcheck
`GET /api/health` returns:
```json
{
  "status": "ok",
  "timestamp": "2026-08-11T15:23:45Z",
  "cameras": {
    "1": { "status": "ok", "last_seen_s": 3 },
    "2": { "status": "error", "last_error": "Connection timeout" }
  },
  "database": { "status": "ok" }
}
```

Returns 200 only if at least one camera has been contacted in the last 60 seconds and the database is reachable.

## Deployment Architecture

```
┌─────────────────────────────────────────┐
│ Docker Container (arm64)                │
│                                         │
│  ┌─────────────────────────────────────┐│
│  │ CAPS-DASH (uvicorn, 1 worker)       ││
│  │ ├─ Camera loops (async)              ││
│  │ ├─ REST API (FastAPI)                ││
│  │ ├─ WebSocket hub                     ││
│  │ └─ Background jobs                   ││
│  └─────────────────────────────────────┘│
│                                         │
│  ┌─────────────────────────────────────┐│
│  │ SQLite /app/data/caps.db             ││
│  └─────────────────────────────────────┘│
│                                         │
│  ┌─────────────────────────────────────┐│
│  │ Models /app/models/*.onnx (RO)      ││
│  └─────────────────────────────────────┘│
│                                         │
└─────────────────────────────────────────┘
         ▲              ▲
         │ (env)        │ (bind mount)
         │              │
    /.env.example   models/
    
    nginx reverse proxy (TLS)
         ▲
         │ HTTPS
         ▼
    Browser
```

**Entrypoint**: `/usr/local/bin/docker-entrypoint.sh` runs migrations, then execs uvicorn.

**User**: Non-root (`caps:10001`) to limit blast radius of any RCE.

**Volumes**: 
- `/app/data` (read-write) — database + backups.
- `/app/models` (read-only) — pre-committed ONNX weights.

## Version & Lifecycle

| Aspect | Value |
|--------|-------|
| Runtime Python | 3.12–3.13 (upper bound at next minor) |
| FastAPI | 0.141–0.142 |
| Pydantic | 2.13–3.0 |
| SQLAlchemy | 2.0.51–2.1 |
| React | 19.x |
| Ant Design | 6.x |
| License (runtime) | Apache-2.0 (onnxruntime) |
| License (dev-only) | AGPL-3.0 (ultralytics) |

No LTS; latest stable at scaffold time, committed lockfile. The board is embedded; updates are infrequent and planned.
