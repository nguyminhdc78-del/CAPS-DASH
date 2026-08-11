"""Stripping credentials out of anything that leaves the process.

A camera's `source_url` may legitimately carry `user:password@` - that is how
some ESP32 firmware is configured, and the worker needs the real value to reach
the device. It must never appear anywhere else: not in a response, not in an
audit row, not in a log line.

The subtle half is free text. An httpx error stringifies as

    Client error '404 Not Found' for url 'http://admin:s3cret@10.0.0.7/anh'

so redacting the `source_url` field alone still leaks the password through the
error message stored on `cameras.last_error` and returned by the camera list -
which security-role users can read, while `source_url` itself is admin-only.
Both shapes are handled here, in one place, at the layer both the vision code
and the API layer can import.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

REDACTED_USERINFO = "***"

# scheme://userinfo@host, wherever it appears inside a longer sentence.
_URL_WITH_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)(?P<userinfo>[^/\s@]+)@")


def sanitize_source_url(source_url: str) -> str:
    """Strip `user:password@` userinfo from a URL.

    Never applied to the value written to the `cameras` row itself - the
    worker still needs the real credential to reach the device.
    """
    if "@" not in source_url:
        return source_url
    parsed = urlsplit(source_url)
    if not parsed.netloc or "@" not in parsed.netloc:
        # Not a URL with userinfo - e.g. a filesystem path that happens to
        # contain '@'. Leave it alone rather than mangle a valid path.
        return source_url
    host = parsed.hostname or ""
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return urlunsplit(parsed._replace(netloc=netloc))


def redact_credentials(text: str) -> str:
    """Redact userinfo in every URL embedded in a free-text string.

    Used on error messages before they are logged, persisted or returned.
    Redacts rather than removes so the message still reads as a URL and stays
    useful for diagnosis.
    """
    if "@" not in text:
        return text
    return _URL_WITH_USERINFO.sub(rf"\g<scheme>{REDACTED_USERINFO}@", text)
