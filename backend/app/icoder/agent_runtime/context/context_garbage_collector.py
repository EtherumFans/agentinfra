"""Background GC — sweep expired contexts + destroy post-grace + prune audit (SPEC §5.5).

Default cadence: 300 s (5 min). Tunable via ``sweep_interval_seconds``.

The collector owns one asyncio task; ``start`` is idempotent and
``stop`` awaits the in-flight run.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from .context_audit import ContextAudit
from .context_lifecycle import ContextLifecycle


@dataclass
class GCResult:
    swept_ids: list[str] = field(default_factory=list)
    destroyed_ids: list[str] = field(default_factory=list)
    pruned_audit_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.swept_ids) + len(self.destroyed_ids) + len(self.pruned_audit_ids)


class ContextGarbageCollector:
    """Periodic sweeper + destroyer + audit pruner."""

    def __init__(
        self,
        lifecycle: ContextLifecycle,
        audit: ContextAudit,
        *,
        sweep_interval_seconds: int = 300,
        audit_prune_enabled: bool = True,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], asyncio.Future] | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._audit = audit
        self._interval = sweep_interval_seconds
        self._audit_prune_enabled = audit_prune_enabled
        # Context persistence currently uses timezone-naive SQL DateTime
        # columns. Derive that value from an aware UTC clock without relying on
        # Python's deprecated datetime.utcnow().
        self._now = now_fn or (
            lambda: datetime.now(UTC).replace(tzinfo=None)
        )
        self._sleep = sleep_fn or asyncio.sleep
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._run_count = 0
        self._last_result: GCResult | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def run_count(self) -> int:
        return self._run_count

    @property
    def last_result(self) -> GCResult | None:
        return self._last_result

    async def run_once(self) -> GCResult:
        """Run sweep + destroy + audit prune exactly once."""
        swept = await self._lifecycle.sweep_expired()
        destroyed = await self._lifecycle.destroy_expired()
        pruned = (
            await self._audit.prune_expired() if self._audit_prune_enabled else []
        )
        result = GCResult(
            swept_ids=swept,
            destroyed_ids=destroyed,
            pruned_audit_ids=pruned,
        )
        self._run_count += 1
        self._last_result = result
        return result

    async def start(self) -> None:
        """Start the background loop. No-op if already running."""
        if self.is_running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="context-gc")

    async def stop(self, *, timeout: float | None = None) -> None:
        """Signal stop and await the in-flight run."""
        if self._task is None:
            return
        self._stop.set()
        try:
            if timeout is None:
                await self._task
            else:
                await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.TimeoutError:
            self._task.cancel()
        finally:
            self._task = None

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await self.run_once()
                except Exception:
                    pass
                try:
                    await self._sleep(self._interval)
                except asyncio.CancelledError:
                    raise
                if self._interval <= 0:
                    break
        except asyncio.CancelledError:
            pass
