"""Async task manager for long-running encoding pipelines.

Tracks tasks in-memory with WebSocket progress broadcasting.
Production: replace with Redis + Celery/ARQ.
"""
import asyncio
import logging
import time
from datetime import datetime, UTC
from typing import Optional

logger = logging.getLogger(__name__)


class TaskManager:
    """In-memory task tracker with progress broadcasting."""

    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._ws_subscribers: dict[str, set] = {}  # task_id -> set of WS connections
        self._lock = asyncio.Lock()

    async def create_task(self, task_type: str, params: dict = None) -> str:
        """Create a new task and return its ID."""
        import uuid
        task_id = str(uuid.uuid4())[:12]
        now = datetime.now(UTC).isoformat()
        async with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "type": task_type,
                "status": "pending",  # pending/running/completed/failed
                "progress": 0,  # 0-100
                "current_step": "",
                "steps": [],
                "result": None,
                "error": None,
                "created_at": now,
                "completed_at": None,
            }
        return task_id

    async def update_progress(self, task_id: str, progress: int, current_step: str,
                              step_status: str = "running"):
        """Update task progress and broadcast to subscribers."""
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "running"
                self._tasks[task_id]["progress"] = progress
                self._tasks[task_id]["current_step"] = current_step
                self._tasks[task_id]["steps"].append({
                    "name": current_step,
                    "status": step_status,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
        await self._broadcast(task_id, {
            "type": "progress",
            "task_id": task_id,
            "progress": progress,
            "current_step": current_step,
            "step_status": step_status,
        })

    async def complete_task(self, task_id: str, result: dict = None):
        """Mark task as completed with result."""
        now = datetime.now(UTC).isoformat()
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "completed"
                self._tasks[task_id]["progress"] = 100
                self._tasks[task_id]["completed_at"] = now
                self._tasks[task_id]["result"] = result
        await self._broadcast(task_id, {
            "type": "completed",
            "task_id": task_id,
            "result": result,
        })

    async def fail_task(self, task_id: str, error: str):
        """Mark task as failed with error."""
        now = datetime.now(UTC).isoformat()
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["completed_at"] = now
                self._tasks[task_id]["error"] = error
        await self._broadcast(task_id, {
            "type": "failed",
            "task_id": task_id,
            "error": error,
        })

    def get_task(self, task_id: str) -> Optional[dict]:
        """Get task status by ID."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        # Return a safe copy
        return {
            "task_id": task["task_id"],
            "type": task["type"],
            "status": task["status"],
            "progress": task["progress"],
            "current_step": task["current_step"],
            "steps": task["steps"][-10:],  # Last 10 steps
            "error": task["error"],
            "created_at": task["created_at"],
            "completed_at": task["completed_at"],
        }

    def get_result(self, task_id: str) -> Optional[dict]:
        """Get completed task result."""
        task = self._tasks.get(task_id)
        if task and task["status"] == "completed":
            return task["result"]
        return None

    async def subscribe(self, task_id: str, websocket) -> None:
        """Subscribe a WebSocket to task progress updates."""
        async with self._lock:
            if task_id not in self._ws_subscribers:
                self._ws_subscribers[task_id] = set()
            self._ws_subscribers[task_id].add(websocket)
        # Send current state immediately
        task = self.get_task(task_id)
        if task:
            await websocket.send_json({"type": "status", **task})

    async def unsubscribe(self, task_id: str, websocket) -> None:
        """Unsubscribe a WebSocket from task progress."""
        async with self._lock:
            if task_id in self._ws_subscribers:
                self._ws_subscribers[task_id].discard(websocket)

    async def _broadcast(self, task_id: str, message: dict) -> None:
        """Broadcast a message to all subscribers of a task."""
        async with self._lock:
            subscribers = list(self._ws_subscribers.get(task_id, set()))
        dead = set()
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                if task_id in self._ws_subscribers:
                    self._ws_subscribers[task_id] -= dead

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t["status"] in ("pending", "running"))


# Singleton
task_manager = TaskManager()
