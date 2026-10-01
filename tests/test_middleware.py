from __future__ import annotations

import asyncio

from starlette.types import Message, Receive, Scope, Send

from resume_builder.middleware import MaxBodySizeMiddleware, SecurityHeadersMiddleware


async def _drive(
    app: MaxBodySizeMiddleware | SecurityHeadersMiddleware,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    chunks: list[bytes] | None = None,
    scope_type: str = "http",
) -> list[Message]:
    sent: list[Message] = []
    pending = [{"type": "http.request", "body": c, "more_body": True} for c in chunks or []]
    pending.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive() -> Message:
        return pending.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": scope_type, "headers": headers or []}
    await app(scope, receive, send)
    return sent


async def _read_all_then_ok(scope: Scope, receive: Receive, send: Send) -> None:
    more = True
    while more:
        more = (await receive()).get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _status(messages: list[Message]) -> int:
    return int(next(m["status"] for m in messages if m["type"] == "http.response.start"))


def test_small_body_passes_through() -> None:
    app = MaxBodySizeMiddleware(_read_all_then_ok, max_bytes=10)
    assert _status(asyncio.run(_drive(app, chunks=[b"12345"]))) == 200


def test_malformed_content_length_falls_back_to_the_streaming_check() -> None:
    app = MaxBodySizeMiddleware(_read_all_then_ok, max_bytes=10)
    headers = [(b"content-length", b"not-a-number")]
    assert _status(asyncio.run(_drive(app, headers=headers, chunks=[b"12345"]))) == 200
    assert _status(asyncio.run(_drive(app, headers=headers, chunks=[b"x" * 6, b"x" * 6]))) == 413


def test_streamed_overflow_wins_even_if_the_app_swallows_the_error() -> None:
    async def app_that_catches(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            while (await receive()).get("more_body", False):
                pass
        except Exception:
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"bad body"})

    app = MaxBodySizeMiddleware(app_that_catches, max_bytes=10)
    messages = asyncio.run(_drive(app, chunks=[b"x" * 6, b"x" * 6]))

    assert _status(messages) == 413
    assert [m["type"] for m in messages] == ["http.response.start", "http.response.body"]
    assert messages[1]["body"] == b'{"detail":"Request body too large"}'


def test_non_http_scopes_are_not_touched() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    for middleware in (MaxBodySizeMiddleware(inner), SecurityHeadersMiddleware(inner)):
        asyncio.run(_drive(middleware, scope_type="lifespan"))
    assert seen == ["lifespan", "lifespan"]


def test_security_headers_do_not_override_an_explicit_value() -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"x-frame-options", b"SAMEORIGIN")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    messages = asyncio.run(_drive(SecurityHeadersMiddleware(inner)))
    headers = dict(messages[0]["headers"])
    assert headers[b"x-frame-options"] == b"SAMEORIGIN"
    assert headers[b"x-content-type-options"] == b"nosniff"


def test_framing_can_be_allowed_for_development_only() -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    strict = dict(asyncio.run(_drive(SecurityHeadersMiddleware(inner)))[0]["headers"])
    relaxed = dict(
        asyncio.run(_drive(SecurityHeadersMiddleware(inner, allow_framing=True)))[0]["headers"]
    )
    assert strict[b"x-frame-options"] == b"DENY"
    assert b"x-frame-options" not in relaxed
    assert relaxed[b"x-content-type-options"] == b"nosniff"  # everything else stays
