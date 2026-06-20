"""M2a Task 2 — Real 4-tier Risk Router。

设计：
- 输入：真实推理结果（primary_dx、evidence、candidates、payment_risk 等）
- 输出：low / medium / high / critical 4 档
- 动作矩阵（与 docs/ICODER_V3_OPTIMIZED_RUNTIME_SPEC.md §3.6 对齐）：

  | 档位 | 自动写回 | 草稿写回 | 强制人工 | 医保上传 |
  |---|---|---|---|---|
  | low         | ✅ | ✅ | ❌ | ✅ |
  | medium      | ❌ | ✅ | ❌ | ❌ |
  | high        | ❌ | ✅ | ✅ | ❌ |
  | critical    | ❌ | ❌ | ✅ | ❌（block） |

特殊规则：
- 任何 primary_dx_change_possible 必为 critical
- sample 数据进入生产 trace → critical + 拒绝（绝不静默通过）
- evidence_grounded=False + payment_risk_high=True → critical
- adjudicator_rule_conflict → critical
- safety_rule_triggered → critical
- high_risk_coding_point_hit → high
- evidence_weak / candidate_scores_close → medium
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


RISK_LEVELS = ("low", "medium", "high", "critical")


@dataclass
class RiskAction:
    auto_apply_allowed: bool
    draft_writeback_allowed: bool
    manual_review_required: bool
    payment_upload_allowed: bool
    block_insurance_upload: bool
    requires_human: bool
    description_zh: str


ACTION_MATRIX: dict[str, RiskAction] = {
    "low": RiskAction(
        auto_apply_allowed=True,
        draft_writeback_allowed=True,
        manual_review_required=False,
        payment_upload_allowed=True,
        block_insurance_upload=False,
        requires_human=False,
        description_zh="可自动建议或自动写回，不需要人工复核",
    ),
    "medium": RiskAction(
        auto_apply_allowed=False,
        draft_writeback_allowed=True,
        manual_review_required=False,
        payment_upload_allowed=False,
        block_insurance_upload=False,
        requires_human=False,
        description_zh="只允许生成草稿建议，不自动写回病案首页，不上传医保（草稿可由人工编辑后确认）",
    ),
    "high": RiskAction(
        auto_apply_allowed=False,
        draft_writeback_allowed=True,
        manual_review_required=True,
        payment_upload_allowed=False,
        block_insurance_upload=False,
        requires_human=True,
        description_zh="需要人工复核，不允许自动写回，不上传医保（草稿可由人工编辑后强制复核）",
    ),
    "critical": RiskAction(
        auto_apply_allowed=False,
        draft_writeback_allowed=False,
        manual_review_required=True,
        payment_upload_allowed=False,
        block_insurance_upload=True,
        requires_human=True,
        description_zh="必须阻断自动写回和草稿写回，强制人工审查或退回补充材料；不允许医保上传",
    ),
}


@dataclass
class RiskRouteResult:
    risk_level: str
    risk_reasons: list[str] = field(default_factory=list)
    actions: dict[str, Any] = field(default_factory=dict)
    sample_rejected: bool = False
    primary_dx_change_possible: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class RiskRouter:
    """4 档风险路由器。"""

    def route(
        self,
        indicators: dict[str, Any] | None = None,
        *,
        is_sample: bool = False,
        data_source: str = "real",
        production_allowed: bool = True,
    ) -> RiskRouteResult:
        """根据推理结果判定风险等级。

        Args:
            indicators: 业务指标（primary_dx_change_possible, evidence_grounded 等）
            is_sample: 是否为占位模拟数据
            data_source: "real" | "desensitized" | "sample"
            production_allowed: 调用方是否声明该数据可用于生产

        Returns:
            RiskRouteResult — 含 risk_level、reasons、actions、sample_rejected 标志
        """
        indicators = indicators or {}
        reasons: list[str] = []

        # sample data → 强制 critical + 拒绝
        if is_sample or data_source == "sample" or not production_allowed:
            reasons.append("占位模拟数据（is_sample=True）被路由到生产 trace — 强制 critical + 拒绝")
            return RiskRouteResult(
                risk_level="critical",
                risk_reasons=reasons,
                actions=asdict(ACTION_MATRIX["critical"]),
                sample_rejected=True,
                primary_dx_change_possible=False,
            )

        # primary dx change 必为 critical
        if indicators.get("primary_dx_change_possible") is True:
            reasons.append("主诊断可能改变（影响 DRG/DIP 入组）")

        # evidence ungrounded + payment risk high → critical
        if (
            indicators.get("evidence_grounded") is False
            and indicators.get("payment_risk_high") is True
        ):
            reasons.append("证据无法回链且支付风险高")

        # safety rule triggered → critical
        if indicators.get("safety_rule_triggered") is True:
            reasons.append("规则治理内核安全类规则触发")

        # adjudicator conflict → critical
        if indicators.get("adjudicator_rule_conflict") is True:
            reasons.append("裁决器与规则审核冲突")

        if reasons:
            return RiskRouteResult(
                risk_level="critical",
                risk_reasons=reasons,
                actions=asdict(ACTION_MATRIX["critical"]),
                primary_dx_change_possible=indicators.get("primary_dx_change_possible") is True,
            )

        # high risk 触发
        if (
            indicators.get("high_risk_coding_point_hit") is True
            or indicators.get("other_dx_affects_drg") is True
            or indicators.get("payment_risk_medium") is True
        ):
            if indicators.get("high_risk_coding_point_hit") is True:
                reasons.append("命中高风险易错编码点（原 SoftSpot 概念）")
            if indicators.get("other_dx_affects_drg") is True:
                reasons.append("其他诊断可能影响 DRG/DIP")
            if indicators.get("payment_risk_medium") is True:
                reasons.append("支付风险中等")
            return RiskRouteResult(
                risk_level="high",
                risk_reasons=reasons,
                actions=asdict(ACTION_MATRIX["high"]),
            )

        # medium risk
        if indicators.get("evidence_weak") is True or indicators.get("candidate_scores_close") is True:
            if indicators.get("evidence_weak") is True:
                reasons.append("存在轻微证据不足")
            if indicators.get("candidate_scores_close") is True:
                reasons.append("候选码分数接近")
            return RiskRouteResult(
                risk_level="medium",
                risk_reasons=reasons,
                actions=asdict(ACTION_MATRIX["medium"]),
            )

        # default: low
        return RiskRouteResult(
            risk_level="low",
            risk_reasons=[],
            actions=asdict(ACTION_MATRIX["low"]),
        )

    def can_writeback(self, level: str, kind: str = "auto") -> bool:
        """检查某档位是否允许某类写回。

        kind: "auto" | "draft" | "payment"
        """
        action = ACTION_MATRIX.get(level)
        if not action:
            raise ValueError(f"Unknown risk level: {level}")
        if kind == "auto":
            return action.auto_apply_allowed
        if kind == "draft":
            return action.draft_writeback_allowed
        if kind == "payment":
            return action.payment_upload_allowed
        raise ValueError(f"Unknown writeback kind: {kind}")
