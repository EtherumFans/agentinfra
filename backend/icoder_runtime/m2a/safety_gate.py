"""M2a Task 3 — Medical Safety Gate（医学安全门禁）计算器。

12 指标 + 8 发布门禁规则（与 docs/ICODER_V3_OPTIMIZED_RUNTIME_SPEC.md §3.5A 对齐）。

输入：12 个指标的实际数值（来自真实金标准评测或 runtime 实时采集）
输出：
- status: "pass" | "warning" | "block"
- blocked_metrics: 阻断列表
- warning_metrics: 警告列表
- release_blocked: 阻断发布
- insurance_upload_blocked: 阻断医保上传
- human_required: 强制人工复核
- triggered_rules: 触发的规则 ID 列表
- primary_dx_change_blocked: 主诊断改变是否被阻断（不依赖阈值，硬阻断）
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ============================================================
# 12 项指标（与前端 icoderQualityMetrics.ts 对齐）
# ============================================================

MEDICAL_SAFETY_METRICS: list[dict[str, Any]] = [
    {"id": "primary_dx_damage_rate", "higher_is_better": False, "threshold": 0.0, "block_on_violation": True},
    {"id": "primary_dx_auto_replace_rate", "higher_is_better": False, "threshold": 0.0, "block_on_violation": True},
    {"id": "other_dx_overcode_rate", "higher_is_better": False, "threshold": 0.05, "block_on_violation": True},
    {"id": "other_dx_miss_rate", "higher_is_better": False, "threshold": 0.10, "block_on_violation": True},
    {"id": "procedure_net_fix_rate", "higher_is_better": True, "threshold": 0.85, "block_on_violation": True},
    {"id": "evidence_grounding_rate", "higher_is_better": True, "threshold": 0.95, "block_on_violation": True},
    {"id": "unsupported_code_rate", "higher_is_better": False, "threshold": 0.03, "block_on_violation": False},
    {"id": "high_risk_coding_point_regression", "higher_is_better": True, "threshold": 0.95, "block_on_violation": True},
    {"id": "payment_risk_misjudge_rate", "higher_is_better": False, "threshold": 0.05, "block_on_violation": True},
    {"id": "human_review_consistency_rate", "higher_is_better": True, "threshold": 0.85, "block_on_violation": False},
    {"id": "rule_conflict_unresolved_rate", "higher_is_better": False, "threshold": 0.0, "block_on_violation": True},
    {"id": "auto_passed_no_evidence_count", "higher_is_better": False, "threshold": 0, "block_on_violation": True},
]


# ============================================================
# 8 条发布门禁规则（REL-001 ~ REL-008）
# ============================================================

RELEASE_GATE_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "REL-001",
        "metric_id": "primary_dx_damage_rate",
        "trigger": "primary_dx_damage_rate > 0",
        "action": "block_release",
        "description_zh": "主诊断损坏率 > 0 → 硬阻断发布（一票否决）",
    },
    {
        "rule_id": "REL-002",
        "metric_id": "primary_dx_auto_replace_rate",
        "trigger": "primary_dx_auto_replace_rate > 0",
        "action": "block_auto_writeback",
        "description_zh": "主诊断自动替换率 > 0 → 阻断自动写回 + 强制人工",
    },
    {
        "rule_id": "REL-003",
        "metric_id": "evidence_grounding_rate",
        "trigger": "evidence_grounding_rate < 0.95",
        "action": "block_release",
        "description_zh": "证据回链率 < 95% → 阻断生产发布",
    },
    {
        "rule_id": "REL-004",
        "metric_id": "unsupported_code_rate",
        "trigger": "unsupported_code_rate > 0.03",
        "action": "shadow_eval_only",
        "description_zh": "不支持编码率上升 → 进入影子评估",
    },
    {
        "rule_id": "REL-005",
        "metric_id": "high_risk_coding_point_regression",
        "trigger": "high_risk_coding_point_regression < 0.95",
        "action": "block_release",
        "description_zh": "高风险易错编码点回归失败 → 阻断发布",
    },
    {
        "rule_id": "REL-006",
        "metric_id": "payment_risk_misjudge_rate",
        "trigger": "payment_risk_misjudge_rate > 0.05",
        "action": "block_payment_upload",
        "description_zh": "医保支付风险误判率超阈值 → 阻断医保上传前自动放行",
    },
    {
        "rule_id": "REL-007",
        "metric_id": "auto_passed_no_evidence_count",
        "trigger": "auto_passed_no_evidence_count > 0",
        "action": "block_release_and_require_human",
        "description_zh": "证据无法回链但被自动通过的数量 > 0 → 强制人工 + 阻断发布",
    },
    {
        "rule_id": "REL-008",
        "metric_id": "evidence_grounding_rate",
        "trigger": "primary_dx_replace && !evidence_grounded",
        "action": "block_auto_writeback",
        "description_zh": "主诊断替换若证据无法回链 → 阻断自动写回 + 强制人工（不依赖阈值）",
    },
]


def _gate_status(value: float, threshold: float, higher_is_better: bool) -> str:
    """单指标门禁状态。"""
    if higher_is_better:
        if value >= threshold:
            return "pass"
        if value >= 0.95 * threshold:
            return "warning"
        return "block"
    else:
        if value <= threshold:
            return "pass"
        if value <= 1.05 * threshold:
            return "warning"
        return "block"


@dataclass
class SafetyGateResult:
    status: str  # pass | warning | block
    blocked_metrics: list[str] = field(default_factory=list)
    warning_metrics: list[str] = field(default_factory=list)
    release_blocked: bool = False
    insurance_upload_blocked: bool = False
    human_required: bool = False
    primary_dx_change_blocked: bool = False
    triggered_rules: list[str] = field(default_factory=list)
    metric_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class MedicalSafetyGate:
    """医学安全门禁计算器。"""

    def evaluate(
        self,
        metrics: dict[str, float] | None = None,
        *,
        primary_dx_change_attempted: bool = False,
        evidence_grounded: bool = True,
    ) -> SafetyGateResult:
        """计算医学安全门禁结果。

        Args:
            metrics: 12 项指标的实际数值
            primary_dx_change_attempted: 本次 run 是否尝试主诊断替换
            evidence_grounded: 主诊断是否可证据回链
        """
        metrics = metrics or {}
        blocked: list[str] = []
        warning: list[str] = []
        metric_status: dict[str, str] = {}
        triggered: list[str] = []
        release_blocked = False
        insurance_blocked = False
        human_required = False

        for m in MEDICAL_SAFETY_METRICS:
            mid = m["id"]
            if mid not in metrics:
                continue
            v = float(metrics[mid])
            status = _gate_status(v, m["threshold"], m["higher_is_better"])
            metric_status[mid] = status
            if status == "block":
                blocked.append(mid)
                if m["block_on_violation"]:
                    matched = next((r for r in RELEASE_GATE_RULES if r["metric_id"] == mid), None)
                    if matched:
                        triggered.append(matched["rule_id"])
                        if matched["action"] == "block_release":
                            release_blocked = True
                        elif matched["action"] == "block_payment_upload":
                            insurance_blocked = True
                        elif matched["action"] == "block_release_and_require_human":
                            release_blocked = True
                            human_required = True
                        elif matched["action"] == "block_auto_writeback":
                            human_required = True
            elif status == "warning":
                warning.append(mid)

        # 硬阻断：主诊断损坏
        primary_dx_change_blocked = False
        if primary_dx_change_attempted and not evidence_grounded:
            primary_dx_change_blocked = True
            triggered.append("REL-008")
            human_required = True
            release_blocked = True

        if release_blocked:
            status = "block"
        elif warning or primary_dx_change_blocked:
            status = "warning"
        else:
            status = "pass"

        return SafetyGateResult(
            status=status,
            blocked_metrics=blocked,
            warning_metrics=warning,
            release_blocked=release_blocked,
            insurance_upload_blocked=insurance_blocked,
            human_required=human_required,
            primary_dx_change_blocked=primary_dx_change_blocked,
            triggered_rules=triggered,
            metric_status=metric_status,
        )
