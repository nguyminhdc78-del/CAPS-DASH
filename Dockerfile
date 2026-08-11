# Multi-stage build. The `web` stage builds the SPA; the board never runs
# Node - it only ever receives the built `dist`. `runtime` installs backend
# dependencies WITHOUT the `vision-dev` extra, so the AGPL-3.0 `ultralytics`
# package (dev-only, used to export the .onnx model on a developer machine)
# never enters this image - `.github/workflows/ci.yml` asserts this too.
#
# Target: linux/arm64 (Arduino UNO Q, QRB2210, glibc 2.28+). Built via
# buildx/QEMU in `.github/workflows/docker.yml`; both base images below
# publish official arm64 manifests.

# --- web: build the SPA -------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# VITE_* build-time env, if any, would go here as ARG/ENV; there are none
# today - the SPA talks to whatever origin served it.
RUN npm run build

# --- runtime: backend + the built SPA ------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Unbuffered stdout so structlog's JSON lines reach `docker logs` promptly
# (matters for the healthcheck and for `journalctl`-style tailing);
# dontwritebytecode keeps the image free of stray .pyc files from the
# `caps-dash migrate` run the entrypoint performs on every container start.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# `data/`, `models/`, `backups/` are the only paths the app ever writes to
# (or is even asked to - `models/` is normally a read-only bind mount, but
# owning it too costs nothing and avoids a second special case). Created
# under a non-root user from the start rather than chown'd after the fact.
RUN useradd --system --create-home --uid 10001 --shell /usr/sbin/nologin caps \
    && mkdir -p /app/data /app/models /app/backups \
    && chown -R caps:caps /app

WORKDIR /app

# Dependencies before source: this layer only invalidates when pyproject.toml
# changes, so an ordinary code change does not re-run the (comparatively
# slow) onnxruntime/opencv-headless install.
COPY pyproject.toml ./
COPY README.md ./
COPY backend/ ./backend/
# `pip install .` (no `-e`, no `[dev]`, no `[vision-dev]`): a normal,
# non-editable install of exactly the runtime dependency set.
RUN pip install .

COPY alembic.ini ./
COPY models/ ./models/
COPY deploy/docker-entrypoint.sh deploy/healthcheck.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/healthcheck.sh

# The board never builds the frontend - only ever receives this directory.
COPY --from=web /web/dist ./frontend/dist

ENV SPA_DIST_DIR=/app/frontend/dist \
    MODEL_PATH=/app/models/yolo-vehicle.onnx \
    DATABASE_URL=sqlite:////app/data/caps.db \
    BACKUP_DIR=/app/backups

USER caps
EXPOSE 8000

# Readiness, not liveness: a container that is up but cannot reach its own
# database is not something an orchestrator should call "healthy" yet.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/usr/local/bin/healthcheck.sh"]

# `caps-dash migrate` runs here, once, before `exec "$@"` hands off to the
# CMD below - never at import time, never inside the app's own startup path
# (see `cli/migrate_command.py`'s docstring for why: an unattended restart
# must never be able to silently rewrite the schema of a running system).
ENTRYPOINT ["docker-entrypoint.sh"]

# ONE worker. Not a tuning knob: each worker would start its own camera
# supervisor, duplicating every ESP32-CAM request, every inference run, and
# racing to write the same SQLite file. `app_factory.py`'s runtime guard
# (`WEB_CONCURRENCY`) is defence in depth for this same rule, not a
# replacement for hard-coding it here.
CMD ["uvicorn", "caps_dash.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
