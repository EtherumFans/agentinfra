"""Runtime Audit Log — persistent record of lifecycle and security events."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class RuntimeAuditLogger:
    """Records security-relevant events: install, enable, disable, uninstall, approval, run."""

    SCHEMA_VERSION = "1.0"
    EVENT_TYPES = (
        "agent_installed", "agent_enabled", "agent_disabled", "agent_uninstalled",
        "agent_upgraded", "agent_rollback", "agent_run", "agent_approval_submitted",
        "agent_approval_granted", "agent_approval_denied",
        "registry_repaired", "registry_corruption_detected",
        "fallback_triggered", "shadow_diff_recorded",
        "data_policy_violation",
    )

    def __init__(self, storage_dir: str | Path = ".icoder"):
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "audit_log.jsonl"
        self._lock = threading.Lock()

    def record(self, event_type: str, actor: str = "system", detail: dict | None = None):
        """Record an audit event."""
        if event_type not in self.EVENT_TYPES:
            logger.warning(f"Unknown audit event type: {event_type}")

        entry = {
            "schema_version": self.SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "actor": actor,
            "detail": detail or {},
        }
        line = json.dumps(entry, ensure_ascii=False)

        with self._lock:
            try:
                with open(self._file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                logger.error(f"Failed to write audit log: {e}")

    def query(self, event_type: str = "", limit: int = 100) -> list[dict]:
        """Read recent audit events."""
        results: list[dict] = []
        if not self._file.exists():
            return results

        try:
            lines = self._file.read_text(encoding="utf-8").strip().split("\n")
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if event_type and entry.get("event") != event_type:
                        continue
                    results.append(entry)
                    if len(results) >= limit:
                        break
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

        return results
