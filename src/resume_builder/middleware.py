"""ASGI middleware enforcing a maximum request body size.

`api.py`'s POST endpoints are intentionally no-auth (see its module
docstring — any app or AI agent can call them directly). Pydantic's own
validation in `models.py` rejects an oversized `photo` field, but that check
only runs *after* Starlette has already read the full request body into
memory. Without a cap here, nothing stops a caller from POSTing an
arbitrarily large body and forcing memory/CPU consumption before validation
ever gets a chance to reject it.

This rejects oversized requests as early as possible:
  1. via the `Content-Length` header, when present and honest (cheap, no
     body read at all) — but callers can omit or lie about this header, so
  2. it also enforces the same cap while actually reading the body stream,
     which catches a missing/spoofed Content-Length combined with chunked
     transfer encoding.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 8MB comfortably covers the resume/cover-letter text fields plus a photo
# already compressed client-side (see web_static/index.html, which caps the
# encoded photo at 2MB) — with headroom for base64 overhead and a caller
# that skips compression entirely.
MAX_BODY_BYTES = 8 * 1024 * 1024


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

        async def guarded_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b"") or b"")
                if seen > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, guarded_receive, send)
        except _BodyTooLarge:
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
