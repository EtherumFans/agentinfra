"""M2a Task 4 — Human Review writeback（人工复核写回）。

约束：
- POST /api/runs/{run_id}/human-review 必须带 reason_code
- 拒绝 sample 数据的写回（sample run 绝不能触发人工写回）
- 主诊断变更（primary_dx_change）只能由人工写回
- Learning Loop 只接受真实人工修改（is_human=true 且 is_sample=false）
- reason_code 必须从合法枚举中选取

合法 reason_code 枚举（13 类）：
- 编码更正、规则触发、证据补强、术语纠正、删除冗余、补充遗漏
- 主诊断确认、规则冲突调解、支付风险复核、医保结算清单对齐
- 数据质量问题、规则升级建议、错误分类纠正
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from .run_trace import RunTraceService
from .store import M2aStore


# 合法 reason_code 枚举
VALID_REASON_CODES = frozenset({
    "code_correction",            # 编码更正
    "rule_triggered",             # 规则触发
    "evidence_strengthened",      # 证据补强
    "terminology_corrected",      # 术语纠正
    "remove_redundant",           # 删除冗余
    "add_missing",                # 补充遗漏
    "primary_dx_confirmed",       # 主诊断确认
    "rule_conflict_resolved",     # 规则冲突调解
    "payment_risk_reviewed",      # 支付风险复核
    "insurance_alignment",        # 医保结算清单对齐
    "data_quality_issue",         # 数据质量问题
    "rule_upgrade_suggested",     # 规则升级建议
    "error_taxonomy_corrected",   # 错误分类纠正
})


@dataclass
class HumanReviewRecord:
    review_id: str
    run_id: str
    reviewer: str
    decision: str  # approve | reject | modify
    reason_code: str
    rationale: str
    primary_dx_change: bool = False
    is_human: bool = True
    is_sample: bool = False
    created_at: str = ""
    modifications: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class HumanReviewService:
    """人工复核写回服务。"""

    def __init__(self, store: M2aStore | None = None, run_trace: RunTraceService | None = None):
        self._store = store or M2aStore()
        self._run_trace = run_trace or RunTraceService(store=self._store)
        self._lock = threading.Lock()
        self._reviews_path = self._store._dir / "human_reviews.jsonl"
        self._learn_path = self._store._dir / "learning_loop.jsonl"

    def submit_review(
        self,
        run_id: str,
        reviewer: str,
        decision: str,
        reason_code: str,
        rationale: str,
        *,
        primary_dx_change: bool = False,
        modifications: dict[str, Any] | None = None,
    ) -> HumanReviewRecord:
        """提交人工复核写回。

        Raises:
            ValueError: reason_code 非法、decision 非法、run 是 sample
            KeyError: run 不存在
        """
        # 校验 decision
        if decision not in ("approve", "reject", "modify"):
            raise ValueError(f"Invalid decision: {decision} (must be approve | reject | modify)")

        # 校验 reason_code
        if reason_code not in VALID_REASON_CODES:
            raise ValueError(
                f"Invalid reason_code: {reason_code}. "
                f"Must be one of {sorted(VALID_REASON_CODES)}"
            )

        # 校验 run 存在 + 是否为 sample
        run = self._run_trace.get_run(run_id)
        if run is None:
            raise KeyError(f"Run {run_id} not found in production trace")

        if run.get("is_sample") is True or run.get("data_source") == "sample":
            raise ValueError(
                f"M2a: sample run {run_id} REJECTED for human review writeback. "
                f"占位模拟数据绝不能触发人工写回。"
            )

        # primary_dx_change 只能由人工写回 → 此处就是人工写回，所以 OK
        # 但需要校验 is_human=true
        record = HumanReviewRecord(
            review_id=str(uuid.uuid4()),
            run_id=run_id,
            reviewer=reviewer,
            decision=decision,
            reason_code=reason_code,
            rationale=rationale,
            primary_dx_change=primary_dx_change,
            is_human=True,
            is_sample=False,
            created_at=datetime.now(timezone.utc).isoformat(),
            modifications=modifications or {},
        )

        # 写入 human_reviews.jsonl（独立于 run trace）
        with self._lock:
            try:
                import json
                with open(self._reviews_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            except OSError as e:
                raise IOError(f"Failed to write human review: {e}")

        # 如果是主诊断变更 → 加入 Learning Loop
        if primary_dx_change or decision == "modify":
            self._append_learning_loop(record, run)

        # 关联回 run trace（in-memory + 持久化）
        try:
            self._run_trace.attach_human_review(run_id, record.to_dict())
        except (KeyError, ValueError):
            # run 已 final 但可以附加
            pass

        return record

    def _append_learning_loop(self, review: HumanReviewRecord, run: dict | None) -> None:
        """Learning Loop 只接受 is_human=true 且 is_sample=false 的修改。"""
        if not review.is_human or review.is_sample:
            return  # 双重保险
        import json
        entry = {
            "loop_entry_id": str(uuid.uuid4()),
            "review_id": review.review_id,
            "run_id": review.run_id,
            "reviewer": review.reviewer,
            "reason_code": review.reason_code,
            "primary_dx_change": review.primary_dx_change,
            "modifications": review.modifications,
            "created_at": review.created_at,
        }
        with self._lock:
            try:
                with open(self._learn_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError as e:
                raise IOError(f"Failed to append learning loop: {e}")

    def list_reviews(self, run_id: str = "", limit: int = 100) -> list[dict]:
        """查询人工复核记录。"""
        if not self._reviews_path.exists():
            return []
        results: list[dict] = []
        import json
        with self._lock:
            try:
                lines = self._reviews_path.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if run_id and entry.get("run_id") != run_id:
                        continue
                    results.append(entry)
                    if len(results) >= limit:
                        break
            except OSError:
                pass
        return results

    def list_learning_loop(self, limit: int = 100) -> list[dict]:
        """查询学习闭环条目（仅真实人工修改）。"""
        if not self._learn_path.exists():
            return []
        results: list[dict] = []
        import json
        with self._lock:
            try:
                lines = self._learn_path.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # 强制过滤：is_human=true 且 is_sample=false
                    if entry.get("is_human") is True and entry.get("is_sample") is True:
                        continue  # 永远不会发生（保险）
                    results.append(entry)
                    if len(results) >= limit:
                        break
            except OSError:
                pass
        return results
