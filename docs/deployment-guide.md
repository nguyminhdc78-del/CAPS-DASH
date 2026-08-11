# Deployment Guide

Linux-only guide to install, run, and operate CAPS-DASH on Arduino UNO Q or similar aarch64 boards.

## Requirements

- **Hardware**: Arduino UNO Q (QRB2210, aarch64) or equivalent (Debian 10+, 2 GB RAM, 32 GB flash).
- **OS**: Linux (Debian 10+); aarch64 architecture required.
- **Network**: WiFi connection to internal LAN where ESP32-CAM modules are located.
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
| INFERENCE_POOL_SIZE | int | `1` | Thread pool workers for inference. **MUST be 1.** |
| INFERENCE_INPUT_SIZE | int | `640` | YOLO input size (width). Larger = more accurate, slower. |
| DETECTOR_CONFIDENCE | float | `0.25` | Confidence threshold (0–1). Lower catches more, noisier. |
| DEFAULT_POLL_INTERVAL_S | float | `3.0` | Camera poll interval (seconds). |
| DEFAULT_VOTE_WINDOW | int | `5` | Vote filter window size (frames). |
| DEFAULT_VOTE_THRESHOLD | int | `4` | Consensus threshold (N-of-M). |
| CAMERA_TIMEOUT_S | float | `5.0` | HTTP request timeout to camera. |
| CAMERA_FAIL_STREAK_OFFLINE | int | `3` | Mark offline after this many consecutive failures. |
| SNAPSHOT_MAX_AGE_S | float | `10.0` | Reuse cached snapshot in ROI editor for this long. |
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

### CPU
- **Peak (6 cameras, all detecting)**: Unmeasured.
- **Idle (no detections)**: Minimal (poll loop only).

### Storage
All unmeasured. What is known structurally: history rows are written only when a
slot changes state, not per scan, so growth tracks vehicle movements rather than
poll rate; and `BACKUP_KEEP_COUNT` backups are each a full copy of the database,
so backup storage is roughly `keep_count x database size`.

### Network
- **Outbound**: None (inference is local).
- **Inbound**: One ESP32 → app per camera (JPEG ~150 KB, poll interval 3 s = ~50 KB/s max per camera).

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
