"""RunHistory — persistent store of agent execution records."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from icoder_runtime.core.runtime_result import RuntimeRunResult

logger = logging.getLogger(__name__)


class RunHistoryStore:
    """Append-only store of RuntimeRunResult records as JSONL."""

    SCHEMA_VERSION = "1.0"

    def __init__(self, storage_dir: str | Path = ".icoder", persist_full_input: bool = True):
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "run_history.jsonl"
        self._lock = threading.Lock()
        self.persist_full_input = persist_full_input

    def record(self, result: RuntimeRunResult, input_text: str = ""):
        """Append a run result to the history."""
        entry = {
            "schema_version": self.SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": result.run_id,
            "agent_ref": result.agent_ref,
            "status": result.status,
            "processing_time_ms": result.processing_time_ms,
            "primary_diagnosis_code": result.primary_diagnosis.get("code", ""),
            "primary_diagnosis_description": result.primary_diagnosis.get("description", ""),
            "review_conclusion": result.structured.get("review_conclusion", "") if result.structured else "",
            "issues_count": len(result.issues_found),
            "errors": result.errors,
        }
        if self.persist_full_input:
            entry["input_preview"] = input_text[:500]

        line = json.dumps(entry, ensure_ascii=False)

        with self._lock:
            try:
                with open(self._file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                logger.error(f"Failed to write run history: {e}")

    def query(self, agent_ref: str = "", limit: int = 50) -> list[dict]:
        """Read recent run history entries, optionally filtered by agent_ref."""
        results: list[dict] = []
        if not self._file.exists():
            return results

        with self._lock:
            try:
                lines = self._file.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if agent_ref and entry.get("agent_ref") != agent_ref:
                            continue
                        results.append(entry)
                        if len(results) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
            except OSError:
                pass

        return results

    def get(self, run_id: str) -> dict | None:
        """Get a single run by run_id."""
        for entry in self.query(limit=1000):
            if entry.get("run_id") == run_id:
                return entry
        return None

    @property
    def run_count(self) -> int:
        if not self._file.exists():
            return 0
        try:
            return sum(1 for _ in open(self._file, encoding="utf-8") if _.strip())
        except OSError:
            return 0
