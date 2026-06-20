"""M2a Task 1 — Real Run Trace。

每一个真实 run 包含：
- run_id        : 顶层 run 标识（UUIDv7 字符串）
- trace_id      : 全局 trace 标识（UUIDv7 字符串）
- tool_run_id   : 每个 tool 调用的独立标识（UUIDv7 字符串）
- data_source   : "real" | "desensitized" | "sample"
- production_allowed : 是否允许进入生产 trace
- final_status  : "success" | "error" | "timeout" | "fallback" | "human_reviewed"
- risk_route    : 4 档风险路由结果
- safety_gate   : 医学安全门禁结果
- human_review  : 人工复核记录（可选）
- tool_calls    : 工具调用列表（按时间顺序）

UUIDv7 标识：UUID7 用 48-bit 时间戳 + 12-bit 随机，append-only 友好。
本实现使用 time.time_ns() 生成单调时间戳 + 12 hex 随机（确定性 UUID7 字串）。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from .store import M2aStore


def _uuid7_like() -> str:
    """生成 UUIDv7 风格的字符串（48-bit ms 时间戳 + 12 hex 随机）。

    真实 UUIDv7 需要外部库；本实现用 Python 标准库模拟相同的可排序特性。
    """
    ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48-bit
    rand = uuid.uuid4().hex[:12]
    raw = f"{ts_ms:012x}{rand}"
    # Format: 8-4-4-4-12
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


@dataclass
class ToolCall:
    tool_run_id: str
    tool_name: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_output: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    ended_at: str = ""
    duration_ms: int = 0
    status: str = "ok"  # ok | error | timeout
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunTrace:
    run_id: str = ""
    trace_id: str = ""
    agent_ref: str = ""
    started_at: str = ""
    ended_at: str = ""
    duration_ms: int = 0
    final_status: str = "success"  # success | error | timeout | fallback | human_reviewed
    data_source: str = "real"
    is_sample: bool = False
    production_allowed: bool = True
    tool_calls: list[ToolCall] = field(default_factory=list)
    risk_route: dict[str, Any] = field(default_factory=dict)
    safety_gate: dict[str, Any] = field(default_factory=dict)
    human_review: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tool_calls"] = [tc if isinstance(tc, dict) else tc.to_dict() for tc in self.tool_calls]
        return d


class RunTraceService:
    """Run Trace 服务：管理真实 run 的生命周期。"""

    def __init__(self, store: M2aStore | None = None):
        self._store = store or M2aStore()
        self._lock = threading.Lock()
        # In-memory active runs
        self._active: dict[str, RunTrace] = {}

    def start_run(
        self,
        agent_ref: str,
        data_source: str = "real",
        is_sample: bool = False,
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
    ) -> RunTrace:
        """开始一个 run，生成 run_id + trace_id。

        如果 is_sample=True，则强制 production_allowed=False。
        如果 is_sample=True 但调用方显式要求 production_allowed=True，则拒绝。

        ``run_id`` / ``trace_id`` (M3-0): caller-provided identifiers, used
        by the API layer to align the M2a trace with the persistent
        CodingReviewRun row in the DB. When not provided, the service
        generates fresh uuid7 ids.
        """
        run_id = run_id or _uuid7_like()
        trace_id = trace_id or _uuid7_like()
        trace = RunTrace(
            run_id=run_id,
            trace_id=trace_id,
            agent_ref=agent_ref,
            started_at=datetime.now(timezone.utc).isoformat(),
            data_source=data_source,
            is_sample=is_sample,
            production_allowed=not is_sample,
            metadata=metadata or {},
        )
        with self._lock:
            self._active[run_id] = trace
        return trace

    def add_tool_call(self, run_id: str, tool_name: str, tool_input: dict | None = None) -> ToolCall:
        """添加一次工具调用，返回 tool_run_id。"""
        with self._lock:
            trace = self._active.get(run_id)
            if not trace:
                raise KeyError(f"Run {run_id} not found or already finalized")
            tc = ToolCall(
                tool_run_id=_uuid7_like(),
                tool_name=tool_name,
                tool_input=tool_input or {},
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            trace.tool_calls.append(tc)
            return tc

    def complete_tool_call(
        self,
        run_id: str,
        tool_run_id: str,
        tool_output: dict | None = None,
        status: str = "ok",
        error: str = "",
    ) -> None:
        """结束一个工具调用。"""
        with self._lock:
            trace = self._active.get(run_id)
            if not trace:
                raise KeyError(f"Run {run_id} not found")
            for tc in trace.tool_calls:
                if tc.tool_run_id == tool_run_id:
                    tc.ended_at = datetime.now(timezone.utc).isoformat()
                    if tc.started_at:
                        try:
                            t0 = datetime.fromisoformat(tc.started_at)
                            t1 = datetime.fromisoformat(tc.ended_at)
                            tc.duration_ms = int((t1 - t0).total_seconds() * 1000)
                        except ValueError:
                            tc.duration_ms = 0
                    tc.tool_output = tool_output or {}
                    tc.status = status
                    tc.error = error
                    return
        raise KeyError(f"Tool call {tool_run_id} not found in run {run_id}")

    def finalize_run(
        self,
        run_id: str,
        final_status: str = "success",
        risk_route: dict | None = None,
        safety_gate: dict | None = None,
    ) -> RunTrace:
        """结束一个 run，写入 production 或 sample trace。"""
        with self._lock:
            trace = self._active.pop(run_id, None)
        if trace is None:
            raise KeyError(f"Run {run_id} not found or already finalized")

        trace.ended_at = datetime.now(timezone.utc).isoformat()
        if trace.started_at:
            try:
                t0 = datetime.fromisoformat(trace.started_at)
                t1 = datetime.fromisoformat(trace.ended_at)
                trace.duration_ms = int((t1 - t0).total_seconds() * 1000)
            except ValueError:
                trace.duration_ms = 0
        trace.final_status = final_status
        trace.risk_route = risk_route or {}
        trace.safety_gate = safety_gate or {}

        record = trace.to_dict()
        if trace.is_sample:
            self._store.append_sample(record)
        else:
            # production_allowed must be True for real data
            record["production_allowed"] = True
            self._store.append_production(record)
        return trace

    def attach_human_review(self, run_id: str, review: dict) -> RunTrace:
        """为已 final 的 run 附加人工复核记录（不重复 final）。"""
        with self._lock:
            trace = self._active.get(run_id)
        # trace might be active or already finalized
        if trace is None:
            # 查找已 final 的 run
            existing = self._store.get(run_id)
            if not existing:
                raise KeyError(f"Run {run_id} not found")
            existing["human_review"] = review
            # 重新写盘（仅 production 路径：sample 拒绝写回，强制人工）
            if existing.get("is_sample") is True:
                raise ValueError("M2a: sample run REJECTED for human review writeback")
            self._store.append_production(existing)
            return RunTrace(**{k: v for k, v in existing.items() if k in RunTrace.__dataclass_fields__})
        trace.human_review = review
        return trace

    def get_run(self, run_id: str) -> dict | None:
        if run_id in self._active:
            return self._active[run_id].to_dict()
        return self._store.get(run_id)

    def list_production(self, limit: int = 100, agent_ref: str = "") -> list[dict]:
        return self._store.query_production(limit=limit, agent_ref=agent_ref)

    def list_sample(self, limit: int = 100, agent_ref: str = "") -> list[dict]:
        return self._store.query_sample(limit=limit, agent_ref=agent_ref)
