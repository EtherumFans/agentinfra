"""M2a 共享存储：JSONL append-only + sample/production 物理隔离。

两张表：
- production_runs.jsonl — 真实数据（拒绝 is_sample）
- sample_runs.jsonl    — 占位模拟数据（永远不允许进入 production trace）

API：
- append_production(record)  — 写入并校验 is_sample: true 一律拒绝
- append_sample(record)      — 写入 sample trace
- query_production(...)      — 只查 production
- query_sample(...)          — 只查 sample
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class M2aStore:
    """JSONL append-only store with hard sample/production separation."""

    PRODUCTION_FILE = "production_runs.jsonl"
    SAMPLE_FILE = "sample_runs.jsonl"

    def __init__(self, storage_dir: str | Path | None = None):
        self._dir = (
            Path(storage_dir)
            if storage_dir is not None
            else Path(os.environ.get("ICODER_REGISTRY_DIR", ".icoder")) / "m2a"
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._prod_path = self._dir / self.PRODUCTION_FILE
        self._sample_path = self._dir / self.SAMPLE_FILE

    def _is_sample_payload(self, record: dict[str, Any]) -> bool:
        """检查 record 是否携带 sample 标记。

        任何一项命中即视为 sample:
        - is_sample == true
        - data_source == "sample"
        - production_allowed == false
        """
        if record.get("is_sample") is True:
            return True
        if record.get("data_source") == "sample":
            return True
        if record.get("production_allowed") is False:
            return True
        return False

    def append_production(self, record: dict[str, Any]) -> None:
        """写入生产 trace。如果 is_sample 为 true 则拒绝并抛 ValueError。"""
        if self._is_sample_payload(record):
            raise ValueError(
                "M2a: sample data is REJECTED from production trace. "
                f"run_id={record.get('run_id')} data_source={record.get('data_source')}"
            )
        record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        record.setdefault("data_source", "real")
        record.setdefault("production_allowed", True)
        self._append(self._prod_path, record)

    def append_sample(self, record: dict[str, Any]) -> None:
        """写入 sample trace。强制加 is_sample: true。"""
        record["is_sample"] = True
        record["data_source"] = "sample"
        record["production_allowed"] = False
        record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._append(self._sample_path, record)

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                logger.error(f"M2a: failed to write to {path}: {e}")
                raise

    def query_production(self, limit: int = 100, agent_ref: str = "") -> list[dict]:
        return self._query(self._prod_path, limit, agent_ref)

    def query_sample(self, limit: int = 100, agent_ref: str = "") -> list[dict]:
        return self._query(self._sample_path, limit, agent_ref)

    def _query(self, path: Path, limit: int, agent_ref: str) -> list[dict]:
        results: list[dict] = []
        if not path.exists():
            return results
        with self._lock:
            try:
                lines = path.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if agent_ref and entry.get("agent_ref") != agent_ref:
                        continue
                    results.append(entry)
                    if len(results) >= limit:
                        break
            except OSError as e:
                logger.error(f"M2a: query failed for {path}: {e}")
        return results

    def get(self, run_id: str) -> dict | None:
        for path in (self._prod_path, self._sample_path):
            for entry in self._query(path, limit=1000, agent_ref=""):
                if entry.get("run_id") == run_id:
                    return entry
        return None

    @property
    def production_count(self) -> int:
        return self._count(self._prod_path)

    @property
    def sample_count(self) -> int:
        return self._count(self._sample_path)

    def _count(self, path: Path) -> int:
        if not path.exists():
            return 0
        with self._lock:
            try:
                return sum(1 for line in open(path, encoding="utf-8") if line.strip())
            except OSError:
                return 0
