"""Shadow Diff — compares legacy and PlatformRuntime results in shadow mode."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShadowRunLog:
    """Record of a single shadow mode comparison."""

    run_id: str = ""
    agent_ref: str = ""
    timestamp: str = ""
    legacy_status: str = ""
    platform_status: str = ""
    legacy_primary_dx: str = ""
    platform_primary_dx: str = ""
    legacy_secondary_count: int = 0
    platform_secondary_count: int = 0
    legacy_procedure_count: int = 0
    platform_procedure_count: int = 0
    legacy_latency_ms: int = 0
    platform_latency_ms: int = 0
    diagnosis_match: bool = False
    procedure_match: bool = False
    conclusion_match: bool = False
    fields_compared: list[str] = field(default_factory=list)
    diffs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent_ref": self.agent_ref,
            "timestamp": self.timestamp,
            "legacy_status": self.legacy_status,
            "platform_status": self.platform_status,
            "legacy_primary_dx": self.legacy_primary_dx,
            "platform_primary_dx": self.platform_primary_dx,
            "legacy_secondary_count": self.legacy_secondary_count,
            "platform_secondary_count": self.platform_secondary_count,
            "legacy_procedure_count": self.legacy_procedure_count,
            "platform_procedure_count": self.platform_procedure_count,
            "legacy_latency_ms": self.legacy_latency_ms,
            "platform_latency_ms": self.platform_latency_ms,
            "diagnosis_match": self.diagnosis_match,
            "procedure_match": self.procedure_match,
            "conclusion_match": self.conclusion_match,
            "fields_compared": self.fields_compared,
            "diffs": self.diffs,
        }


class ShadowDiffService:
    """Compares legacy and PlatformRuntime results, persists ShadowRunLog entries."""

    SCHEMA_VERSION = "1.0"

    def __init__(self, storage_dir: str | Path = ".icoder"):
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "shadow_run_log.jsonl"
        self._lock = threading.Lock()

    def compare_and_record(
        self,
        legacy_result: dict,
        platform_result: dict,
        agent_ref: str = "",
    ) -> ShadowRunLog:
        """Compare two results and record the diff."""
        # Extract fields for comparison
        l_structured = legacy_result.get("structured") or {}
        p_structured = platform_result.get("structured") or {}

        l_dx = (legacy_result.get("primary_diagnosis") or l_structured.get("primary_diagnosis") or {})
        p_dx = (platform_result.get("primary_diagnosis") or p_structured.get("primary_diagnosis") or {})

        l_code = l_dx.get("code", "")
        p_code = p_dx.get("code", "")

        l_sec = legacy_result.get("secondary_diagnoses", []) or l_structured.get("secondary_diagnoses", [])
        p_sec = platform_result.get("secondary_diagnoses", []) or p_structured.get("secondary_diagnoses", [])

        l_proc = legacy_result.get("procedures", []) or l_structured.get("procedures", [])
        p_proc = platform_result.get("procedures", []) or p_structured.get("procedures", [])

        l_conc = l_structured.get("review_conclusion", "")
        p_conc = p_structured.get("review_conclusion", "")

        # Compute diffs
        diffs: list[dict] = []
        fields_compared = ["primary_diagnosis.code", "secondary_diagnoses.count",
                          "procedures.count", "review_conclusion", "processing_time_ms"]

        if l_code != p_code:
            diffs.append({"field": "primary_diagnosis.code", "legacy": l_code, "platform": p_code})
        if l_conc != p_conc:
            diffs.append({"field": "review_conclusion", "legacy": l_conc, "platform": p_conc})

        log_entry = ShadowRunLog(
            run_id=legacy_result.get("review_id", platform_result.get("run_id", "")),
            agent_ref=agent_ref,
            timestamp=datetime.now(timezone.utc).isoformat(),
            legacy_status=str(legacy_result.get("status", "unknown")),
            platform_status=str(platform_result.get("status", "unknown")),
            legacy_primary_dx=l_code,
            platform_primary_dx=p_code,
            legacy_secondary_count=len(l_sec),
            platform_secondary_count=len(p_sec),
            legacy_procedure_count=len(l_proc),
            platform_procedure_count=len(p_proc),
            legacy_latency_ms=legacy_result.get("processing_time_ms", 0),
            platform_latency_ms=platform_result.get("processing_time_ms", 0),
            diagnosis_match=(l_code == p_code),
            procedure_match=(len(l_proc) == len(p_proc)),
            conclusion_match=(l_conc == p_conc),
            fields_compared=fields_compared,
            diffs=diffs,
        )

        self._persist(log_entry)
        return log_entry

    def _persist(self, entry: ShadowRunLog):
        data = entry.to_dict()
        data["schema_version"] = self.SCHEMA_VERSION
        line = json.dumps(data, ensure_ascii=False)

        with self._lock:
            try:
                with open(self._file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                logger.error(f"Failed to write shadow run log: {e}")

    def stats(self, hours: int = 24) -> dict[str, Any]:
        """Compute shadow diff statistics."""
        cutoff = datetime.now(timezone.utc)
        total = 0
        dx_match = 0
        conc_match = 0
        proc_match = 0

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
                total += 1
                if entry.get("diagnosis_match"):
                    dx_match += 1
                if entry.get("conclusion_match"):
                    conc_match += 1
                if entry.get("procedure_match"):
                    proc_match += 1
        except (OSError, json.JSONDecodeError):
            pass

        return {
            "total_comparisons": total,
            "diagnosis_match_rate": round(dx_match / max(total, 1), 4),
            "conclusion_match_rate": round(conc_match / max(total, 1), 4),
            "procedure_match_rate": round(proc_match / max(total, 1), 4),
            "window_hours": hours,
        }

    def _empty_stats(self) -> dict:
        return {
            "total_comparisons": 0,
            "diagnosis_match_rate": 0.0,
            "conclusion_match_rate": 0.0,
            "procedure_match_rate": 0.0,
            "window_hours": 24,
        }
