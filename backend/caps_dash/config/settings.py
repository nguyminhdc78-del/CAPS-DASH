"""Application settings.

Every tunable lives here. Nothing is hardcoded at its point of use - the
reference project scattered constants across modules and shipped an admin
password in source, which is exactly what this module exists to prevent.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# Placeholder values that must never survive into production.
_UNSAFE_SECRETS = {"", "change-me", "changeme", "secret", "caps"}

# HS256 signs with SHA-256, so a key shorter than the 32-byte digest reduces
# the effective security of every token. RFC 7518 section 3.2.
MIN_SECRET_KEY_BYTES = 32


class Settings(BaseSettings):
    """Runtime configuration, loaded from process env then `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Environment -------------------------------------------------------
    app_env: Literal["dev", "prod"] = "dev"
    app_name: str = "CAPS-DASH"
    host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is intended on the board
    port: int = 8000

    # --- Security ----------------------------------------------------------
    secret_key: SecretStr = SecretStr("change-me")
    # `NoDecode` is load-bearing, not decoration. Without it pydantic-settings
    # JSON-decodes every complex-typed field as it reads the `.env` file -
    # before any validator runs - so the documented
    # `CORS_ORIGINS=https://parking.local` raises SettingsError and the app
    # refuses to start. In prod the field is also mandatory, so following the
    # shipped deployment guide would have been unbootable.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7
    login_max_attempts: int = 5
    login_window_s: int = 300

    # --- Storage -----------------------------------------------------------
    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'caps.db'}"
    backup_dir: Path = REPO_ROOT / "data" / "backups"
    # 6 months, not 12: the deployment host is an Arduino UNO Q writing to
    # flash, where both capacity and write endurance are limited.
    retention_months: int = 6
    # Backups are cheap individually but each is a full copy of the live
    # database; unbounded retention would itself become a flash-capacity
    # problem. Five gives a week or two of daily backups without babysitting.
    backup_keep_count: int = 5

    # --- Vision pipeline ---------------------------------------------------
    detector_backend: Literal["onnx", "ultralytics", "fake"] = "onnx"
    model_path: Path = REPO_ROOT / "models" / "yolo-vehicle.onnx"
    # One worker, one model in RAM. On a QRB2210 sharing its CPU with the API,
    # the SPA and SQLite, this is the correct default rather than a placeholder.
    inference_pool_size: int = 1
    inference_input_size: int = 640
    detector_confidence: float = 0.25
    # The reference project's own config notes record that 1.0s x 3 flickered
    # and that a real deployment wants roughly 3.0s x 4.
    default_poll_interval_s: float = 3.0
    default_vote_window: int = 5
    default_vote_threshold: int = 4
    camera_timeout_s: float = 5.0
    camera_fail_streak_offline: int = 3
    # Parked cars do not move, so most frames are the same picture and
    # running the detector on them re-derives an unchanged answer for ~616 ms
    # of a shared four-core board. A frame is only inferred when it differs
    # from the last inferred one by this much (mean absolute difference of a
    # 64x48 greyscale sample, 0-255 scale). Measured on the reference camera
    # with its exposure locked and settled: noise sits at 0.8 with peaks of
    # 3.3, while a car covering a sixth of the frame reads about 13. This
    # default sits in that gap.
    #
    # **Lock the camera's exposure first.** With aec/agc/awb on automatic the
    # sensor hunts and the whole frame shifts brightness between shots -
    # measured noise then reaches 7.5 with peaks of 38, which overlaps the
    # car signal completely and no threshold can separate them. See
    # `docs/deployment-guide.md`.
    motion_change_threshold: float = 8.0
    # ...and inferred anyway this often regardless, so slow drift - dusk, a
    # light switched on, auto-exposure creeping - cannot keep the detector
    # asleep indefinitely. This bounds how long the system can be wrong.
    motion_force_interval_s: float = 10.0

    # A floor on the gap between two inference runs, independent of how often
    # the camera is polled.
    #
    # `poll_interval_s` cannot serve this purpose: it also sets how often a
    # frame is published to the browser, so raising it to slow the detector
    # down makes the live view stutter at the same time. A 30 fps RTSP camera
    # wants a fast tick for a smooth picture and a slow one for the detector,
    # and those are different numbers.
    #
    # Composes with the change gate rather than replacing it: the gate answers
    # "has anything changed?", this answers "is it too soon to look again?",
    # and inference runs only when both say yes. `motion_force_interval_s`
    # still overrides both, so a scene that drifts is still re-examined.
    # 0 disables it, which is the default - it only matters on a source fast
    # enough for the detector to become the bottleneck.
    min_inference_interval_s: float = 0.0

    # A live snapshot is a real request to the camera, and the ROI editor is
    # opened repeatedly while drawing. Reuse the worker's still for this long
    # before going back to the device.
    snapshot_max_age_s: float = 10.0

    # --- Reporting ---------------------------------------------------------
    # A range is mandatory on history queries, and capped: the largest table in
    # the system is on flash storage behind a shared CPU, and one accidental
    # unbounded scan is enough to stall every camera loop behind it.
    history_default_span_days: int = 7
    history_max_span_days: int = 92
    # How often the hourly aggregation job looks for closed hours it has not
    # summarised yet. Short enough that a chart is never more than ~10 minutes
    # stale, long enough not to compete with inference for CPU every tick.
    aggregation_interval_s: float = 600.0
    # A row cap on `/exports/history.csv`, not a page size: past this the
    # caller must narrow the filters. Keeps a single export request bounded
    # on a board that also has to keep every camera loop fed.
    max_export_rows: int = 100_000

    # --- Alerts --------------------------------------------------------------
    # A parked car occupying a slot this long is unusual enough to flag for a
    # guard to check; tuned per site rather than hardcoded so a loading bay
    # and a resident garage can use different values.
    overstay_hours: float = 12.0
    # Fraction of the volume free below which disk space is "low". Halved for
    # the escalation to CRITICAL.
    disk_low_percent: float = 0.10
    # A percentage alone misfires on a small flash card: 10% of a 4 GB card is
    # ~400 MB, comfortable, while 10% of a 64 MB card is ~6 MB, already an
    # emergency. This absolute floor (MiB) catches the small-volume case the
    # percentage misses; halved for the escalation to CRITICAL, same as above.
    disk_low_min_free_mb: int = 256
    # Minimum time between two alerts sharing the same (type, entity) key.
    # Without this a flapping camera or a disk hovering at the threshold
    # produces one alert per job tick instead of one alert per incident.
    alert_cooldown_s: float = 3600.0

    # --- Realtime ----------------------------------------------------------
    ws_auth_deadline_s: float = 5.0
    ws_heartbeat_s: float = 20.0
    ws_max_viewers_per_camera: int = 4
    # Every open stream is a socket, a task and a queue on a board that also
    # runs the inference loop. Refusing the sixteenth viewer is a better
    # outcome than serving all of them badly.
    ws_max_connections_total: int = 16
    # How stale the cached first frame may be. Comfortably more than a poll
    # interval, far less than "the last frame anyone saw yesterday" - past
    # this a new viewer waits for a real frame rather than being shown history
    # as if it were live.
    ws_first_frame_max_age_s: float = 30.0

    # --- Web ---------------------------------------------------------------
    spa_dist_dir: Path = REPO_ROOT / "frontend" / "dist"

    # --- Observability -----------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string so `.env` stays readable."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Settings:
        """Fail fast rather than run a production box with dev defaults."""
        if self.app_env != "prod":
            return self
        problems: list[str] = []
        secret = self.secret_key.get_secret_value().strip()
        if secret.lower() in _UNSAFE_SECRETS:
            problems.append("SECRET_KEY is unset or still the placeholder value")
        elif len(secret.encode()) < MIN_SECRET_KEY_BYTES:
            # HS256 keys shorter than the hash output weaken the signature -
            # RFC 7518 section 3.2. Long enough to matter, cheap to satisfy.
            problems.append(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_BYTES} bytes; "
                "generate one with: python -c \"import secrets;"
                ' print(secrets.token_urlsafe(48))"'
            )
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS contains '*', which is not allowed in prod")
        if not self.cors_origins:
            problems.append("CORS_ORIGINS is empty; list the dashboard's real origin")
        if problems:
            raise ValueError("Refusing to start in prod: " + "; ".join(problems))
        return self

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
