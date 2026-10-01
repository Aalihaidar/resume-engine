"""Test helpers shared across modules (fixtures live in conftest.py)."""

from __future__ import annotations

import base64
import struct
import zlib


def png_bytes(size: int = 16) -> bytes:
    """A real, decodable PNG, built by hand so the tests need no imaging library."""
    rows = b"".join(
        b"\x00" + b"".join(bytes([x * 16 % 256, y * 16 % 256, 150]) for x in range(size))
        for y in range(size)
    )

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def data_uri(mime: str, payload: bytes) -> str:
    return f"data:image/{mime};base64,{base64.b64encode(payload).decode()}"
