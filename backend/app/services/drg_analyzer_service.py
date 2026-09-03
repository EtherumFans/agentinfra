"""Auditable output for the development-only DRG/DIP risk-review adapter.

The local mapping produces non-authoritative candidates only.  It cannot
calculate official grouping, weight, DIP score, payment or settlement values.

Pipeline:
  encoded_codes → group_drg() → rule_engine.validate("drg_dip", ...)
  → DRGOutputSchema → RuntimeRunResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── DRG Impact Analysis ──


@dataclass
class DRGImpact:
    """Non-authoritative DRG candidate for risk review."""
    predicted_drg: str = ""           # Backward-compatible candidate field.
    drg_name: str = ""
    mdc: str = ""                     # MDCF / MDCE ...
    mdc_name: str = ""
    adrg: str = ""                    # ADRG code (FR / EC / IA ...)
    cc_level: str = ""                # 不伴合并症 / CC / MCC
    grouping_method: str = ""         # surgical / medical
    coverage: bool = False            # grouper 是否找到分组
    payment_weight: float = 0.0       # Always zero without authorized rules.
    payment_estimate_yuan: float = 0.0
    billing_authoritative: bool = False
    result_status: str = "experimental_candidate"

    def to_dict(self) -> dict:
        return {
            "predicted_drg": self.predicted_drg,
            "drg_name": self.drg_name,
            "mdc": self.mdc,
            "mdc_name": self.mdc_name,
            "adrg": self.adrg,
            "cc_level": self.cc_level,
            "grouping_method": self.grouping_method,
            "coverage": self.coverage,
            "payment_weight": self.payment_weight,
            "payment_estimate_yuan": self.payment_estimate_yuan,
            "billing_authoritative": self.billing_authoritative,
            "result_status": self.result_status,
        }


@dataclass
class DIPImpact:
    """DIP placeholder; official scores require an authorized regional pack."""
    dip_score: float = 0.0
    dip_score_ceiling: float = 0.0    # DIP 分值上限
    payment_estimate_yuan: float = 0.0
    note: str = ""
    billing_authoritative: bool = False

    def to_dict(self) -> dict:
        return {
            "dip_score": self.dip_score,
            "dip_score_ceiling": self.dip_score_ceiling,
            "payment_estimate_yuan": self.payment_estimate_yuan,
            "note": self.note,
            "billing_authoritative": self.billing_authoritative,
        }


@dataclass
class DRGRisk:
    """DRG/DIP 风险点."""
    rule_id: str = ""           # DRG001 / DIP003 ...
    severity: str = ""          # critical / high / medium / low / info
    risk_type: str = ""         # grouping / payment / compliance
    message: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "risk_type": self.risk_type,
            "message": self.message,
            "suggestion": self.suggestion,
        }


# ── Top-level Output Schema ──


@dataclass
class DRGOutputSchema:
    """DRG 分析器标准输出."""

    # 输入回显
    primary_diagnosis: dict = field(default_factory=dict)
    secondary_diagnoses: list[dict] = field(default_factory=list)
    procedures: list[dict] = field(default_factory=list)

    # 分组结果
    drg_impact: DRGImpact = field(default_factory=DRGImpact)
    dip_impact: DIPImpact = field(default_factory=DIPImpact)

    # 风险与建议
    risks: list[DRGRisk] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # 质量标志
    quality_flags: dict = field(default_factory=dict)
    governance: dict = field(default_factory=dict)
    manual_review_required: bool = True

    # 总结
    review_conclusion: str = "PASS"   # PASS | WARNING | FAIL
    confidence: float = 0.0
    notes: str = ""

    # 元数据
    provider: str = ""          # 哪个 provider 产出
    model: str = ""
    is_mock: bool = False
    error: bool = False
    error_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_diagnosis": self.primary_diagnosis,
            "secondary_diagnoses": self.secondary_diagnoses,
            "procedures": self.procedures,
            "drg_impact": self.drg_impact.to_dict(),
            "dip_impact": self.dip_impact.to_dict(),
            "risks": [r.to_dict() for r in self.risks],
            "recommendations": self.recommendations,
            "quality_flags": self.quality_flags,
            "governance": self.governance,
            "manual_review_required": self.manual_review_required,
            "review_conclusion": self.review_conclusion,
            "confidence": self.confidence,
            "notes": self.notes,
            "provider": self.provider,
            "model": self.model,
            "is_mock": self.is_mock,
            "error": self.error,
            "error_reason": self.error_reason,
        }

    @classmethod
    def from_rule_validation(
        cls,
        rule_result: Any,  # RuleValidationResult
        grouper_result: dict,
        primary_diagnosis: dict,
        secondary_diagnoses: list[dict],
        procedures: list[dict],
        dip_impact: DIPImpact | None = None,
    ) -> "DRGOutputSchema":
        """Build DRGOutputSchema from rule engine + grouper results."""
        risks: list[DRGRisk] = []
        recommendations: list[str] = []

        # Map severity → risk_type
        sev_to_risk = {
            "critical": "compliance",
            "high": "payment",
            "medium": "payment",
            "low": "grouping",
            "info": "grouping",
        }

        for issue in rule_result.issues:
            risks.append(DRGRisk(
                rule_id=issue.rule_id,
                severity=issue.severity,
                risk_type=sev_to_risk.get(issue.severity, "grouping"),
                message=issue.message,
                suggestion=issue.suggestion,
            ))
            if issue.suggestion and issue.severity in ("critical", "high", "medium"):
                recommendations.append(issue.suggestion)

        # DRG impact from grouper
        drg_impact = DRGImpact(
            predicted_drg=grouper_result.get("drg", ""),
            drg_name=grouper_result.get("drg_name", ""),
            mdc=grouper_result.get("mdc", ""),
            mdc_name=grouper_result.get("mdc_name", ""),
            adrg=grouper_result.get("adrg", ""),
            cc_level=grouper_result.get("cc_level", ""),
            grouping_method=grouper_result.get("grouping_method", ""),
            coverage=grouper_result.get("coverage", False),
            payment_weight=0.0,
            payment_estimate_yuan=0.0,
            billing_authoritative=False,
            result_status="experimental_candidate",
        )

        # Determine review conclusion
        critical_count = sum(1 for r in risks if r.severity == "critical")
        high_count = sum(1 for r in risks if r.severity == "high")

        if critical_count > 0:
            review_conclusion = "FAIL"
        elif high_count > 0 or rule_result.manual_review_required:
            review_conclusion = "WARNING"
        else:
            # An unverified rule pack can never produce an automatic PASS.
            review_conclusion = "WARNING"

        # Confidence based on coverage
        confidence = 0.50 if grouper_result.get("coverage") else 0.0
        governance = grouper_result.get("governance", {})

        return cls(
            primary_diagnosis=primary_diagnosis,
            secondary_diagnoses=secondary_diagnoses,
            procedures=procedures,
            drg_impact=drg_impact,
            dip_impact=dip_impact or DIPImpact(),
            risks=risks,
            recommendations=recommendations,
            quality_flags=rule_result.quality_flags or {},
            governance=governance,
            manual_review_required=True,
            review_conclusion=review_conclusion,
            confidence=confidence,
            notes=(
                "Development-only DRG/DIP risk heuristic; not an official "
                "grouper or settlement result. Manual review is required. "
                f"heuristic_method={grouper_result.get('grouping_method', 'N/A')}"
            ),
            provider="drg-analyzer",
            model="icoder-drg-dip-risk-heuristics-1.0.0-development",
            is_mock=False,
        )

    @classmethod
    def failure_result(cls, reason: str) -> "DRGOutputSchema":
        """Return an empty, auditable failure without synthetic DRG data."""
        return cls(
            primary_diagnosis={},
            secondary_diagnoses=[],
            procedures=[],
            drg_impact=DRGImpact(),
            dip_impact=DIPImpact(),
            risks=[DRGRisk(
                rule_id="DRG_RUNTIME_FAILURE",
                severity="critical",
                risk_type="grouping",
                message="DRG analysis did not complete.",
                suggestion="Check the local grouper/rule set and require manual review.",
            )],
            recommendations=["人工复核 DRG/DIP 分组；不得使用本次结果结算。"],
            quality_flags={"runtime_failure": True},
            governance={},
            manual_review_required=True,
            review_conclusion="FAIL",
            confidence=0.0,
            notes="DRG analysis failed closed.",
            provider="drg-analyzer",
            model="icoder-drg-dip-risk-heuristics-1.0.0-development",
            is_mock=False,
            error=True,
            error_reason=reason,
        )


# ── DRG Adapter (similar to medical_coding.CodingEngineAdapter) ──


class DRGAnalysisAdapter:
    """Adapter for running DRG analysis on encoded codes.

    Unlike medical_coding (which uses LLM), this adapter is deterministic.
    Its result is a development risk-review candidate, never a billing result.
    """

    name = "drg_analysis_adapter"

    def __init__(self, llm_gateway=None, system_prompt: str = ""):
        self._gateway = llm_gateway
        self._system_prompt = system_prompt

    async def analyze_async(
        self,
        primary_diagnosis: dict,
        secondary_diagnoses: list[dict] | None = None,
        procedures: list[dict] | None = None,
        context: dict | None = None,
    ) -> DRGOutputSchema:
        """Run DRG analysis synchronously (no LLM call).

        Args:
            primary_diagnosis: {code, description, confidence}
            secondary_diagnoses: list of same
            procedures: list of {code, description, confidence}
            context: patient_gender, patient_age, etc.

        Returns:
            DRGOutputSchema with candidate matching + rule validation
        """
        from app.services.drg_grouper import group_drg
        from compliance_services.rule_engine import RuleEngine
        from compliance_services.drg_dip_rules import DRGDIPRuleSet

        secondary_diagnoses = secondary_diagnoses or []
        procedures = procedures or []
        context = context or {}

        # 1. Run grouper
        try:
            pd_code = primary_diagnosis.get("code", "") if isinstance(primary_diagnosis, dict) else ""
            sec_codes = [s.get("code", "") for s in secondary_diagnoses if isinstance(s, dict)]
            main_proc = procedures[0] if procedures else {}
            main_proc_code = main_proc.get("code", "") if isinstance(main_proc, dict) else ""

            grouper_result = group_drg(
                [pd_code] + sec_codes if pd_code else [],
                procedure_code=main_proc_code or None,
            )
        except Exception as exc:
            logger.error(
                "DRG grouper failed error_type=%s", type(exc).__name__,
            )
            from app.services.clinical_asset_governance import (
                ClinicalAssetGovernanceError,
            )
            reason = (
                "clinical_asset_governance_failed"
                if isinstance(exc, ClinicalAssetGovernanceError)
                else "grouper_failed"
            )
            return DRGOutputSchema.failure_result(reason)

        # 2. Run rule engine
        try:
            engine = RuleEngine()
            engine.register(DRGDIPRuleSet())
            structured = {
                "primary_diagnosis": primary_diagnosis,
                "secondary_diagnoses": secondary_diagnoses,
                "procedures": procedures,
            }
            rule_result = engine.validate("drg_dip", structured, context)
        except Exception as exc:
            logger.error(
                "DRG rule engine failed error_type=%s", type(exc).__name__,
            )
            return DRGOutputSchema.failure_result("rule_engine_failed")

        # 3. Build non-authoritative DIP placeholder.  No pseudo-payment math.
        dip_impact = _estimate_dip_impact(grouper_result, primary_diagnosis, procedures)

        # 4. Assemble
        return DRGOutputSchema.from_rule_validation(
            rule_result=rule_result,
            grouper_result=grouper_result,
            primary_diagnosis=primary_diagnosis,
            secondary_diagnoses=secondary_diagnoses,
            procedures=procedures,
            dip_impact=dip_impact,
        )

    def health_check(self) -> dict:
        from app.config import settings
        from app.services.clinical_asset_governance import get_drg_risk_governance

        try:
            governance = get_drg_risk_governance(
                deployment_mode=settings.ICODER_DEPLOYMENT_MODE,
            )
        except Exception:
            return {
                "engine": self.name,
                "status": "unavailable",
                "billing_authoritative": False,
            }
        return {
            "engine": self.name,
            "status": "development_only",
            "billing_authoritative": False,
            "governance": governance,
        }


def _estimate_dip_impact(grouper_result: dict, primary_diag: dict, procedures: list[dict]) -> DIPImpact:
    """Return a fail-closed placeholder until an authorized DIP pack exists."""
    del primary_diag, procedures
    coverage_note = "存在开发期候选匹配" if grouper_result.get("coverage") else "未匹配开发期候选"
    return DIPImpact(
        dip_score=0.0,
        dip_score_ceiling=0.0,
        payment_estimate_yuan=0.0,
        note=(
            f"{coverage_note}；未安装经授权的地区 DIP 目录，"
            "因此不计算分值或支付金额。"
        ),
        billing_authoritative=False,
    )
