"""Streaming request-body limits for memory-sensitive inference endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Bound selected HTTP request bodies without buffering them.

    A valid ``Content-Length`` above the configured maximum is rejected before
    the first body read. Requests without that header (including chunked
    transfer) are counted as ASGI frames arrive and aborted as soon as their
    cumulative payload crosses the same boundary.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        paths: Collection[str],
        path_prefixes: Collection[str] = (),
        methods: Collection[str] = ("POST",),
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes
        self.paths = frozenset(path.rstrip("/") for path in paths)
        self.path_prefixes = tuple(prefix.rstrip("/") + "/" for prefix in path_prefixes)
        self.methods = frozenset(method.upper() for method in methods)

    @staticmethod
    def _header(scope: Scope, name: bytes) -> bytes | None:
        for key, value in scope.get("headers", []):
            if key.lower() == name:
                return value
        return None

    def _error_response(self, scope: Scope) -> JSONResponse:
        raw_request_id = self._header(scope, b"x-request-id")
        request_id = (
            raw_request_id.decode("utf-8", errors="replace")
            if raw_request_id
            else str(uuid.uuid4())
        )
        return JSONResponse(
            status_code=413,
            content={
                "requestid": request_id,
                "status": 413,
                "type": "request_too_large",
                "detail": f"Request body exceeds {self.max_bytes} bytes.",
            },
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", "")).rstrip("/")
        method = str(scope.get("method", "")).upper()
        selected = path in self.paths or any(
            path.startswith(prefix) for prefix in self.path_prefixes
        )
        if not selected or method not in self.methods:
            await self.app(scope, receive, send)
            return

        raw_content_length = self._header(scope, b"content-length")
        if raw_content_length:
            try:
                content_length = int(raw_content_length)
            except (TypeError, ValueError):
                content_length = 0
            if content_length > self.max_bytes:
                await self._error_response(scope)(scope, receive, send)
                return

        received_bytes = 0
        limit_exceeded = False

        async def limited_receive() -> Message:
            nonlocal received_bytes, limit_exceeded
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                remaining = self.max_bytes - received_bytes
                if len(body) > remaining:
                    limit_exceeded = True
                    # Forward only the bounded prefix and terminate the body.
                    # FastAPI may produce its own parse error for the truncated
                    # JSON; limited_send suppresses it in favour of one 413.
                    received_bytes = self.max_bytes
                    return {
                        "type": "http.request",
                        "body": body[:remaining],
                        "more_body": False,
                    }
                received_bytes += len(body)
            return message

        async def limited_send(message: Message) -> None:
            if not limit_exceeded:
                await send(message)

        await self.app(scope, limited_receive, limited_send)
        if limit_exceeded:
            await self._error_response(scope)(scope, receive, send)
