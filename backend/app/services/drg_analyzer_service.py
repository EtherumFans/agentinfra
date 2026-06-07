"""DRGOutputSchema — standard output format for DRG analyzer agent.

v1.0: Wraps CHS-DRG 1.1 grouping result + DRG/DIP rule validation.

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
    """DRG 分组对医保支付的影响分析."""
    predicted_drg: str = ""           # FR3 / EC13 / IA15 ...
    drg_name: str = ""
    mdc: str = ""                     # MDCF / MDCE ...
    mdc_name: str = ""
    adrg: str = ""                    # ADRG code (FR / EC / IA ...)
    cc_level: str = ""                # 不伴合并症 / CC / MCC
    grouping_method: str = ""         # surgical / medical
    coverage: bool = False            # grouper 是否找到分组
    payment_weight: float = 1.0       # 估算的 DRG 权重
    payment_estimate_yuan: float = 0.0  # 估算的医保支付(元)

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
        }


@dataclass
class DIPImpact:
    """DIP 分值与支付估算."""
    dip_score: float = 0.0
    dip_score_ceiling: float = 0.0    # DIP 分值上限
    payment_estimate_yuan: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "dip_score": self.dip_score,
            "dip_score_ceiling": self.dip_score_ceiling,
            "payment_estimate_yuan": self.payment_estimate_yuan,
            "note": self.note,
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
    manual_review_required: bool = False

    # 总结
    review_conclusion: str = "PASS"   # PASS | WARNING | FAIL
    confidence: float = 0.0
    notes: str = ""

    # 元数据
    provider: str = ""          # 哪个 provider 产出
    model: str = ""
    is_mock: bool = False

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
            "manual_review_required": self.manual_review_required,
            "review_conclusion": self.review_conclusion,
            "confidence": self.confidence,
            "notes": self.notes,
            "provider": self.provider,
            "model": self.model,
            "is_mock": self.is_mock,
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
            payment_weight=_estimate_drg_weight(grouper_result),
            payment_estimate_yuan=_estimate_payment(grouper_result),
        )

        # Determine review conclusion
        critical_count = sum(1 for r in risks if r.severity == "critical")
        high_count = sum(1 for r in risks if r.severity == "high")

        if critical_count > 0:
            review_conclusion = "FAIL"
        elif high_count > 0 or rule_result.manual_review_required:
            review_conclusion = "WARNING"
        else:
            review_conclusion = "PASS"

        # Confidence based on coverage
        confidence = 0.95 if grouper_result.get("coverage") else 0.50

        return cls(
            primary_diagnosis=primary_diagnosis,
            secondary_diagnoses=secondary_diagnoses,
            procedures=procedures,
            drg_impact=drg_impact,
            dip_impact=dip_impact or DIPImpact(),
            risks=risks,
            recommendations=recommendations,
            quality_flags=rule_result.quality_flags or {},
            manual_review_required=rule_result.manual_review_required,
            review_conclusion=review_conclusion,
            confidence=confidence,
            notes=f"CHS-DRG 1.1 grouping. grouper_method={grouper_result.get('grouping_method', 'N/A')}",
            provider="drg-analyzer",
            model="medical-coding/mock",
            is_mock=False,
        )

    @classmethod
    def mock_result(cls) -> "DRGOutputSchema":
        """Default mock for testing."""
        return cls(
            primary_diagnosis={"code": "I21.0", "description": "急性前壁心肌梗死", "confidence": 0.95},
            secondary_diagnoses=[
                {"code": "I10", "description": "原发性高血压", "confidence": 0.88},
            ],
            procedures=[{"code": "00.66", "description": "经皮冠状动脉支架植入术", "confidence": 0.92}],
            drg_impact=DRGImpact(
                predicted_drg="EC13",
                drg_name="经皮冠状动脉支架植入伴 CC",
                mdc="MDCE",
                mdc_name="循环系统疾病及功能障碍",
                adrg="EC1",
                cc_level="伴一般合并症/并发症 (CC)",
                grouping_method="surgical",
                coverage=True,
                payment_weight=2.5,
                payment_estimate_yuan=25000.0,
            ),
            dip_impact=DIPImpact(
                dip_score=120.5,
                dip_score_ceiling=200.0,
                payment_estimate_yuan=24100.0,
                note="DIP 估算:基于 I21.0+00.66 组合",
            ),
            risks=[],
            recommendations=[],
            quality_flags={"grouper_coverage": True, "grouper_method": "surgical"},
            manual_review_required=False,
            review_conclusion="PASS",
            confidence=0.95,
            notes="Mock DRG analyzer result.",
            provider="drg-analyzer",
            model="medical-coding/mock",
            is_mock=True,
        )


# ── DRG Adapter (similar to medical_coding.CodingEngineAdapter) ──


class DRGAnalysisAdapter:
    """Adapter for running DRG analysis on encoded codes.

    Unlike medical_coding (which uses LLM), this adapter is deterministic:
    pure rule-based + grouper lookup. Future versions may add LLM-based
    explanation layer.
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
            DRGOutputSchema with grouping + rule validation
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
        except Exception as e:
            logger.exception("DRG grouper failed: %s", e)
            grouper_result = {
                "mdc": "", "mdg_name": "", "adrg": "", "drg": "",
                "drg_name": "", "cc_level": "", "grouping_method": "",
                "coverage": False, "error": str(e),
            }

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
        except Exception as e:
            logger.exception("DRG rule engine failed: %s", e)
            # Fallback: empty result
            rule_result = type("Stub", (), {
                "issues": [],
                "rules_fired": [],
                "manual_review_required": False,
                "quality_flags": {},
            })()

        # 3. Build DIP impact (simplified: estimate from grouper)
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
        return {"engine": self.name, "status": "ready"}


# ── Helpers ──


# CHS-DRG 1.1 简化版权重表 (实际医院需从医保局获取精确权重)
# 这里给出常见 MDC 的近似权重,基于 2023 年公开数据
_DRG_WEIGHT_TABLE = {
    "MDCA": 1.20,  # 神经系统
    "MDCB": 0.85,  # 眼科
    "MDCC": 0.80,  # 耳鼻喉
    "MDCD": 1.15,  # 呼吸系统
    "MDCE": 1.80,  # 循环系统
    "MDCF": 1.05,  # 消化系统
    "MDCG": 1.30,  # 肝胆胰
    "MDCH": 0.90,  # 骨骼肌肉
    "MDCI": 1.40,  # 皮肤/乳腺
    "MDCJ": 0.75,  # 内分泌
    "MDCK": 1.10,  # 肾脏
    "MDCL": 1.00,  # 泌尿
    "MDCM": 0.95,  # 男性生殖
    "MDCN": 0.90,  # 女性生殖
    "MDCO": 0.85,  # 妊娠
    "MDCP": 1.50,  # 新生儿
    "MDCQ": 1.25,  # 血液
    "MDCR": 0.95,  # 创伤中毒
    "MDCS": 1.60,  # 感染
    "MDCT": 0.80,  # 精神
    "MDCU": 0.50,  # 其他
    "MDCV": 1.70,  # 烧伤
    "MDCW": 1.30,  # 多系统
    "MDCX": 0.00,  # 错误组
}

# 平均每权重医保支付 (元) — 2024 年公开数据近似值
_AVG_PAYMENT_PER_WEIGHT = 10000.0


def _estimate_drg_weight(grouper_result: dict) -> float:
    """Estimate DRG weight from MDC + CC level."""
    mdc = grouper_result.get("mdc", "")
    cc_level = grouper_result.get("cc_level", "")
    base = _DRG_WEIGHT_TABLE.get(mdc, 1.0)
    if "MCC" in cc_level:
        return round(base * 1.5, 2)
    elif "CC" in cc_level:
        return round(base * 1.2, 2)
    return round(base, 2)


def _estimate_payment(grouper_result: dict) -> float:
    """Estimate medical insurance payment in yuan."""
    weight = _estimate_drg_weight(grouper_result)
    return round(weight * _AVG_PAYMENT_PER_WEIGHT, 2)


def _estimate_dip_impact(grouper_result: dict, primary_diag: dict, procedures: list[dict]) -> DIPImpact:
    """Estimate DIP score and payment (simplified).

    Real DIP scoring requires national DIP score table (CHS-DIP 2.0).
    This is an MVP estimation based on DRG + primary diagnosis category.
    """
    if not grouper_result.get("coverage"):
        return DIPImpact(dip_score=0.0, note="DRG 未匹配,DIP 无法计算")

    base_score = 100.0
    drg_weight = _estimate_drg_weight(grouper_result)
    estimated_score = round(base_score * drg_weight, 1)

    return DIPImpact(
        dip_score=estimated_score,
        dip_score_ceiling=round(estimated_score * 1.5, 1),
        payment_estimate_yuan=round(estimated_score * 200, 2),  # DIP 分单价约 200 元
        note=f"DIP 估算: DRG 权重 {drg_weight} → DIP 分值 {estimated_score}。实际需对照医保局 DIP 目录。",
    )
