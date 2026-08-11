"""WebSocket close codes and the short reasons we send with them.

Reasons are machine codes, not sentences. A close reason is visible to anyone
holding the socket, so it must not leak internal detail - and the client has to
branch on it (reconnect after `token_expired`, give up after `forbidden`),
which a prose message makes impossible.

RFC 6455 section 7.4.1 defines the numbers.
"""

from __future__ import annotations

from typing import Final

NORMAL: Final = 1000
GOING_AWAY: Final = 1001
POLICY_VIOLATION: Final = 1008
INTERNAL_ERROR: Final = 1011
TRY_AGAIN_LATER: Final = 1013

# Reasons. Kept under 123 bytes - the protocol limit for the reason field.
REASON_AUTH_TIMEOUT: Final = "auth_timeout"
REASON_AUTH_INVALID: Final = "auth_invalid"
REASON_TOKEN_EXPIRED: Final = "token_expired"  # noqa: S105 - a close reason, not a secret
REASON_FORBIDDEN: Final = "forbidden"
REASON_CAMERA_UNKNOWN: Final = "camera_unknown"
REASON_TOO_MANY_VIEWERS: Final = "too_many_viewers"
REASON_HEARTBEAT_LOST: Final = "heartbeat_lost"
REASON_SERVER_ERROR: Final = "server_error"
