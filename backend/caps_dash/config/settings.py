"""Application settings.

Every tunable lives here. Nothing is hardcoded at its point of use - the
reference project scattered constants across modules and shipped an admin
password in source, which is exactly what this module exists to prevent.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# Placeholder values that must never survive into production.
_UNSAFE_SECRETS = {"", "change-me", "changeme", "secret", "caps"}


def _trusts_every_hop(forwarded_allow_ips: str) -> bool:
    """True if this trust list lets any caller forge `X-Forwarded-For`.

    Checking for the literal `"*"` is not enough: `0.0.0.0/0` and `::/0` are
    the other standard spellings of "trust every hop", and uvicorn honours
    them the same way. A prod deployment that used the CIDR form would sail
    past a string comparison while leaving the client IP fully caller-
    controlled - which forges both the per-IP search budget and every audit
    row's `client_ip`, the two protections the public kiosk depends on.
    """
    for raw_entry in forwarded_allow_ips.split(","):
        entry = raw_entry.strip()
        if entry == "*":
            return True
        try:
            # `strict=False` so a host address with a prefix does not raise.
            if ipaddress.ip_network(entry, strict=False).prefixlen == 0:
                return True
        except ValueError:
            # Not an address or network (a hostname, or noise). uvicorn will
            # not treat it as a wildcard, so it is not our concern here.
            continue
    return False

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
    # Whether the refresh cookie carries the `Secure` flag. `None` (the
    # default) means "follow APP_ENV": Secure in prod, not in dev - correct
    # when prod is served over HTTPS. Set `COOKIE_SECURE=false` to run prod
    # over plain http (e.g. a LAN demo board on `http://<ip>:8000`): a Secure
    # cookie is silently dropped by the browser over http, so the refresh
    # cookie never stores and every reload/new tab logs the user out. Only
    # relax this on a trusted network - it is a real reduction in cookie
    # protection, made deliberately for the http-demo case.
    cookie_secure: bool | None = None
    login_max_attempts: int = 5
    login_window_s: int = 300
    # uvicorn's own env var (`FORWARDED_ALLOW_IPS`, read by `Config.load()` to
    # build `ProxyHeadersMiddleware`), mirrored here so `serve_command.py` can
    # pass it explicitly and the `.env` launch path works too - one knob, one
    # name, no divergence between the raw-uvicorn paths (Docker, systemd) and
    # this one. Must name the reverse proxy's address as uvicorn sees it (the
    # bridge gateway under Docker, `127.0.0.1` for a local nginx). Setting it
    # to `"*"` trusts every hop, which makes `X-Forwarded-For` fully
    # client-controlled - the real client IP becomes whatever the caller
    # claims, which is worthless for both the rate limiter and the audit log.
    forwarded_allow_ips: str = "127.0.0.1"

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
    # How many inferences may run at once - NOT how many threads one inference
    # uses; that is `inference_threads` below, and confusing the two has
    # already produced one wrong conclusion. One worker means one detector
    # instance and one model in RAM. On a QRB2210 sharing its CPU with the API,
    # the SPA and SQLite, this is a correctness constraint rather than a
    # performance knob: raising it loads a second model and buys contention.
    # Do not raise it to fit a tick budget - raise the tick instead.
    inference_pool_size: int = 1
    # Threads onnxruntime may use inside ONE inference (`intra_op_num_threads`;
    # `inter_op` is pinned to 1). 0 means "decide for yourself", which on a
    # four-core board means all four.
    #
    # The cap was introduced because something else needed those cores
    # continuously: an RTSP camera sending HEVC runs a four-thread FFMPEG
    # decoder in the same process, and measured on the board the two together
    # pinned it at 325% CPU of 400% available. The decoder was the one that
    # lost - 13-15 fps against a 30 fps camera, backlog on the camera's side,
    # 36 session resyncs in one sixteen-minute window.
    #
    # That decoder is no longer on the primary path: snapshot polling decodes
    # one small JPEG per tick instead of a continuous stream, so nothing is
    # left to starve and the cap has no reason to stay where it was.
    #
    # Measured on the board 2026-08-12, 50 runs per setting on a real camera
    # frame at 640x640, service stopped so nothing else held a core:
    #
    #     threads   mean     speedup
    #     2         837 ms   1.00x
    #     3         631 ms   1.32x
    #     4         533 ms   1.57x
    #
    # Sublinear, as expected, and still worth taking: raising this cannot make
    # two inferences run at once (that is `inference_pool_size`, which stays
    # 1), it makes each one finish sooner - which is exactly what the
    # serialized budget needs. 3 cameras x 533 ms is 1.60 s against a 2.0 s
    # tick and fits; at 2 threads it was 2.51 s and did not.
    #
    # 4 because the target board has four cores and one inference runs at a
    # time. On a host with fewer cores, lower it to match - oversubscribing
    # intra-op threads costs scheduling overhead and buys nothing.
    inference_threads: int = 4
    inference_input_size: int = 640
    detector_confidence: float = 0.25
    # The reference project's own config notes record that 1.0s x 3 flickered
    # and that a real deployment wants roughly 3.0s x 4.
    #
    # Deliberately left at 3.0 rather than retuned to the MaixCam's 2.0: this
    # is the fallback for a generic slow HTTP camera, and one device is not a
    # reason to move it. The 2.0 s cadence lives on the camera row and in the
    # dashboard's per-source-type default instead.
    default_poll_interval_s: float = 3.0
    default_vote_window: int = 5
    default_vote_threshold: int = 4
    # A timeout guards against a wedged camera, not a slow one, so it wants
    # headroom over the worst case rather than a tight fit around the median.
    # 5.0 is the pre-existing default and has not been re-derived for the
    # MaixCam - that wants measured p90 x 3, rounded up, and the latency
    # measurement is still outstanding (phase-01). Do not tighten it to match
    # a fast link: `camera_fail_streak_offline` below already requires three
    # consecutive failures before a camera is called offline.
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
    # asleep indefinitely. This bounds how long the system can be wrong when
    # the change gate misses a real change.
    #
    # 30 s, not 10. At the 0.2 s streaming tick 10 s was 50 ticks between
    # forced runs; at a 2 s polling tick it is 5, so every camera force-infers
    # constantly and competes with genuine change-triggered runs inside a
    # budget that is already tight. A parked car does not need 10 s bounding.
    # This is a deliberate trade of detection latency for headroom, not a
    # free win - see `docs/deployment-guide.md`.
    motion_force_interval_s: float = 30.0

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
    # still overrides both, so a scene that drifts is still re-examined. 0
    # disables it.
    #
    # 0 by default now that the primary path polls. The floor existed for the
    # 0.2 s streaming tick, where a scene that kept changing ran the detector
    # back to back for as long as it did; the measured 3.54 -> 0.83 load
    # average that justified 1.5 was taken at that tick and does not transfer
    # to a 2 s one. At any tick >= 1.5 s the floor is inert anyway - it only
    # gates `reason == "changed"` (`camera_tick_policy.py`), and the gap
    # between two same-camera change-triggered runs is already bounded below
    # by the tick itself. 0 says that plainly rather than leaving a number
    # that looks tuned. Kept as a lever for any future fast source.
    min_inference_interval_s: float = 0.0

    # A live snapshot is a real request to the camera, and the ROI editor is
    # opened repeatedly while drawing. Reuse the worker's still for this long
    # before going back to the device.
    snapshot_max_age_s: float = 10.0

    # Read the plate of a car when its bay fills. Off by default, and that is
    # the honest default rather than a timid one:
    #
    # - It costs ~1 s of the shared inference worker per arrival, measured on
    #   the board, so a site that does not want the feature should not pay for
    #   it by accident.
    # - It downloads its models on first use, which a machine with no internet
    #   must be able to decline.
    # - It stores a plate number, which identifies a vehicle and through it a
    #   person. A feature with that consequence should be switched on
    #   deliberately, by someone who has decided to store it.
    #
    # Turning it on is one line; leaving it on by default would mean shipping
    # personal-data collection to anyone who upgraded without reading.
    plate_reading_enabled: bool = False

    # --- Public kiosk --------------------------------------------------------
    # Makes the `/kiosk` lobby display reachable with no login, and adds a
    # partial-match plate search to it. Off by default because enabling it is
    # a real trade, not a formality: anyone on the network can locate any
    # vehicle by typing part of its plate. It also needs
    # `plate_reading_enabled` on - with that off there are zero `plate_reads`
    # rows, so the search box has nothing to search and stays hidden rather
    # than shown returning nothing.
    public_kiosk_enabled: bool = False
    # Per-client-IP budget for the public search endpoint. Tunable because a
    # busy lobby may need it raised without a code change; 10/60s was sized
    # for an internal-LAN-only deployment where one IP is effectively one
    # device (see Phase 01 of the public-kiosk plan).
    public_kiosk_max_searches: int = 10
    public_kiosk_window_s: int = 60

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
        if self.public_kiosk_enabled and _trusts_every_hop(self.forwarded_allow_ips):
            # Trusting every hop makes `X-Forwarded-For` attacker-controlled,
            # which forges both the public search rate limit and the audit
            # trail's client IP - the exact two protections the public kiosk
            # depends on.
            problems.append(
                "FORWARDED_ALLOW_IPS is '*' while PUBLIC_KIOSK_ENABLED is true; "
                "this lets any caller forge their client IP, defeating both the "
                "kiosk rate limit and the audit trail. Set it to the reverse "
                "proxy's real address instead."
            )
        if problems:
            raise ValueError("Refusing to start in prod: " + "; ".join(problems))
        return self

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def refresh_cookie_secure(self) -> bool:
        """`Secure` flag for the refresh cookie: explicit `COOKIE_SECURE` wins,
        else follow the environment (Secure in prod, plain in dev)."""
        return self.is_prod if self.cookie_secure is None else self.cookie_secure


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
