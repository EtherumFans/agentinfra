"""Fallback tracking — logs every legacy fallback event with structured context."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FallbackLog:
    """Single fallback event record."""

    def __init__(self, agent_ref: str = "", error_code: str = "", reason: str = "",
                 source_path: str = "", timestamp: str = ""):
        self.agent_ref = agent_ref
        self.error_code = error_code
        self.reason = reason
        self.source_path = source_path  # e.g. "agents.py:run_agent" or "reviews.py:create_review"
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "agent_ref": self.agent_ref,
            "error_code": self.error_code,
            "reason": self.reason,
            "source_path": self.source_path,
            "timestamp": self.timestamp,
        }


class FallbackTracker:
    """Tracks fallback events and provides stats.

    Usage:
        tracker = FallbackTracker(storage_dir=".icoder")
        tracker.record(FallbackLog(
            agent_ref="test/agent@1.0",
            error_code="LLM_PROVIDER_NOT_CONFIGURED",
            reason="PlatformRuntime.run_agent failed",
            source_path="agents.py:run_agent",
        ))
        stats = tracker.stats()
    """

    SCHEMA_VERSION = "1.0"

    def __init__(self, storage_dir: str | Path = ".icoder"):
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "fallback_log.jsonl"
        self._lock = threading.Lock()

    def record(self, event: FallbackLog):
        """Record a fallback event to persistent log."""
        entry = event.to_dict()
        entry["schema_version"] = self.SCHEMA_VERSION
        line = json.dumps(entry, ensure_ascii=False)

        with self._lock:
            try:
                with open(self._file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                logger.error(f"Failed to write fallback log: {e}")

        logger.warning(
            f"[FALLBACK] {event.source_path}: agent={event.agent_ref}, "
            f"error={event.error_code}, reason={event.reason}"
        )

    def stats(self, hours: int = 24) -> dict[str, Any]:
        """Compute fallback statistics for the last N hours."""
        cutoff = datetime.now(timezone.utc)
        events: list[FallbackLog] = []
        error_codes: dict[str, int] = {}
        affected_agents: set[str] = set()

        if not self._file.exists():
            return self._empty_stats()

        try:
            for line in open(self._file, encoding="utf-8"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                ts = entry.get("timestamp", "")
                if ts:
                    try:
                        event_time = datetime.fromisoformat(ts)
                        if (cutoff - event_time).total_seconds() > hours * 3600:
                            continue
                    except ValueError:
                        pass
                code = entry.get("error_code", "UNKNOWN")
                error_codes[code] = error_codes.get(code, 0) + 1
                affected_agents.add(entry.get("agent_ref", ""))
                events.append(FallbackLog(**{k: v for k, v in entry.items() if k != "schema_version"}))
        except (OSError, json.JSONDecodeError):
            pass

        total_runs = max(error_codes.get("__total_runs__", sum(error_codes.values())), 1)
        return {
            "total_fallbacks": len(events),
            "fallback_rate": round(len(events) / total_runs, 4),
            "top_errors": sorted(error_codes.items(), key=lambda x: x[1], reverse=True)[:5],
            "affected_agents": sorted(affected_agents),
            "last_fallback_at": events[-1].timestamp if events else "",
            "window_hours": hours,
        }

    def _empty_stats(self) -> dict:
        return {
            "total_fallbacks": 0,
            "fallback_rate": 0.0,
            "top_errors": [],
            "affected_agents": [],
            "last_fallback_at": "",
            "window_hours": 24,
        }
