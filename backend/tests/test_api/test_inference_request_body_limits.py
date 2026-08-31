"""ASGI-level request-body limits for memory-sensitive inference routes."""

from __future__ import annotations

import json
import os

import pytest


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")


async def _send_chunked_request(
    path: str,
    chunks: list[bytes],
    *,
    content_length: bytes | None = None,
):
    from app.main import app

    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    sent: list[dict] = []

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    headers = [
        (b"content-type", b"application/json"),
        (b"transfer-encoding", b"chunked"),
        (b"x-request-id", b"chunked-limit-test"),
    ]
    if content_length is not None:
        headers.append((b"content-length", content_length))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return sent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v2/tools/extract-facts",
        "/api/v2/tools/guided-documents/",
    ],
)
async def test_chunked_inference_body_over_limit_returns_413(path):
    # Sixteen 64 KiB frames reach exactly 1 MiB; the final byte must abort
    # before FastAPI allocates and parses one aggregate JSON request body.
    sent = await _send_chunked_request(path, [b" " * 65_536] * 16 + [b"x"])

    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    assert start["status"] == 413
    payload = json.loads(body)
    assert payload == {
        "requestid": "chunked-limit-test",
        "status": 413,
        "type": "request_too_large",
        "detail": "Request body exceeds 1048576 bytes.",
    }


@pytest.mark.asyncio
async def test_underreported_content_length_cannot_bypass_streaming_limit():
    sent = await _send_chunked_request(
        "/api/v2/tools/extract-facts",
        [b"x" * (1024 * 1024 + 1)],
        content_length=b"1",
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    assert start["status"] == 413


@pytest.mark.asyncio
async def test_streaming_limit_allows_exact_boundary():
    from app.middleware.request_body_limit import RequestBodyLimitMiddleware

    received = bytearray()
    sent: list[dict] = []

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            received.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestBodyLimitMiddleware(
        downstream,
        max_bytes=4,
        paths={"/bounded"},
    )
    chunks = [
        {"type": "http.request", "body": b"ab", "more_body": True},
        {"type": "http.request", "body": b"cd", "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/bounded",
            "headers": [],
        },
        receive,
        send,
    )
    assert bytes(received) == b"abcd"
    assert sent[0]["status"] == 204
