"""Thread auth registration — A1B-AE.5.

Corti public §9 rule 6:

    MCP tools are registered when a new thread is created (the
    first message). Auth DataParts MUST be on that first message.
    Later messages on the same thread do NOT re-register tools;
    auth DataParts are ignored for MCP registration on subsequent
    messages.

This module tracks the per-thread registration state. It is a thin
in-memory tracker keyed by context_id; production deployments should
replace it with a Redis/DB-backed store. For A1B-AE.5 the in-memory
tracker is sufficient — the message:send path uses it to decide
whether to call ``extract_mcp_auth`` (first message) or skip
extraction (subsequent messages).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .mcp_auth_extractor import ExtractedMcpAuth


@dataclass
class _ThreadState:
    """In-memory state for one thread."""

    has_registered: bool = False
    registered_mcp_names: set[str] = field(default_factory=set)
    message_count: int = 0


class ThreadAuthRegistry:
    """In-memory tracker for thread-first-message auth registration.

    Thread-safe via a single coarse-grained lock. Production deployments
    should swap for Redis/DB-backed; the interface stays stable.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: dict[str, _ThreadState] = {}

    def is_first_message(self, context_id: str) -> bool:
        """True iff no message has been registered for this thread yet."""
        with self._lock:
            state = self._threads.get(context_id)
            return state is None or state.message_count == 0

    def register_first_message(
        self,
        context_id: str,
        auth_entries: list[ExtractedMcpAuth],
    ) -> None:
        """Record that the first message has been processed + which MCP
        names it registered tools for.

        Idempotent within the same context — calling twice for the
        same context_id is a no-op after the first call. Subsequent
        auth DataParts on the same thread are silently ignored per
        Corti public §9 rule 6.
        """
        with self._lock:
            state = self._threads.setdefault(context_id, _ThreadState())
            if state.has_registered:
                return
            state.has_registered = True
            for entry in auth_entries:
                state.registered_mcp_names.add(entry.mcp_name)
            state.message_count = 1

    def ack_message(self, context_id: str) -> None:
        """Increment the message counter for a thread (any message)."""
        with self._lock:
            state = self._threads.setdefault(context_id, _ThreadState())
            state.message_count += 1

    def get_state(self, context_id: str) -> dict[str, Any]:
        """Read-only snapshot of the thread's registration state."""
        with self._lock:
            state = self._threads.get(context_id)
            if state is None:
                return {"has_registered": False, "registered_mcp_names": [], "message_count": 0}
            return {
                "has_registered": state.has_registered,
                "registered_mcp_names": sorted(state.registered_mcp_names),
                "message_count": state.message_count,
            }

    def clear(self) -> None:
        """Drop all state (test helper)."""
        with self._lock:
            self._threads.clear()


# Module-level singleton
thread_auth_registry = ThreadAuthRegistry()


__all__ = ["ThreadAuthRegistry", "thread_auth_registry"]
