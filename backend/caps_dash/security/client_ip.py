"""The one place that reads a request's client IP.

`request.client.host` is only the real client address when the ASGI server
was told which proxies to trust (`FORWARDED_ALLOW_IPS`, read natively by
uvicorn and mirrored on `Settings.forwarded_allow_ips`). Behind an untrusted
proxy - or with the trust list left too permissive - every caller looks like
the proxy, which silently defeats both the IP rate limit and the audit trail:
the limiter throttles one address instead of many, and every audit row names
the proxy instead of whoever actually made the request.
"""

from __future__ import annotations

from fastapi import Request


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
