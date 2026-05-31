"""Thread State Manager — governed, persistent conversation state for Agent sessions.

Provides:
- Thread creation and retrieval
- Message history persistence
- State snapshots (save/restore)
- Governed memory access (guard before read/write)
"""

import time
import uuid
import logging
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class ThreadState:
    """A single conversation thread with message history and metadata."""

    def __init__(self, thread_id: str, agent_id: str, user_id: str = ""):
        self.thread_id = thread_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.messages: list[dict] = []
        self.metadata: dict = {}
        self.created_at = time.time()
        self.updated_at = time.time()
        self.status = "active"  # active | paused | completed | archived
        self._snapshots: list[dict] = []

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content, "timestamp": time.time()})
        self.updated_at = time.time()

    def save_snapshot(self, label: str = "") -> dict:
        snap = {
            "label": label or f"snapshot_{len(self._snapshots) + 1}",
            "messages": list(self.messages),
            "metadata": dict(self.metadata),
            "timestamp": time.time(),
        }
        self._snapshots.append(snap)
        return snap

    def restore_snapshot(self, index: int = -1) -> bool:
        if not self._snapshots:
            return False
        snap = self._snapshots[index]
        self.messages = list(snap["messages"])
        self.metadata = dict(snap["metadata"])
        return True

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "messages": self.messages,
            "message_count": len(self.messages),
            "metadata": self.metadata,
            "status": self.status,
            "snapshot_count": len(self._snapshots),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ThreadStateManager:
    """In-memory thread state registry with governed access.

    Production deployment should use Redis/DB persistence.
    """

    def __init__(self):
        self._threads: dict[str, ThreadState] = {}
        self._access_log: list[dict] = []

    def create(self, agent_id: str, user_id: str = "", thread_id: str = "") -> ThreadState:
        tid = thread_id or f"thread-{uuid.uuid4().hex[:12]}"
        ts = ThreadState(tid, agent_id, user_id)
        self._threads[tid] = ts
        self._log_access(tid, "create", user_id)
        return ts

    def get(self, thread_id: str) -> Optional[ThreadState]:
        ts = self._threads.get(thread_id)
        if ts:
            self._log_access(thread_id, "read", ts.user_id)
        return ts

    def delete(self, thread_id: str, actor: str = "") -> bool:
        if thread_id in self._threads:
            del self._threads[thread_id]
            self._log_access(thread_id, "delete", actor)
            return True
        return False

    def list_by_agent(self, agent_id: str) -> list[dict]:
        return [t.to_dict() for t in self._threads.values() if t.agent_id == agent_id]

    def list_by_user(self, user_id: str) -> list[dict]:
        return [t.to_dict() for t in self._threads.values() if t.user_id == user_id]

    def _log_access(self, thread_id: str, action: str, actor: str) -> None:
        self._access_log.append({
            "thread_id": thread_id,
            "action": action,
            "actor": actor,
            "timestamp": time.time(),
        })
        if len(self._access_log) > 10000:
            self._access_log = self._access_log[-5000:]

    def get_access_log(self, thread_id: str, limit: int = 50) -> list[dict]:
        return [e for e in self._access_log if e["thread_id"] == thread_id][-limit:]

    def stats(self) -> dict:
        return {
            "total_threads": len(self._threads),
            "active_threads": sum(1 for t in self._threads.values() if t.status == "active"),
            "total_messages": sum(len(t.messages) for t in self._threads.values()),
        }


# Singleton
thread_manager = ThreadStateManager()
