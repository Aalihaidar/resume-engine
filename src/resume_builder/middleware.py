"""ASGI middleware for the public HTTP API.

`api.py`'s POST endpoints are intentionally no-auth (see its module
docstring — any app or AI agent can call them directly), so two things are
handled before a request reaches the routes.

MaxBodySizeMiddleware
---------------------
Pydantic's own validation in `models.py` rejects an oversized `photo` field, but
that check only runs *after* Starlette has already read the full request body
into memory. Without a cap here, nothing stops a caller from POSTing an
arbitrarily large body and forcing memory/CPU consumption before validation
ever gets a chance to reject it.

This rejects oversized requests as early as possible:
  1. via the `Content-Length` header, when present and honest (cheap, no
     body read at all) — but callers can omit or lie about this header, so
  2. it also enforces the same cap while actually reading the body stream,
     which catches a missing/spoofed Content-Length combined with chunked
     transfer encoding. The framework turns an exception raised mid-read into
     its own "400 could not parse body", so the 413 is sent from here and
     whatever the application tries to send afterwards is discarded.

SecurityHeadersMiddleware
-------------------------
Adds the response headers that make browsers treat every response from this
service conservatively. The Content-Security-Policy is *not* here: it belongs to
the one HTML document the service serves (see `api.index`), and a strict policy
on the interactive API docs would break them.
"""

from __future__ import annotations

import contextlib

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 8MB comfortably covers the resume/cover-letter text fields plus a photo
# already compressed client-side (see web_static/assets/app.js, which caps the
# encoded photo at 2MB) — with headroom for base64 overhead and a caller
# that skips compression entirely.
MAX_BODY_BYTES = 8 * 1024 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000",
}


class _BodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    """Starlette-compatible ASGI middleware. Add via app.add_middleware(...)."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                pass  # malformed header — fall through to the streaming check

        seen = 0
        too_large = False
        response_started = False

        async def guarded_receive() -> Message:
            nonlocal seen, too_large
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b"") or b"")
                if seen > self.max_bytes:
                    too_large = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if too_large:
                return  # the app's own error response; ours replaces it
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        with contextlib.suppress(_BodyTooLarge):
            await self.app(scope, guarded_receive, guarded_send)

        if too_large and not response_started:
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"detail":"Request body too large"}',
            }
        )


class SecurityHeadersMiddleware:
    """Add SECURITY_HEADERS to every HTTP response (including 413s from the cap).

    `allow_framing` drops X-Frame-Options so an editor's embedded browser can show
    the page during development; production never sets it.
    """

    def __init__(self, app: ASGIApp, allow_framing: bool = False) -> None:
        self.app = app
        self.headers = {
            name: value
            for name, value in SECURITY_HEADERS.items()
            if not (allow_framing and name == "X-Frame-Options")
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
