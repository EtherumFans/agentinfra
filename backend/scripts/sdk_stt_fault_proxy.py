"""Loopback-only WebSocket fault proxy for managed STT recovery E2E tests.

The first connection for each opaque resume session is closed immediately
after audio sequence 1 is acknowledged. Subsequent connections are relayed
without faults. The proxy never logs tokens, audio, transcripts, or session
identifiers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect
from websockets.asyncio.server import ServerConnection, serve


class FaultState:
    def __init__(self, metrics_path: Path) -> None:
        self._metrics_path = metrics_path
        self._lock = asyncio.Lock()
        self._connections: dict[str, int] = {}
        self._dropped: set[str] = set()

    async def started(self, session_id: str) -> None:
        async with self._lock:
            self._connections[session_id] = self._connections.get(session_id, 0) + 1
            self._write()

    async def should_drop(self, session_id: str) -> bool:
        async with self._lock:
            return session_id not in self._dropped

    async def dropped(self, session_id: str) -> None:
        async with self._lock:
            self._dropped.add(session_id)
            self._write()

    def _write(self) -> None:
        payload = {
            "schema_version": "icoder.stt-fault-proxy/v1",
            "unique_sessions": len(self._connections),
            "forced_disconnects": len(self._dropped),
            "total_resume_connections": sum(self._connections.values()),
            "sessions_with_reconnect": sum(
                1 for count in self._connections.values() if count >= 2
            ),
            "clinical_payload_captured": False,
        }
        temporary = self._metrics_path.with_suffix(self._metrics_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(self._metrics_path)


def _json_object(message: Any) -> dict[str, Any]:
    if not isinstance(message, str):
        return {}
    try:
        value = json.loads(message)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


async def run_proxy(upstreams: list[str], port: int, metrics_path: Path) -> None:
    state = FaultState(metrics_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    upstream_lock = asyncio.Lock()
    upstream_index = 0

    async def next_upstream() -> str:
        nonlocal upstream_index
        async with upstream_lock:
            selected = upstreams[upstream_index % len(upstreams)]
            upstream_index += 1
            return selected

    async def handler(client: ServerConnection) -> None:
        request_path = client.request.path
        if not request_path.startswith("/ws/speech-to-text?"):
            await client.close(code=1008, reason="unsupported proxy path")
            return
        upstream = await next_upstream()
        upstream_socket = await connect(
            f"{upstream}{request_path}",
            proxy=None,
            compression=None,
            max_size=34 * 1024 * 1024,
        )
        session: dict[str, str] = {"id": ""}

        async def client_to_upstream() -> None:
            async for message in client:
                command = _json_object(message)
                if command.get("type") == "start":
                    session_id = command.get("sessionId")
                    if isinstance(session_id, str):
                        session["id"] = session_id
                        await state.started(session_id)
                await upstream_socket.send(message)

        async def upstream_to_client() -> None:
            async for message in upstream_socket:
                await client.send(message)
                event = _json_object(message)
                session_id = session["id"]
                if (
                    session_id
                    and event.get("type") == "audio_ack"
                    and event.get("sequence") == 1
                    and await state.should_drop(session_id)
                ):
                    await state.dropped(session_id)
                    await client.close(code=1012, reason="synthetic recovery fault")
                    await upstream_socket.close(code=1000, reason="fault injected")
                    return

        tasks = {
            asyncio.create_task(client_to_upstream()),
            asyncio.create_task(upstream_to_client()),
        }
        try:
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            await upstream_socket.close()

    async with serve(
        handler,
        "127.0.0.1",
        port,
        compression=None,
        max_size=34 * 1024 * 1024,
    ):
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, action="append")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--metrics-file", required=True, type=Path)
    args = parser.parse_args()
    upstreams = [value.rstrip("/") for value in args.upstream]
    if any(not value.startswith("ws://127.0.0.1:") for value in upstreams):
        raise SystemExit("every upstream must be an explicit loopback ws:// endpoint")
    asyncio.run(run_proxy(upstreams, args.port, args.metrics_file.resolve()))


if __name__ == "__main__":
    main()
