# Changelog

All notable changes to CAPS-DASH documented by release. Format follows [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]

### Added
- **Bay-status LED ring on the camera node (WS2812B, GPIO 14).** A driver standing at the bay now sees the answer without a screen: **red = occupied, green = free, breathing amber = unresolved or no server**. The ring is divided into one arc per bay the camera watches, with a dark LED between arcs so two adjacent occupied bays do not read as one long red one. New firmware endpoint `GET /ring?slots=10u` (`firmware/esp32cam/slot-ring-led.{h,cpp}`) and a `SlotLedRing` pusher on the camera loop (`backend/caps_dash/services/slot_led_service.py`). Nothing to configure: it pushes on a state change, refreshes every 15 s so a rebooted ring repairs itself, and a device answering `404` is asked once and then left alone - the reference rig is a MaixCam and has no ring.
  - **The camera is told the answer, it does not work it out.** YOLO and the vote filter run on the server; a node guessing locally would light a colour that disagreed with the dashboard beside it.
  - **UNKNOWN is amber, never green** - the same rule as the dashboard, on the lamp. Green sends a driver to a space nobody has looked at. So does a lamp still confidently showing the answer it heard twenty minutes ago, so the firmware falls back to amber after 90 s without a push (three missed refreshes).
  - **The colours are picked for daylight, not taste.** In sunlight only saturation and maximum drive survive; washing a hue toward white - the instinctive way to make an LED brighter - is exactly what destroys it. The eye is also not equally sensitive to the two dies: the green die (~525 nm, V(λ)≈0.79) reads roughly twice the luminance of the red (~625 nm, V(λ)≈0.27) at the same current, which typical part specs bear out (1100-1400 mcd vs 550-700 mcd at 20 mA). Red therefore runs flat out at `(255, 12, 0)` - the hint of green buys ~9% luminance for an invisible hue shift - and green is deliberately held *back* to `(0, 200, 40)` so it does not make the red look broken or blind anyone at night. The touch of blue nudges green toward the blue-green that traffic signals use deliberately: red/green is the worst possible pair for the ~8% of men with a red-green deficiency. **Red is the ceiling; if it is not readable in direct sun the fix is a hood or a bigger ring, not a bigger number.**
  - Power is the trap: a 16-LED ring is ~320 mA on top of the camera's ~250 mA peak, and a 500 mA charger browns the ESP32 out mid-transmit - indistinguishable from a flaky camera. See `docs/deployment-guide.md` for wiring, commissioning and the 3.3 V-data caveat.
  - `GET /status` now also reports `ring` and `ring_age_s`, which is what separates "these bays are unresolved" from "the server stopped talking" - the ring shows amber for both.
  - **"No free bay" is its own display.** When every bay the ring covers is occupied it stops drawing arcs and pulses the whole ring red, fast and shallow (1.4 s, floor 150/255). Arcs answer "which bay is free" for somebody standing under the camera; they cannot answer "is it worth driving down this aisle" from the far end, where the ring is one red smudge and the gaps are invisible. Motion is the strongest attention cue there is, so a full row becomes a single moving object. The floor is high on purpose - a pulse dipping to near-black halves the average output and undoes the reason the colours were picked. Distinct from the amber breath by both colour and rhythm.
  - **Fixed: the ring went stale exactly when the car park was quiet.** The push started out in `apply_outcome`, so it only happened when a detection did - and on a still scene the change gate stops letting detections through, which is its entire job. Pushes stopped with them, the firmware's 90 s staleness window expired, and the ring showed "no server" amber over bays whose state was perfectly well known. **Measured on the board: 321 s without a push.** The 15 s refresh could not save it either, since that also lived inside the call that had stopped happening. The tick now drives the ring instead of the detector; `tests/workers/test_camera_loop_integration.py` pins the property that broke - pushes must outnumber detections on a gated scene. Found by reading the board's journal against real hardware, not by any test.
  - **A commissioning test in the dashboard** (Cameras → settings panel → "Bay-status LED ring"): three buttons that light the whole ring red, green or amber, so an installer standing at the camera can confirm the pin, the 5V supply and the colour order (a strip that lights green when told red is wired RGB, not GRB) without waiting for a real car to arrive. New endpoint `POST /api/cameras/{id}/ring-test`, admin only. Unlike the camera loop's own pusher - which stays silent on failure, because a lamp must never become a detection problem - this one **raises**: somebody is standing in front of the ring waiting, and a 404 ("the node answers but has no ring: flash the firmware") is deliberately a different error from a connect failure ("check the wiring"). Not audited, and the pattern reverts within 15 s when the camera loop pushes again; there is no lock to hold it, for the same reason UNKNOWN is not green.
  - **The WiFi password left the tracked sketch.** It now comes from `firmware/esp32cam/wifi-credentials.h` (gitignored, with a committed `.example.h` as the contract), picked up via `__has_include`. The old arrangement was a literal in the `.ino` plus a comment asking whoever flashed the board to blank it before committing - a process that has to be remembered every time eventually is not, and forgetting once puts a live credential in git history forever. A build without the file compiles but cannot associate, which is deliberate: it fails loudly at the network rather than looking like a hardware fault.
  - **`STATIC_IP` corrected from `.51` to `.50`.** The installed module holds `.50` and the `02` camera row points at `http://192.168.137.50/anh`; the sketch carried `.51` on a since-stale note about another device answering on `.50`. Flashing that would have moved the module off the address the database names and taken the camera offline at the next reboot - a failure that looks like the LED work broke the camera and points nowhere near the cause. The two are one setting in two places and the comment now says so.
  - Dependency: Adafruit NeoPixel (LGPL-3.0, firmware only, never part of the server image). Its ESP32 backend drives the strip from the RMT peripheral; the camera uses I2S0 and LEDC channel 0, so the two do not contend.
- **Technical description of every algorithm in the system** (`docs/algorithms-and-techniques.md`, Vietnamese). One reference covering the vision pipeline end to end (change gate, letterbox, dual-layout YOLO decode, per-class NMS, ground-point assignment, band-sampling fallback, ROI filtering, N-of-M voting), the concurrency model (single-worker constraint, inference scheduler, camera stagger, thread-safe hot reload), the realtime protocol (binary framing, latest-wins backpressure, post-connect WS auth), data and time handling (change-only history, session derivation, hourly rollup, clock guard, online backup), security (argon2id, JWT typing, sliding-window limiter, ranked RBAC), and the frontend techniques. Each entry records the algorithm, its parameters, complexity, and the measured failure it exists to prevent.
- **Public customer kiosk** (unauthenticated, behind `PUBLIC_KIOSK_ENABLED`, off by default). The `/kiosk` lobby screen is now public, showing free bay codes and (when `PLATE_READING_ENABLED=true`) a partial-match licence-plate search for customers to find their own car. This is a deliberate privacy trade-off: anyone on the network can enumerate the car park and locate a vehicle. Mitigated by: the kill-switch (default off), per-IP rate limit (10 searches/60s, env-tunable), and anonymous audit (one row per search with client IP). See `docs/project-overview-pdr.md`'s Privacy Position for the full rationale.
- **New environment variables**:
  - `PUBLIC_KIOSK_ENABLED` (default false): Gate for the `/api/public/*` endpoints.
  - `PUBLIC_KIOSK_MAX_SEARCHES` (default 10): Rate-limit budget per IP per window.
  - `PUBLIC_KIOSK_WINDOW_S` (default 60): Rate-limit window (seconds).
  - `FORWARDED_ALLOW_IPS` (default `127.0.0.1`): Comma-separated proxy IPs to trust for `X-Forwarded-For` extraction. Critical for correct client IP extraction behind a reverse proxy, both for rate limiting and audit logging. See `docs/deployment-guide.md` Proxy-trust subsection.
- **Public API routes**:
  - `GET /api/public/summary`: Occupancy counts + free bay codes per floor. No authentication.
  - `GET /api/public/plates/search?q=<plate>`: Partial-match search on occupied bays only. No authentication, rate-limited per IP, anonymous audit.
- **Frontend**: New public kiosk components with auto-clear of results (60s) on shared hardware, disabled notice when feature is off, and plate search with typed input cleared alongside results.
- **Anonymous audit rows**: Each public search writes an `audit_log` row with `user_id=NULL`, `username=""`, `client_ip=<IP>`, and `after={"public": true, "matches": n}`.

### Fixed
- **The ROI is now the detection filter, and a bay reports one vehicle.** A stock COCO model pointed at the reference rig returned **14–21 boxes per frame for three parked cars** (measured over 16 consecutive live frames, 2026-08-14): a computer mouse and a toy on the desk behind the bays both scored as vehicles, and each car came back two or three times over as `car` and again as `truck`, which per-class NMS inside the detector cannot merge. Every one of those boxes was drawn on the live view and counted in the dashboard's vehicle readout. Two rules now apply in `vision/domain/slot_detections.py`, before state, the overlay and the plate reader: a detection outside every slot polygon is discarded, and a slot keeps only its best-scoring box (highest confidence, largest area on a tie, so the overlay does not jitter between two equal boxes). On the measured frames that takes 14–21 boxes down to at most 3. **Occupancy is unaffected by construction** — one box and five boxes in a bay both mean occupied — which is why the collapse is safe ahead of the vote filter rather than after it; a regression test pins that equivalence.
- **The "two vehicles in one slot" install warning stopped crying wolf.** It counted boxes, so the same car returned as `car` and `truck` read as two vehicles and the warning fired 25 times in 45 minutes on a rig where no polygon was wrong. It now counts *distinct* vehicles, merging boxes above `SAME_VEHICLE_IOU` (0.50) — NMS's shape, but run per slot and across classes, which is exactly the case the detector's own per-class NMS cannot see.
- **Stale lazy-chunk imports after a redeploy no longer dead-end.** The SPA lazy-loads each route as a hashed chunk; a redeploy renames those chunks, so a tab left open on the old `index.html` 404s the old filename and React Router showed "Failed to fetch dynamically imported module". A `lazyWithReload` wrapper (`frontend/src/app/lazy-with-reload.tsx`) now does a single guarded hard reload on that failure, so the tab self-heals to the fresh bundle instead of dead-ending. Loop-guarded via sessionStorage; cleared on any successful load.
- **Session survived a reload again over http.** New `COOKIE_SECURE` setting (default: follow `APP_ENV`). The refresh cookie is `Secure` in prod, which a browser silently drops over plain http — so on an http LAN board every reload/new tab logged the user out. Set `COOKIE_SECURE=false` to serve prod over http and keep the session. A deliberate, documented reduction in cookie protection for the trusted-network demo case; leave unset (or true) behind HTTPS.

### Changed
- **Public kiosk reworked into a dark "HUD" find-your-car screen.** The plate search is now the visual hero, dead centre, styled as a neon-edged plate/HUD field with a radar sweep while the request is genuinely in flight (no fake delay) and a glowing result-reveal card (bay code as the hero, plus floor, plate, time). Occupancy availability is demoted to a compact strip beneath it - kept, not deleted, because it is the kiosk's second job and the only content when the plate-search kill-switch is off. The whole page forces its own dark neon theme (`KIOSK_HUD_THEME`) independent of the admin theme, and is responsive (a landscape lobby TV and a customer's portrait phone share one page; native focus raises the phone keyboard, no on-screen keypad built). No 3D map / wayfinding / car photo: the public API exposes only bay code + floor + plate + time, and images are discarded on device, so those would be fabricated or a privacy breach.
- **UI redesign ("Droom" visual language).** The whole SPA moves from stock Ant Design to an indigo/violet (`#6366F1`/`#8B5CF6`) system on a slate canvas with soft radial tints, Inter type, glassmorphic cards with a gradient top-accent, a deep-slate gradient sidebar with a gradient active pill, a translucent blurred header, gradient stat tiles on the dashboard (total=indigo, free=green, occupied=red, unknown=neutral slate), and an auth screen with animated gradient orbs. Implemented as one global layer (`frontend/src/styles/droom.css`) plus AntD token overrides (`use-theme-config.ts`); component churn kept minimal. Slot-state colours re-aligned (FREE `#22C55E`, OCCUPIED `#EF4444`, UNKNOWN `#94A3B8`) — **UNKNOWN stays a neutral slate, never green**, per the hard rule. Inter loads from the font CDN with a Segoe UI / system fallback so the page (and the offline kiosk) degrades cleanly. Light and dark both themed.
- **`SlidingWindowLimiter.record_failure` renamed to `record`**: The method now records any action (not only failures), and sweep jobs run on both `login_limiter` and `kiosk_limiter` hourly.
- **`/kiosk` is now unauthenticated and calls the public API.** ⚠️ **BREAKING for operators**: An upgrade without `PUBLIC_KIOSK_ENABLED=true` shows a "not enabled" notice. This is intentional; the feature must be explicitly enabled.
- **Snapshot polling replaces RTSP as the primary camera path.** The reference camera is a MaixCam on WiFi serving one JPEG per `GET /snapshot`, polled every 2.0 s through the existing `Esp32CamHttpSource` - no new source class, no migration, no change to the WebSocket transport or the single binary frame+state message. **RTSP is retained and still supported**: the enum value, the source, its diagnostics and its tests are all unchanged, and every measured RTSP number in `deployment-guide.md` is preserved. The reason for the change is CPU and simplicity - an in-process four-thread FFMPEG HEVC decoder cost 325% of 400% available CPU - **not** that RTSP failed: the lag figures were measured over a Windows ICS hotspot at 8-251 ms RTT and are specific to that link.
- `MIN_INFERENCE_INTERVAL_S` 1.5 → **0.0**. It gates only change-triggered runs, whose spacing is already bounded by the tick, so it is inert at any tick ≥ 1.5 s. The measured 3.54 → 0.83 load-average improvement that justified 1.5 belongs to the 0.2 s streaming tick and does not transfer. Still the right setting on a fast streaming source.
- `INFERENCE_THREADS` 2 → **4**, on a measurement rather than a guess. 50 runs per setting on the board with the service stopped: 2 threads 837 ms, 3 threads 631 ms, 4 threads 533 ms per inference - sublinear, and enough. It is what makes three cameras (3 x 533 ms = 1.60 s) fit a 2.0 s tick; at 2 threads that sum was 2.51 s and did not fit. Raising it cannot run two inferences at once - `INFERENCE_POOL_SIZE` stays 1 - it makes each one finish sooner.
- `MOTION_FORCE_INTERVAL_S` 10 → **30**. At a 2 s tick, 10 s meant every camera force-inferred every fifth tick and competed with genuine change-triggered runs. This is the ceiling on how long the system may be wrong when the change gate misses a real change - a deliberate trade for headroom.
- Source type `esp32cam_http` is now labelled "HTTP snapshot (polled)" in the dashboard. The stored value, the wire format and the DB CHECK constraint are unchanged; the type describes a contract - one JPEG per GET - not a vendor.
- New polled cameras default to a **2 s** poll interval (was 3 s). The tick is also the live-view frame rate, so 1 frame / 2 s is the expected live view for a polled camera, not a fault. `DEFAULT_POLL_INTERVAL_S` stays 3.0 for a generic slow HTTP camera.

### Added
- **Licence-plate reading and search (optional, `PLATE_READING_ENABLED`, off by default).** A guard can now find a car by its number - the case the security team actually asked for: a resident cannot remember where they parked. Plates are read **when a bay turns OCCUPIED**, not per tick; the vote filter already announces that moment, so the steady-state cost is zero and the whole feature costs ~1 s of the shared inference worker per arrival. The trigger pays for itself twice: at a transition the bay's polygon is known, so the frame is cropped to that bay first and the plate fills far more of the detector's input - which is what lets the cheap 384 px model do the work. Measured on the board over a full frame with four real plates: `yolo-v9-t-384` 1067 ms, `yolo-v9-t-640` 2642 ms / 3 of 4 read correctly. Cars only; motorbikes are not detected by this system.
  - **The authenticated route `/api/plates/search` (security and above only, every search audited)** - including searches that find nothing, which is exactly the question an audit of a plate database exists to answer. The public kiosk adds an unauthenticated route (see Added section above). The promise that **authenticated dashboard residents are never shown which bay holds which car** is unchanged, and is now a test rather than a comment (`tests/api/test_plate_search.py`).
  - **A bay only counts while it is still occupied.** The query takes `max(read_at)` per slot *before* filtering by plate, so a car that parked in A1 this morning and left cannot send a guard to A1, where a stranger's car is now. "Where was it last seen" is a separate, explicit toggle.
  - Plate rows are purged on the same `RETENTION_MONTHS` schedule as history. It is personal data with an expiry date.
  - Off by default deliberately: it downloads models on first use, costs inference time per arrival, and stores a number that identifies a vehicle and through it a person. Turning it on is one line; defaulting it on would ship personal-data collection to anyone who upgraded without reading.
  - **Verified end to end on the reference installation, 2026-08-13.** Three cars parked in three mapped bays; the running service read all three unprompted and wrote three rows: `50H56789` (0.95, 79 px, 1596 ms), `98A92599` (0.96, 68 px, 1049 ms), `98A83355` (0.95, 76 px, 1035 ms). **3 of 3 correct** against the plates as painted. The first read costs ~550 ms more than the rest - the model loading - and only once per worker thread. Search was then exercised against the live board: `98A-925.99`, `92599` and `98a` all find the right bay; `98` returns nothing, being below the three-character floor.
  - **The framing is the constraint, not the model.** At 640x480 framing the whole car park, a bay crops to ~125x145 px and a scale plate would be ~15 px - unreadable, and measured as such before the plates went on. What made it work was making the plate physically bigger in frame (68-79 px here). For a real installation the equivalent is a camera aimed at one or two bays, not at the whole floor: a plate camera is a different camera from an occupancy camera.
  - Dependency: `fast-alpr` (MIT, ONNX, no PyTorch). EasyOCR was rejected - it would drag torch onto a board with 1.7 GB of RAM to read characters that are plain Latin. Vietnamese plates carry only A-Z and digits, so no language model is involved.
  - `caps-dash.service` now sets `HOME=/var/lib/caps-dash`. The unit runs `ProtectHome=true` and the model caches are hardcoded to `Path.home()` upstream, so without it the first read would have nowhere to write.
- **Camera loops start staggered** across the poll interval instead of all at once (`camera_start_stagger.py`). Three cameras at 2.0 s now first tick at +0.00, +0.67 and +1.33 s, so each detection mostly lands in an empty queue rather than three deep behind the single inference worker. The offset is applied once, before the supervise retry loop, so a crash-and-backoff restart does not drift a flapping camera out of its slot.
- `deploy/maixcam/` - the camera-side HTTP snapshot app under version control, with install, smoke-test and rollback-to-RTSP instructions. The server binds `0.0.0.0` and prints every address it landed on at startup - the endpoint is unauthenticated and, contrary to the original plan, sits on the shared WiFi hotspot rather than a point-to-point link, so the exposure is made visible rather than argued away. It answers **503** rather than serving a frame older than 10 s, so a dead capture thread becomes an offline alert instead of a healthy-looking camera showing a frozen picture.
- RTSP camera source (`rtsp`), for IP cameras, action cameras and NVR sub-streams. Holds one session open, drained by a reader thread, and rebuilds it only when the picture falls behind; see `docs/deployment-guide.md` for the four designs measured and why a session per frame - which bounded lag nicely - wore the camera's session table down to `454 Session Not Found`.
- `MIN_INFERENCE_INTERVAL_S`: a floor on the gap between detector runs, independent of `poll_interval_s`. Needed on a fast source, where one setting cannot serve both the detector's rate and the live view's.
- `rtsp_endpoint_probe`: separates "the camera refused the connection" - its stream is switched off - from "the camera cannot be reached", in milliseconds rather than a full connect timeout. The message reaches the dashboard verbatim.
- `StreamLagTracker`: reports `decode_fps` and `lag_growth_s` per stream, turning "the picture looks late" into a number.
- Dashboard: live detector readouts under the hero camera - share of frames the change gate kept the detector off, median inference time, current vehicle count. All from frame headers the socket already sends.
- `esp32cam_stream` is now selectable in the camera form; the backend had supported it since 0.1.0 but the UI never offered it.

### Fixed
- **Every deep link returned a 404 error envelope instead of the app.** `SpaStaticFiles` fell back to `index.html` with `if response.status_code == 404`, but Starlette *raises* `HTTPException(404)` rather than returning a 404 response - so the fallback had never once run. Refreshing on `/slots`, bookmarking `/plates` or opening a link to `/cameras/01/live` all landed on `{"code":"NOT_FOUND"}`. It survived because the happy path never triggers it: enter at `/`, click the sidebar, and every route after that is resolved in the browser. `/api/...` still returns the error envelope - that split is the point of the mount ordering and is now tested.
- **`index.html` was served with no `Cache-Control`, so a deploy took hours to appear.** It is the one unhashed file and the one that names the current bundle; with no header a browser applies its own heuristic - roughly a tenth of the file's age - and keeps running the previous app. Indistinguishable from a deploy that silently failed. Now `no-cache, must-revalidate` (the ETag round trip still happens; guessing does not), while `assets/*` gets `immutable` for a year, which is safe because Vite fingerprints them by content.
- **Live view lagged reality by seconds on an RTSP camera.** Publishing sat behind the inference await, so every frame a viewer saw had already aged by one detection (~616 ms on the board, more with cameras queued behind the single shared inference worker) - and only on ticks where the picture had changed, so the view was smooth while the car park was still and stalled exactly when a car moved. A tick now reads a frame, publishes it, and *starts* a detection without waiting; at most one runs per camera at a time. The overlay trails the picture by up to one detection and says so via `inference_skipped`.
- Stream lag was checked every 150 frames, so the interval between checks stretched in proportion to the fault it exists to catch: 30 s at 5 fps, two and a half minutes at 1 fps. Now checked once a second of wall clock regardless of frame rate. **Measured on the board before and after: worst-case `lag_s` fell from 16.79 s to 3.80 s.**
- `RESYNC_LAG_S` stays at 3.0, now with the measurement behind it. Tightening it to 1.5 was tried on the reference installation and was worse on every axis (lag p99 3.92 → 5.71 s, decode 11.8 → 9.6 fps, resyncs 5 → 13 per five minutes): a reconnect is dead time, so reconnecting sooner lowers throughput, which rebuilds the backlog faster, which triggers the next reconnect sooner. The fix that removes the problem rather than balancing it is `rtsp.Rtsp(fps=10)` on the camera - see `deployment-guide.md`.
- onnxruntime built its session with no `SessionOptions`, so it took every core. On an RTSP camera the four-thread FFMPEG HEVC decoder in the same process is competing for them, and the board sat at 325% of 400% CPU. `INFERENCE_THREADS` (default 2) now bounds it, with `inter_op` pinned to 1.
- New RTSP and MJPEG cameras defaulted to a 3 s poll interval, which is the live-view frame rate - so a stream updated once every three seconds and showed a picture up to three seconds old. Streaming sources now start at 0.2 s. Existing cameras are unchanged; check the field if a stream looks laggy.
- RTSP sessions opened already behind: FFMPEG buffers up to 5 MB / 5 s of stream while identifying it and hands that back afterwards. Bounded to 500 kB / 1 s, with `fflags;nobuffer` and `flags;low_delay`.
- The live view could step backwards a frame. Frame decodes run concurrently in the browser and can finish out of order; a late one both displayed an older picture and revoked the object URL the `<img>` was showing, blanking it. Out-of-order completions are now dropped.
- `average_process_ms` averaged over ticks rather than over detector runs, so a camera whose scene rarely changed reported a fraction of what a detection actually costs. Now averaged over runs.
- Every process restart wrote one phantom `UNKNOWN -> FREE` history row per slot. 96% of the rows on the reference board were these, burying the real transitions. UNKNOWN is a warm-up state, never an observation, and the tracker is now seeded from `parking_slots.current_state`.
- Camera health was recorded only on ticks where the detector ran, so a camera watching a static scene - the case the change gate exists to skip - looked offline while working perfectly. It is now recorded on any frame arriving, and on a time interval rather than a tick count.
- `validate_source_url` classified source types with a chain of ifs, and `esp32cam_stream` had silently landed in the unvalidated branch. Now a table, with a test asserting every enum member is covered.

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
