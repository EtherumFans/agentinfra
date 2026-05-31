"""SSE (Server-Sent Events) Manager — streaming agent responses.

iCoDer Agentic Framework equivalent: "Streaming with Server-Sent Events (SSE)
used for real-time experiences like ambient notes or live guidance."

Difficulty: HIGH — requires async generator pattern, connection lifecycle management,
incremental token delivery, and differs fundamentally from sync request-response.
"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class SSEManager:
    """Manages SSE connections for streaming agent responses."""

    # Max connections to prevent resource exhaustion
    MAX_CONNECTIONS = 50
    # Heartbeat interval to keep connections alive
    HEARTBEAT_SECONDS = 15
    # Max stream duration before forced close
    MAX_STREAM_SECONDS = 300  # 5 minutes

    def __init__(self):
        self._active_connections: dict[str, asyncio.Event] = {}

    async def stream_agent_response(
        self,
        stream_id: str,
        content_generator: AsyncGenerator[str, None],
    ) -> StreamingResponse:
        """Create an SSE streaming response for agent output.

        Usage in FastAPI endpoint:
            return await sse_manager.stream_agent_response(
                stream_id, expert_runner.stream_run(expert, input)
            )
        """
        if len(self._active_connections) >= self.MAX_CONNECTIONS:
            raise RuntimeError("Too many SSE connections")

        stop_event = asyncio.Event()
        self._active_connections[stream_id] = stop_event
        start_time = time.time()

        async def event_stream():
            """SSE event generator with heartbeat and timeout."""
            try:
                # Send initial connection event
                yield self._sse_event("connected", {"stream_id": stream_id})

                # Stream content chunks
                async for chunk in content_generator:
                    if stop_event.is_set():
                        break
                    if time.time() - start_time > self.MAX_STREAM_SECONDS:
                        yield self._sse_event("timeout", {"message": "Stream timeout"})
                        break
                    yield self._sse_event("token", {"text": chunk})

                # Send completion and stop the heartbeat loop
                yield self._sse_event("done", {"stream_id": stream_id})
                stop_event.set()

            except Exception as e:
                logger.error(f"SSE stream {stream_id} error: {e}")
                yield self._sse_event("error", {"message": str(e)})
            finally:
                self._active_connections.pop(stream_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    def close_stream(self, stream_id: str):
        """Force-close a stream by ID."""
        event = self._active_connections.get(stream_id)
        if event:
            event.set()

    def _sse_event(self, event: str, data: dict) -> str:
        """Format an SSE event."""
        lines = [f"event: {event}"]
        if data:
            lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
        lines.append("")  # Empty line terminates the event
        return "\n".join(lines) + "\n"

    @property
    def active_count(self) -> int:
        return len(self._active_connections)


sse_manager = SSEManager()
