/**
 * Central home for the magic numbers that would otherwise get hardcoded
 * inline in a component. A reviewer changing "how often do we poll" or
 * "what's the minimum password length" edits one line here instead of
 * grepping across every feature that happens to duplicate the value.
 *
 * Values that mirror a backend constraint (password length, confidence
 * bounds) are commented with where the backend enforces the same rule -
 * this file is a client-side convenience, the backend remains the authority.
 */

// Camera runtime confidence tuning. Mirrors RUNTIME_CONFIDENCE_MIN/MAX in
// backend/caps_dash/services/camera_service.py.
export const CAMERA_CONFIDENCE_MIN = 0.01
export const CAMERA_CONFIDENCE_MAX = 0.95
export const CAMERA_CONFIDENCE_STEP = 0.01
/** Debounce before a slider drag turns into a PATCH /cameras/{id}/runtime. */
export const CAMERA_CONFIDENCE_DEBOUNCE_MS = 400

// User account fields. Mirrors CreateUserRequest in
// backend/caps_dash/api/schemas/user_schemas.py.
export const USER_USERNAME_MIN_LENGTH = 3
export const USER_USERNAME_MAX_LENGTH = 64
export const USER_PASSWORD_MIN_LENGTH = 10
export const USER_PASSWORD_MAX_LENGTH = 256
export const USER_DISPLAY_NAME_MAX_LENGTH = 120

// Camera fields. Mirrors CreateCameraRequest in
// backend/caps_dash/api/schemas/camera_schemas.py.
export const CAMERA_CODE_MAX_LENGTH = 16
export const CAMERA_NAME_MAX_LENGTH = 120
export const CAMERA_FLOOR_MAX_LENGTH = 16
export const CAMERA_POLL_INTERVAL_MIN_S = 0.1
export const CAMERA_POLL_INTERVAL_MAX_S = 300
export const CAMERA_VOTE_WINDOW_MAX = 60
export const CAMERA_VOTE_THRESHOLD_MAX = 60

export const DEFAULT_PAGE_SIZE = 50
export const MAX_PAGE_SIZE = 200

// Polling. The board's slot state settles on the order of seconds, so
// polling faster only adds load for no visible benefit.
export const SUMMARY_POLL_MS = 3_000
export const KIOSK_POLL_MS = 3_000
// Far slower than the kiosk: an alert is minutes-relevant, not
// seconds-relevant, and this one polls from every page at once.
export const ALERT_BADGE_POLL_MS = 60_000

// Overview page ("Tổng quan"). The camera list backs both the hero picker
// and the health strip - a few seconds keeps a just-flipped-offline camera
// visible promptly without hammering the list endpoint the way SUMMARY_POLL_MS
// would (that cadence exists for slot state, which settles far faster).
export const DASHBOARD_CAMERA_HEALTH_POLL_MS = 5_000
// The 24h occupancy chart reads pre-aggregated hourly_stats rows, which
// change on the order of an hour, not a few seconds - a full minute keeps it
// current without adding load the board's YOLO workload would feel.
export const DASHBOARD_CHART_POLL_MS = 60_000

/** Slot grid reflow breakpoints: wide -> medium -> narrow column counts. */
export const SLOT_GRID_BREAKPOINTS = {
  wide: 6,
  medium: 3,
  narrow: 2,
} as const
