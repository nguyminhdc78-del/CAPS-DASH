# CAPS-DASH

Car-park administration dashboard for **CAPS** (Camera AI Parking Sensor).

One FastAPI application serves the REST API, a realtime WebSocket channel and
the built Ant Design dashboard — and runs the vehicle-detection loop itself.
Camera images never leave the building.

Qualcomm Hack Challenge 2026 · Nhóm Mặt Trời Nhỏ

---

## What it does

```
ESP32-CAM (ceiling)  ──JPEG over WiFi──>  CAPS-DASH  ──>  browser
                                            │
                          YOLO ─> ground point ─> slot polygon
                                     ─> N-of-M vote ─> SQLite
```

- **Slot occupancy** per floor and per camera, with counts on a lobby kiosk view.
- **Live camera view** with the detected boxes and slot polygons drawn over the frame.
- **ROI editor** to draw parking-slot polygons in the browser; changes apply without a restart.
- **Users and roles** — resident < security < admin, with an audit log of every change.
- **History and statistics** — occupancy over time, derived parking sessions, CSV export.
- **Alerts and operations** — offline cameras, overstays, low disk, backups, retention.

## Requirements

- Python 3.12 or 3.13
- Node.js 22+ (only to build the dashboard)
- Deployment target: aarch64 Linux with glibc 2.28+ (Arduino UNO Q / Debian 10+)

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip
cp .env.example .env                       # then set SECRET_KEY

caps-dash serve --reload
```

- API: <http://localhost:8000/api/health>
- Interactive docs: <http://localhost:8000/docs> (disabled when `APP_ENV=prod`)

Build the dashboard so the backend can serve it:

```bash
cd frontend && npm install && npm run build
```

## Checks

```bash
ruff check .
mypy backend
pytest
```

## Two things worth knowing before changing anything

**Run exactly one worker.** Not a default nobody examined — a correctness
requirement. Each worker would start its own camera loop, so N workers means N
times the requests to every camera, N times the inference, N vote filters
disagreeing about the same slot, and N writers contending for one SQLite file.
The CLI, the Dockerfile and the systemd unit all pin `--workers 1`.

**`UNKNOWN` is not `FREE`.** Until the vote filter has seen a full window, the
system has not established what is in a slot. Reporting it as free would send a
driver to a space nobody has looked at. Never fold `unknown` into a free count.

## Layout

```
backend/caps_dash/
├── config/          settings and fixed domain constants
├── observability/   structured logging, request-id correlation
├── errors/          error codes, exceptions, the response envelope
├── domain/          pure Python geometry and voting — no third-party imports
├── vision/          detectors and frame sources, one per hardware target
├── db/              SQLAlchemy models, session handling, migrations
├── services/        business logic
├── api/             routers and schemas
├── realtime/        WebSocket hub and framing
└── web/             SPA static serving
frontend/            React 19 + TypeScript + Ant Design
docs/                architecture, standards, deployment
plans/               implementation plans
```

`domain/` imports nothing outside the standard library. That is what makes it
testable without a camera and portable to constrained hardware — keep it that way.

## Licence

Source is published as a condition of the competition.

Runtime inference uses **onnxruntime** (Apache-2.0). Ultralytics (**AGPL-3.0**)
is a development-only extra used to export the ONNX model and is never part of
a deployment.
