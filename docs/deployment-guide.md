# Deployment Guide

Linux-only guide to install, run, and operate CAPS-DASH on Arduino UNO Q or similar aarch64 boards.

## Requirements

- **Hardware**: Arduino UNO Q (QRB2210, aarch64) or equivalent (Debian 10+, 2 GB RAM, 32 GB flash).
- **OS**: Linux (Debian 10+); aarch64 architecture required.
- **Network**: A path from the board to each camera. The reference
  installation is a MaixCam on WiFi (USB-C supplies power only); a WiFi
  ESP32-CAM or an RTSP IP camera on the same LAN also work.
- **No internet**: Images are inference-local; no outbound requirement.

## Installation

### Via Docker (Recommended)

**Prerequisites**:
- Docker 20.10+
- Docker Compose 1.29+

**Steps**:

1. Clone the repository and cd to the project root:
```bash
git clone <repo-url> /opt/caps-dash
cd /opt/caps-dash
```

2. Copy the example environment file and set required variables:
```bash
cp deploy/caps-dash.env.example /etc/caps-dash/caps-dash.env
# Edit /etc/caps-dash/caps-dash.env:
# - SECRET_KEY: Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
# - CORS_ORIGINS: Set to the dashboard's domain (e.g., "https://parkingi.local")
# - APP_ENV: Set to "prod"
```

3. Create data directory:
```bash
sudo mkdir -p /var/lib/caps-dash /var/backups/caps-dash
sudo chown -R 10001:10001 /var/lib/caps-dash /var/backups/caps-dash
sudo chmod 700 /var/lib/caps-dash /var/backups/caps-dash
```

4. Start the application:
```bash
docker compose up -d
```

5. Verify:
```bash
docker compose logs app
curl http://localhost:8000/api/health
```

### Via Systemd (Manual Installation)

**Prerequisites**:
- Python 3.12 or 3.13
- Virtual environment

**Steps**:

1. Install runtime dependencies (Debian/Ubuntu):
```bash
sudo apt update
sudo apt install -y python3.12-venv python3-pip build-essential libatlas-base-dev
```

2. Create service user and directories:
```bash
sudo useradd --system --uid 10001 caps
sudo mkdir -p /opt/caps-dash /var/lib/caps-dash /var/backups/caps-dash
sudo chown -R caps:caps /opt/caps-dash /var/lib/caps-dash /var/backups/caps-dash
sudo chmod 755 /opt/caps-dash
sudo chmod 700 /var/lib/caps-dash /var/backups/caps-dash
```

3. Clone repository:
```bash
cd /opt/caps-dash
git clone <repo-url> .
```

4. Create virtual environment:
```bash
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip setuptools
.venv/bin/pip install -e .  # No [dev] or [vision-dev] in production
```

5. Configure environment:
```bash
sudo cp deploy/caps-dash.env.example /etc/caps-dash/caps-dash.env
sudo chown root:caps /etc/caps-dash/caps-dash.env
sudo chmod 640 /etc/caps-dash/caps-dash.env
# Edit /etc/caps-dash/caps-dash.env with production values
```

6. Install systemd unit:
```bash
sudo cp deploy/caps-dash.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable caps-dash
sudo systemctl start caps-dash
```

7. Verify:
```bash
sudo systemctl status caps-dash
curl http://localhost:8000/api/health
```

## Environment Variables

All configuration from environment; never from `.env` in production. This table is the complete reference.

| Variable | Type | Default | Notes |
|----------|------|---------|-------|
| **Core** |
| APP_ENV | `dev` / `prod` | `dev` | Set to `prod` for deployment. Dev disables OpenAPI docs. |
| APP_NAME | string | `CAPS-DASH` | Application display name. |
| HOST | IP | `0.0.0.0` | Binding address. Use `127.0.0.1` if behind a reverse proxy. |
| PORT | int | `8000` | Listening port. Reverse proxy terminates TLS on 443. |
| **Security** |
| SECRET_KEY | string (32+ bytes) | `change-me` | REQUIRED. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| CORS_ORIGINS | CSV | (empty) | Comma-separated origins allowed (e.g., `https://parking.local,https://parking.local:8080`). Prod rejects `*` or empty. |
| ACCESS_TOKEN_TTL_MIN | int | `15` | JWT access token lifetime (minutes). |
| REFRESH_TOKEN_TTL_DAYS | int | `7` | Refresh token lifetime (days). |
| LOGIN_MAX_ATTEMPTS | int | `5` | Attempts before lockout. |
| LOGIN_WINDOW_S | int | `300` | Window for lockout (seconds). |
| **Storage** |
| DATABASE_URL | string | `sqlite:///data/caps.db` | SQLite path. Use absolute path. |
| BACKUP_DIR | string | `data/backups` | Backup directory. Must exist and be writable. |
| RETENTION_MONTHS | int | `6` | Keep history this long. Trade-off: depth vs. flash wear on embedded. |
| BACKUP_KEEP_COUNT | int | `5` | Retain this many backup files. Older ones are deleted. |
| **Vision** |
| DETECTOR_BACKEND | `onnx` / `ultralytics` / `fake` | `onnx` | ONNX for runtime; ultralytics for dev export; fake for testing. |
| MODEL_PATH | string | `models/yolo-vehicle.onnx` | Path to ONNX model. Must exist. |
| INFERENCE_POOL_SIZE | int | `1` | How many inferences run **at once**. **MUST be 1** - one detector per worker thread, one model in RAM. A correctness constraint, not a tuning knob: if a tick budget does not fit, raise the tick, never this. |
| INFERENCE_THREADS | int | `4` | Threads onnxruntime may use *inside* one inference (`intra_op`; `inter_op` is pinned to 1). `0` lets it take every core. The cap was introduced to stop the detector starving the four-thread FFMPEG HEVC decoder an RTSP camera runs in the same process; the primary path no longer runs that decoder, so the reason is gone. **Measured on the board, 50 runs each: 2 → 837 ms, 3 → 631 ms, 4 → 533 ms per inference.** 4 is what makes 3 cameras fit a 2 s tick. Match it to the host's core count. Distinct from `INFERENCE_POOL_SIZE` - see *Two settings with similar names* in `system-architecture.md`. |
| INFERENCE_INPUT_SIZE | int | `640` | YOLO input size (width). Larger = more accurate, slower. |
| DETECTOR_CONFIDENCE | float | `0.25` | Confidence threshold (0–1). Lower catches more, noisier. |
| DEFAULT_POLL_INTERVAL_S | float | `3.0` | Camera poll interval (seconds), and also the live-view frame rate. Only the default for a **new** camera; stored per camera. Left at 3.0 for a generic slow HTTP camera - the MaixCam runs at 2.0, set on its own row rather than by retuning the global for one device. |
| DEFAULT_VOTE_WINDOW | int | `5` | Vote filter window size (frames). |
| DEFAULT_VOTE_THRESHOLD | int | `4` | Consensus threshold (N-of-M). |
| CAMERA_TIMEOUT_S | float | `5.0` | HTTP request timeout to camera. Guards against a *wedged* camera, not a slow one, so keep headroom over the **worst** case rather than tuning it to the median. Measured p90 on the reference WiFi link is 75 ms, so the usual p90 x 3 rule would give 0.23 s - far too tight for a link that has shown 251 ms spikes. `CAMERA_FAIL_STREAK_OFFLINE` does the real offline detection; this only has to catch a server that never answers. |
| CAMERA_FAIL_STREAK_OFFLINE | int | `3` | Mark offline after this many consecutive failures. |
| SNAPSHOT_MAX_AGE_S | float | `10.0` | Reuse cached snapshot in ROI editor for this long. |
| MIN_INFERENCE_INTERVAL_S | float | `0.0` | Floor on the gap between two detector runs, independent of the poll interval. `0` disables it. **Inert at any tick ≥ 1.5 s** - it gates only change-triggered runs, whose spacing is already bounded by the tick - so it is off by default now that the primary path polls. Set it (1.5 was measured good) on a streaming camera, where a fast tick would otherwise run the detector back to back. |
| MOTION_FORCE_INTERVAL_S | float | `30.0` | Inference runs anyway this often even when the change gate sees nothing, so slow drift (dusk, a light switched on, auto-exposure creeping) cannot keep the detector asleep. This is the **ceiling on how long the system may be wrong** when the gate misses a real change. Raised from 10 s when the tick went from 0.2 s to 2 s: at 10 s every camera force-infers every 5 ticks and competes with genuine change-triggered runs. A deliberate trade of detection latency for headroom, not a free win. |
| MOTION_CHANGE_THRESHOLD | float | `8.0` | Mean absolute difference (64x48 greyscale sample, 0-255) below which a frame is treated as unchanged and skipped. Calibrated against the sensor noise floor, not the tick - see the exposure-lock note under "Camera notes". |
| **Reporting** |
| HISTORY_DEFAULT_SPAN_DAYS | int | `7` | Default history query range. |
| HISTORY_MAX_SPAN_DAYS | int | `92` | Maximum range (cap unbounded queries on shared hardware). |
| AGGREGATION_INTERVAL_S | float | `600.0` | How often hourly aggregation job runs (seconds). |
| MAX_EXPORT_ROWS | int | `100000` | CSV export row limit. Larger requests are rejected. |
| **Alerts** |
| OVERSTAY_HOURS | float | `12.0` | Alert if car parked > this many hours. |
| DISK_LOW_PERCENT | float | `0.10` | Alert if <10% free. Halved for CRITICAL. |
| DISK_LOW_MIN_FREE_MB | int | `256` | Alert if <256 MiB free (absolute floor for small cards). |
| ALERT_COOLDOWN_S | float | `3600.0` | Minimum time between duplicate alerts (same type, entity). |
| **Realtime** |
| WS_AUTH_DEADLINE_S | float | `5.0` | WebSocket must auth within this time. |
| WS_HEARTBEAT_S | float | `20.0` | Heartbeat interval (seconds). |
| WS_MAX_VIEWERS_PER_CAMERA | int | `4` | Max concurrent viewers per camera. |
| WS_MAX_CONNECTIONS_TOTAL | int | `16` | Max concurrent WebSocket connections across all cameras. |
| WS_FIRST_FRAME_MAX_AGE_S | float | `30.0` | Serve cached frame if < this old. |
| **Web** |
| SPA_DIST_DIR | string | `frontend/dist` | Path to built SPA (index.html, assets). |
| **Observability** |
| LOG_LEVEL | string | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR). |
| LOG_JSON | bool | `True` | Log in JSON format (structured logs). |

### Example Production `.env`

```bash
# Core
APP_ENV=prod
SECRET_KEY=<generated-48-byte-secret>
CORS_ORIGINS=https://parking.local

# Storage
DATABASE_URL=sqlite:////var/lib/caps-dash/caps.db
BACKUP_DIR=/var/backups/caps-dash
RETENTION_MONTHS=6

# Vision
DETECTOR_BACKEND=onnx
MODEL_PATH=/app/models/yolo-vehicle.onnx
INFERENCE_POOL_SIZE=1
DETECTOR_CONFIDENCE=0.25

# Alerts
OVERSTAY_HOURS=12.0
DISK_LOW_PERCENT=0.10
DISK_LOW_MIN_FREE_MB=256
```

## Reverse Proxy (nginx)

The app binds `127.0.0.1:8000` inside a container or behind systemd. Nginx terminates TLS and proxies HTTP.

### Configuration Example

```nginx
upstream caps_dash {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl http2;
    server_name parking.local;

    ssl_certificate /etc/letsencrypt/live/parking.local/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/parking.local/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://caps_dash;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # WebSocket endpoint — critical headers
    location /ws/ {
        proxy_pass http://caps_dash;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Don't buffer the stream
        proxy_buffering off;
        
        # Timeouts high enough for heartbeat (20 s)
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name parking.local;
    return 301 https://$server_name$request_uri;
}
```

See `deploy/nginx-reverse-proxy.conf.example` for the full template.

## Backup & Restore

### Backup (Manual or Automated)

SQLite 3 has an online backup API that creates a snapshot while the database is live. Backup files are valid databases.

**Manual backup**:
```bash
docker compose exec app caps-dash backup /var/backups/caps-dash/caps-$(date +%Y%m%d-%H%M%S).db
# OR (systemd)
sudo -u caps /opt/caps-dash/.venv/bin/caps-dash backup /var/backups/caps-dash/caps-$(date +%Y%m%d-%H%M%S).db
```

**Automated (cron)**:
```bash
0 2 * * * caps /opt/caps-dash/.venv/bin/caps-dash backup /var/backups/caps-dash/caps-$(date +\%Y\%m\%d-\%H\%M\%S).db
```

**Retention**: Backups are not automatically deleted; manage manually or with a cleanup script. The app respects `BACKUP_KEEP_COUNT`; backups older than the Nth most recent are removed when the admin triggers a backup from the UI.

### Restore from Backup

**Stop the app**:
```bash
docker compose down
# OR (systemd)
sudo systemctl stop caps-dash
```

**Restore**:
```bash
# Backup the current database first
sudo cp /var/lib/caps-dash/caps.db /var/lib/caps-dash/caps.db.old

# Replace with backup
sudo cp /var/backups/caps-dash/caps-2026-08-11-120000.db /var/lib/caps-dash/caps.db
sudo chown caps:caps /var/lib/caps-dash/caps.db
sudo chmod 600 /var/lib/caps-dash/caps.db
```

**Start the app**:
```bash
docker compose up -d
# OR (systemd)
sudo systemctl start caps-dash
```

**Verify**:
```bash
curl http://localhost:8000/api/health
```

## Upgrade & Migration

### Pre-Upgrade Checklist

1. Backup current database: `caps-dash backup ...`
2. Note current version: Check `docker inspect` or `pip show caps-dash`.
3. Test on staging if available.

### Upgrade Steps

**Docker**:
```bash
cd /opt/caps-dash
git fetch origin main
git checkout main
docker compose down
docker compose build --no-cache
docker compose up -d
# Migrations run automatically via entrypoint
```

**Systemd**:
```bash
cd /opt/caps-dash
sudo systemctl stop caps-dash
git fetch origin main
git checkout main
.venv/bin/pip install -e . --upgrade
.venv/bin/caps-dash migrate  # Run manually before starting
sudo systemctl start caps-dash
```

### Post-Upgrade

1. Monitor logs: `docker compose logs -f app` or `sudo journalctl -u caps-dash -f`.
2. Check health: `curl http://localhost:8000/api/health`.
3. Test UI: Login, navigate pages, verify data integrity.
4. Roll back if needed: Restore database backup and git checkout previous version.

## Single Worker Constraint

**The constraint is enforced in three places:**

1. **Dockerfile** (CMD):
```dockerfile
CMD ["uvicorn", "caps_dash.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

2. **Systemd** (ExecStart):
```ini
ExecStart=/opt/caps-dash/.venv/bin/uvicorn caps_dash.main:app --host 127.0.0.1 --port 8000 --workers 1
```

3. **Runtime guard** (app_factory.py):
If `WEB_CONCURRENCY` env var or `--workers` flag implies > 1 worker in prod, the app refuses to start with a clear error message.

**Why not just a comment?** Because a comment is not a constraint. Someone running behind a load balancer might accidentally set `--workers 4` to "tune" performance. The guard catches this.

## Monitoring & Observability

### Logs
- **Format**: JSON (structured) via structlog.
- **Level**: INFO by default; DEBUG for troubleshooting.
- **Output**:
  - Docker: `docker compose logs app` (stdout).
  - Systemd: `sudo journalctl -u caps-dash` (persistent only if configured).
- **No persistent disk log**: By design; flash wear is a concern on embedded devices.

### Healthcheck
`GET /api/health` returns JSON status. Docker Compose includes a HEALTHCHECK directive that calls this every 30 s (timeout 5 s, 3 retries).

### Metrics (Not Yet Implemented)
Future versions might expose Prometheus metrics at `/metrics`. Currently, monitoring is manual: check logs, inspect database, observe CPU/memory via `top`.

## Performance & Resource Usage

### Image Size
- **Approximate**: Unmeasured on target (placeholder until soak test).
- **Target**: < 700 MB (onnxruntime + opencv-headless dominate).
- **Mitigation**: Multi-stage Dockerfile; `opencv-python-headless` (no GUI libraries); slim base; no build toolchain in runtime stage.

### Memory
- **Baseline (startup)**: Unmeasured.
- **Soak test (8h, 6 cameras)**: Unmeasured.
- **Target**: RSS growth < 5% per 8 hours.
- **To be recorded after phase 14, step 13**.

### CPU and inference latency — measured

Measured 2026-08-12 on the real board: Arduino UNO Q, Debian 13 (trixie),
aarch64, 4 cores, 1.7 GB RAM, glibc 2.41, Python 3.13.5, onnxruntime 1.28.0,
CPU execution provider. Ten runs of the shipped `yolo-vehicle.onnx`
(YOLO26-nano, 640x640), warm session:

| | ms |
|---|---|
| fastest | 502 |
| median | 616 |
| slowest | 1440 |

onnxruntime uses every core by default, so this figure already has all four.
Available providers on this SoC are `AzureExecutionProvider` and
`CPUExecutionProvider` - there is no NPU path, as predicted in
`models/README.md`.

**Inference cost alone does NOT bound camera count, because most frames never
reach the detector.** Parked cars do not move, so the change gate
(`vision/frame_change_gate.py`) skips inference on frames identical to the
last one it looked at. Measured on the reference installation with a settled,
exposure-locked camera: **11% of frames were inferred**, the rest cost 2.7 ms
each to compare and skip.

The arithmetic that matters is therefore per-camera *average* cost, not
per-tick worst case:

```
inference when it runs      ~ 616 ms   (fastest 502, slowest 1440)
fraction of frames inferred    ~ 11%   (static car park, exposure locked)
average cost per frame       ~  70 ms  inference + 2.7 ms gate + ~70 ms decode
```

Two caveats that decide whether that 11% holds:

- **Lock the camera's exposure** (see below). Unlocked, the measured skip rate
  collapses and inference fires on most frames - which is what produces the
  pessimistic "roughly five cameras" figure this section used to quote.
- **A busy site infers more.** 11% is a car park where nothing moves between
  arrivals. A thoroughfare with constant foot traffic approaches 100%, and
  then inference really is the bound: `3000 ms / 616 ms` is about five
  cameras at a 3 s poll, before the API, SQLite and the SPA get any CPU.

Practical guidance:

- Size for the busy case if the view has through-traffic, and for the skip
  rate if it does not. Watch `process_ms` on `/api/cameras` and the
  `inference_skipped` flag in the WebSocket header to see which you have.
- The 1440 ms slowest run matters as much as the median: a tick occasionally
  takes more than twice the typical time, so leave slack rather than tuning
  the poll interval to the median.
- More than six cameras is untested on this hardware at this input size.

### ESP32-CAM - measured, and still supported

An ESP32-CAM satisfies the same one-JPEG-per-GET contract as the MaixCam
described below, so everything here still applies if you run one. It is no
longer the reference camera, but nothing about it stopped working.

Measured 2026-08-12 against the real module (AI-Thinker ESP32-CAM, OV3660,
VGA 640x480, RSSI -42 dBm) from the UNO Q:

| | ms/frame | fps |
|---|---|---|
| `GET /anh` per frame, one connection each | 53 | 18.9 |
| `GET /stream` (MJPEG, held open) | 46 | 21.7 |

End to end through the app, to a WebSocket viewer, with the change gate on:

| source | fps | frames inferred |
|---|---|---|
| `esp32cam_http` | 6.2 | 11% |
| `esp32cam_stream` | 8.7 | 11% |

The stream wins by 1.4x, and not for the reason the raw numbers suggest - the
two transports are within 15% of each other. It wins because `read()` stops
waiting on the network: a polling source spends ~53 ms of every tick before
any work begins, while the stream source returns the newest frame from memory.

**Lock the camera's exposure.** With `aec`, `agc` and `awb` on automatic, the
sensor hunts continuously and the whole frame shifts brightness several levels
between frames. Measured noise was then 7.5 mean absolute difference (peaks of
38), against roughly 13 for a car occupying a sixth of the frame - the change
gate cannot separate those, and inference fires on most frames. With exposure
locked and settled, noise falls to 0.8 (peak 3.3) and the same car still reads
13, which is the margin `MOTION_CHANGE_THRESHOLD` sits in:

```
curl "http://<camera>/control?var=aec&val=0"
curl "http://<camera>/control?var=agc&val=0"
```

Or use the dashboard: the camera row has a settings panel with a single
exposure-lock switch. The app remembers the setting and re-applies it whenever
a camera worker starts, because the ESP32 keeps it in RAM only.

**Leave white balance (`awb`) alone.** Locking it too moves noise by 0.1
against a threshold of 8 - nothing - while turning every frame green, and the
detector was trained on normally-coloured images.

Allow a minute for the sensor to settle before measuring anything.

**Check which sensor is fitted; do not assume.** `/status` reports
`sensor_pid` - `0x3660` (13920) is an OV3660, `0x26` an OV2640. They need
different defaults: the OV3660 is oversaturated and slightly dark out of
reset, and the firmware applies `saturation=-2, brightness=1` for it, as
Espressif's own reference example does. Assuming the wrong one is what
produced a strongly green-cast picture on this installation.

### MaixCam HTTP snapshot - the primary path

The reference camera is a Sipeed MaixCam (`maixcam-1677`, riscv64, GC4653
sensor) serving one JPEG per `GET /snapshot` on port 8080. The backend polls it
through `Esp32CamHttpSource` at **2.0 s** - the same source type an ESP32-CAM
uses, because the contract is identical.

**It is on WiFi, not USB-C.** This was assumed the other way round during
planning and measured on 2026-08-12: `usb0` exists and holds `10.22.120.1`, but
it is NO-CARRIER/DOWN, because the USB-C cable supplies power only. The camera
reaches the board over `wlan0` on a DHCP address from the same hotspot the
board is on. **The camera and the board therefore talk over exactly the link
the RTSP figures below were measured on** - it did not get faster. The
migration's reason (CPU and simplicity) is unaffected; the claim that the link
improved was simply wrong.

Because the address is DHCP, it moves. Find it again from the hotspot's client
list, or by `ssh -i ~/.ssh/maixcam root@<ip> hostname` until one answers
`maixcam-1677`.

Measured on the device, 2026-08-12:

| | |
|---|---|
| Camera hardware | 1 CPU core, 128 MB RAM, CPython 3.11.6, **no systemd** |
| Encode path | `img.to_jpeg().to_bytes()` returns real JPEG bytes |
| JPEG size | 35.5 – 41.5 KB at 640x480 (mean 37.4 KB) |
| Capture + encode | 25 ms per frame |
| Sensor open | 1034 ms, and the first frame back is unconverged |
| Latency from the board | min 45 / mean 68 / **p90 75** / max 134 ms over 20 polls |

The JPEG sits ~70x above `MIN_BODY_BYTES` and ~48x below `MAX_BODY_BYTES`, so
the guard bounds need no adjustment.

`CAMERA_TIMEOUT_S` is deliberately **not** p90 x 3 (which would be 0.23 s). A
timeout guards a wedged server, not a slow one, and this WiFi link has shown
251 ms spikes; 5.0 keeps ~40x headroom over the measured p90 while
`CAMERA_FAIL_STREAK_OFFLINE=3` does the actual offline detection.

Install, autostart and rollback: [`deploy/maixcam/README.md`](../deploy/maixcam/README.md).
The device script itself is version-controlled at
`deploy/maixcam/http_snapshot_main.py`.

Camera row:

| field | value |
|---|---|
| `source_type` | `esp32cam_http` (labelled "HTTP snapshot (polled)" in the UI) |
| `source_url` | `http://maixcam-1677.local:8080/snapshot` — **by name, not by IP**. The address is DHCP and it moves (`.90` one evening, `.244` the next morning, with the system dead in between until someone looked). The board resolves mDNS; the extra lookup measured 208 ms mean against 196 ms by raw IP. |
| `poll_interval_s` | `2.0` |

**The 2 s cadence now fits - measured, not assumed.** The tick is also the
live-view frame rate and the inference budget. With `INFERENCE_THREADS=4` an
inference costs **533 ms** on the board, so three cameras is 1.60 s against a
2.0 s tick, with 400 ms spare. At the old `INFERENCE_THREADS=2` it was 837 ms
each, 2.51 s for three, and it did **not** fit - which would have forced the
tick to 2.5-3.0 s and slowed the live view with it. Never raise
`INFERENCE_POOL_SIZE` to buy headroom; raise the tick.

**Measured in production, 2026-08-12**, two cameras at 2.0 s with
`INFERENCE_THREADS=4`:

| | |
|---|---|
| Board load average | **0.38** — against 0.83 for the tuned RTSP configuration |
| Polls | 77 in 2 minutes, **0 failures** |
| Stagger | first ticks 0.927 s apart (theory 1.000) |
| Camera autostart | survives a power cycle, launcher-started, verified |

**Still unmeasured:** three cameras at 2.0 s (only two devices exist), so the
3 × 533 ms = 1.60 s budget is arithmetic over a measured per-inference cost
rather than a measured three-camera run. No soak test, no accuracy figure. Do
not quote a number that is not labelled measured.

**The camera reports its own staleness.** The device serves `503` if its
capture thread has not produced a frame within 10 s, rather than serving the
last good picture behind a `200`. That turns a dead capture thread from an
invisible failure - a healthy-looking camera showing a frozen scene - into
three consecutive read failures and an offline alert.

**The snapshot endpoint is unauthenticated and has no TLS, and it is on WiFi.**
The original plan justified the missing auth by the link being point-to-point.
That justification does not survive the measurement above: the camera is on the
same WPA2 hotspot as the board, so **anyone with the hotspot password can fetch
a live camera frame.**

Bounded, today, by the fact that the hotspot carries two devices and is run by
the camera's owner - but bounded by a WiFi password, not by topology, which is
a weaker guarantee than the one originally claimed. The server binds `0.0.0.0`
(it must; the DHCP address moves) and prints every address it is reachable on
at startup, so the exposure is visible rather than assumed.

**Before putting this camera on a shared or larger network, put authentication
in front of it.** Do not treat the current posture as a default that travels.

**Known limitation, pre-existing:** `source_url` is operator-supplied and
fetched by the server. Scheme and hostname are validated but the host is not
restricted, so an admin can point a camera row at an internal address (SSRF).
Not introduced by this path and not fixed here - recorded so it is not
rediscovered as news.

### Why RTSP is not the primary path

**Not because it did not work.** It works, it is tested, and it is still a
supported `source_type`. It stopped being the shape the system is tuned for
because of **CPU and simplicity**: an in-process four-thread FFMPEG HEVC
decoder cost 325% of 400% available CPU and forced every other tunable to bend
around it. Polling a JPEG decodes one small still per tick instead.

**Read the lag numbers below with their link in mind.** They were measured over
a **Windows ICS hotspot at 8-251 ms RTT (mean 94 ms)** - and the snapshot path
measured on 2026-08-12 runs over **that same hotspot**, because the MaixCam is
on WiFi, not the USB-C link the plan assumed. So the link did not change; only
what is sent over it did. HTTP snapshot polling measures 45-134 ms per fetch
(p90 75) on that link, which is fine for one 37 KB still every 2 s and says
nothing about what a 30 fps HEVC stream costs on it.

These figures are **link-specific** - they say what RTSP costs over a busy
2.4 GHz hotspot, not what it costs everywhere, and they are not evidence that
RTSP is unworkable. The honest statement remains: snapshot polling was chosen
for CPU and simplicity.

### If you must use an RTSP camera - measured

Measured 2026-08-12 against an action camera (640x480 HEVC, 30 fps) joined to
the same hotspot as the board. Every number here is preserved from when RTSP
was the primary path; it cost real hours on real hardware and remains the best
guidance for anyone running an IP camera.

**The source holds ONE session open and drains it on a thread.** Four designs
were tried; the discarded ones all look reasonable until measured:

| design | result |
|---|---|
| one frame per worker tick, session held open | 5.4 s late after 6 s; 28.6 s late after 30 s |
| reader thread draining continuously | correct on a healthy link; 40 s late on a broken one |
| connect, grab one frame, disconnect | lag bounded, but killed the camera - see below |
| **one session, drained, resynced on lag** | what ships |

An RTSP capture yields frames oldest-first and never skips, so a consumer
slower than the camera leaves the rest queued and the lag grows a second per
second, without bound. A draining thread fixes that whenever the link can
carry the stream.

**Do not open a session per frame.** It bounds lag by construction - a new
session starts at the live edge - and it worked, at about 3.1 s a frame. It
also opened roughly twenty RTSP sessions a minute, and the reference camera's
session table could not take it. FFMPEG eventually reported

```
method PLAY failed: 454 Session Not Found
```

the server handing out a session id and immediately forgetting it. A raw
DESCRIBE still returned 200 OK at the time and ping was 24 ms with no loss, so
the camera was reachable and talking - it had simply been worn down. Recovery
needs the camera power-cycled; leaving and re-entering its streaming screen
was not enough.

**A bad link is handled, not designed around.** This one measured 406-1052 ms
round trip with 20% packet loss and 0.13 Mbit/s flowing at one point, and
24 ms with no loss an hour later - transient, not a property of the site. When
`StreamLagTracker` reports the picture more than `RESYNC_LAG_S` (3 s) behind,
the session is rebuilt once, which puts it back at the live edge without
returning to a session per frame. `rtsp_stream_lag` logs `decode_fps` and
`lag_growth_s` so the link's condition is visible rather than guessed at.

**The reference link cannot carry the reference camera.** Measured 2026-08-12:
a MaixCam sending 640x480 HEVC at 30 fps over a Windows ICS hotspot (ping
8-251 ms, mean 94) against a board that decodes ~12 of those 30 frames a
second. The backlog sits on the camera's side of the TCP connection, so
nothing on the board can discard it, and a reconnect is the only way back to
the live edge.

**Tightening `RESYNC_LAG_S` makes this worse, not better.** Two five-minute
windows on that installation:

| RESYNC_LAG_S | decode fps | lag p90 | lag p99 | resyncs |
|---|---|---|---|---|
| **3.0** | 11.8 | **1.84 s** | **3.92 s** | **5** |
| 1.5 | 9.6 | 2.51 s | 5.71 s | 13 |

A reconnect is dead time - a handshake and a wait for a keyframe, during which
nothing arrives. Reconnecting sooner spends more of the link on handshakes,
which lowers throughput, which rebuilds the backlog faster, which triggers the
next reconnect sooner. Leave the threshold wide enough that the loop does not
close on itself.

**The fix is to ask the camera for fewer frames**: `rtsp.Rtsp(fps=10)` in the
MaixCam's `rtsp_stream` app (it defaults to `fps=30`, H265, and the stock app
passes no arguments at all - `RTSP_STREAM_H264` is not offered by that MaixPy
build, so frame rate is the only lever). At a rate the link can carry, no
backlog forms and no resync is needed. Watch `rtsp_stream_failed` for `454
Session Not Found` if resyncs ever get much more frequent - that is the
camera's session table wearing out, and it needs a power cycle to recover.

**Lag is checked on wall clock, not every N frames.** Reporting every 150
frames stretched the gap between checks in exact proportion to the fault it
exists to catch - the reader falls behind because frames arrive slower than
the camera sends them, so at 5 fps that interval was 30 s and at 1 fps two and
a half minutes. The picture could be a minute stale before anything looked at
it. The tracker now reports once a second whatever the frame rate, so the
worst case is `RESYNC_LAG_S` plus about a second.

**The live view does not wait for the detector.** A tick reads a frame,
publishes it and starts a detection without awaiting it. Publishing used to
sit behind the inference await, which added a whole detection - ~616 ms here,
more with cameras queued behind the one shared inference worker - to the age
of every frame a viewer saw, and only on the ticks where the picture had
changed. The symptom was distinctive: smooth while the car park was still,
stalling exactly when a car moved. See `system-architecture.md`.

**Poll interval is the live-view frame rate.** `poll_interval_s` sets how
often a frame reaches the browser. A polled camera pays a request, a transfer
and a decode every tick, so it starts at **2 s** - and 2 s is therefore the
live view an operator should expect from one, which is intended behaviour, not
a bug. On a stream the newest frame is already decoded in memory and a tick
costs almost nothing, so leaving it at seconds means a view that updates that
slowly and shows a picture that old. New RTSP and MJPEG cameras therefore
start at **0.2 s**. The field is shown in the form and can be changed; an
existing camera keeps whatever it was created with - check it first if a
stream looks laggy.

**Set `MIN_INFERENCE_INTERVAL_S` if you run an RTSP camera.** It is a
**process-wide** setting, not a per-camera field - there is no column for it on
the camera row - so it applies to every camera on the board. It now defaults to
`0`,
because it is inert at a polled camera's tick - it gates only change-triggered
runs, whose spacing is already bounded by a tick of 2 s. On a fast streaming
tick it is what makes that tick affordable: the tick rate no longer drives the
detector, but without a floor the detector still runs back to back on a scene
that keeps changing. `1.5` was enough here to take the board from 3.54 load
average to 0.83 - **measured at the 0.2 s tick**, which is the only place that
number applies.

Note the pairing this leaves in the shipped defaults: new `rtsp` and
`esp32cam_stream` cameras still start at a 0.2 s tick while the floor that made
that tick affordable is off. It is inert for polled cameras and harmless until
you actually add a streaming camera - at which point set it, and understand it
will also apply to the polled ones (where it changes nothing, since their tick
already exceeds it).

**FFMPEG is told not to hold frames back.** `probesize` and `analyzeduration`
default to 5 MB and 5 s, and everything read while FFMPEG works out what the
stream is gets buffered and handed back afterwards - so a session is born
seconds in arrears. They are cut to 500 kB / 1 s, with `fflags;nobuffer` and
`flags;low_delay`. None of these discard a frame; they only stop frames being
held. If a camera ever fails to be identified at all (an unopenable capture on
a URL that a raw DESCRIBE answers), these limits are the first thing to raise.

**A camera that refuses the connection is not broken.** Action cameras run
their RTSP server only while the streaming screen is open, and the dashboard
now says so in as many words: *"refused the connection - it is on the network
but not streaming"*. The reader retries every 2 s in that state rather than
backing off, so a picture appears promptly once the camera is switched on.

### Idle CPU
Minimal - the poll loop only. Nothing is encoded and no frame is published
unless somebody is watching a live view.

### Storage
All unmeasured. What is known structurally: history rows are written only when a
slot changes state, not per scan, so growth tracks vehicle movements rather than
poll rate; and `BACKUP_KEEP_COUNT` backups are each a full copy of the database,
so backup storage is roughly `keep_count x database size`.

### Network
- **Outbound**: None (inference is local).
- **Inbound**: One camera → app per camera. Structural, not measured: a JPEG of
  ~150 KB at the 2.0 s primary tick is ~75 KB/s per camera; at the 3 s generic
  default, ~50 KB/s. Both are upper bounds - the frames measured from the
  MaixCam-shaped path are ~10 KB, an order of magnitude below this.

## Troubleshooting

### App Won't Start
**Check**:
1. Logs: `docker compose logs app` or `sudo journalctl -u caps-dash`.
2. Environment: `APP_ENV=prod` with invalid SECRET_KEY? Prod validates strictly.
3. Port: Is 8000 already in use? `sudo ss -tlnp | grep 8000`.
4. Database: Is `DATABASE_URL` path writable? `ls -la /var/lib/caps-dash/`.

### Camera Offline
**Check**:
1. Network: Can the app reach the camera? `curl http://<camera-ip>/capture`.
2. Camera settings**: Source URL correct in the UI?
3. Logs**: `last_error` field on the Camera row.

### WebSocket Not Streaming
**Check**:
1. Browser console: Any errors?
2. Nginx logs: `proxy_pass`, `Upgrade` headers correct?
3. Firewall**: Is port 443 (HTTPS) or 8000 (dev) open?

### Disk Running Out
**Check**:
1. Backup location: `du -sh /var/backups/caps-dash`.
2. Database size: `du -sh /var/lib/caps-dash/caps.db`.
3. Purge old data: Admin → System → Purge retention (delete records > 6 months old).

## Soak Test (Performance Verification)

**Goal**: Record memory growth, detect leaks, verify graceful shutdown.

**Setup**:
- Run app with 4 fake cameras (no real hardware needed).
- Open browser; navigate to live view (one viewer).
- Keep running for 8 hours.

**Record**:
- RSS at start (empty app).
- RSS at end (after 8h).
- CPU usage (peak, steady-state).
- Any error messages in logs.
- Successful shutdown on SIGTERM.

**Success criteria**:
- RSS growth < 5% from start to end.
- No "objectURL leaked" or "subscriber queue overflow" warnings.
- No "Task was destroyed" lines on shutdown.
- Graceful exit within 20 seconds of SIGTERM.

**To be recorded in this document after completion.**

## Licence & Dependencies

**Runtime (deployed in image)**:
- Apache-2.0: onnxruntime, numpy, opencv-python-headless.
- MIT: FastAPI, Pydantic, SQLAlchemy, React, Ant Design, others.

**Development-only (not deployed)**:
- AGPL-3.0: ultralytics (used only to export ONNX; never deployed).

CI asserts that `pip freeze` inside the built image contains no AGPL code.

## Support & Escalation

- **Logs**: Always collect with `docker compose logs app` or `journalctl`.
- **Database**: Backup before any manual intervention; restore if unsure.
- **Configuration**: Environment-based; no hardcoded values in code.
- **Scaling**: If 6-camera ceiling is insufficient, a multi-process refactor is required (future work).
