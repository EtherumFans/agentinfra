# Principal Diagnosis Reasoning — structured explainability for primary diagnosis selection
from typing import Optional
from pydantic import BaseModel, Field


class WhyNotSelected(BaseModel):
    """Reason a candidate was NOT selected as principal diagnosis."""

    code: str = Field(description="ICD-10 code of the rejected candidate")
    name: str = Field(description="Diagnosis name")
    reason: str = Field(description="Explanation in Chinese why this candidate was not selected")
    rule_reference: Optional[str] = Field(default=None, description="Coding rule ID if applicable, e.g. R013")


class DisagreementAnalysis(BaseModel):
    """Analysis when AI principal diagnosis differs from existing codes."""

    has_disagreement: bool = Field(default=False)
    existing_code: Optional[str] = Field(default=None)
    existing_name: Optional[str] = Field(default=None)
    ai_code: Optional[str] = Field(default=None)
    ai_name: Optional[str] = Field(default=None)
    analysis: str = Field(default="", description="Root cause analysis of the disagreement")
    recommendation: str = Field(default="", description="Suggested resolution: accept_ai / accept_existing / needs_senior_review")
    rule_basis: list[str] = Field(default_factory=list, description="Rules supporting the AI recommendation")


class ConfidenceEscalation(BaseModel):
    """Escalation trigger when confidence is borderline."""

    escalated: bool = Field(default=False)
    reason: str = Field(default="", description="Why this case needs escalation")
    trigger: str = Field(default="", description="What triggered escalation: score_gap, evidence_conflict, rule_ambiguity")
    candidates_in_contention: list[str] = Field(default_factory=list, description="Codes that are close contenders")


class PrincipalDiagnosisReasoning(BaseModel):
    """Complete reasoning for principal diagnosis selection."""

    why_selected: str = Field(
        default="",
        description="为什么选择此编码作为主要诊断 (2-4句中文，引用编码规则和时间线证据)"
    )
    why_not_selected: list[WhyNotSelected] = Field(
        default_factory=list,
        description="对排名靠前但未选中的候选，逐一解释排除原因"
    )
    rule_basis: list[str] = Field(
        default_factory=list,
        description="引用的编码规则 ID，如 R001, R013"
    )
    timeline_evidence: str = Field(
        default="",
        description="从时间线中提取的证据：入院目的、手术日期、资源消耗时段等"
    )
    confidence_level: str = Field(
        default="medium",
        description="high: 明确无误; medium: 合理但需复核; low: 需升级人工审核"
    )
    confidence_rationale: str = Field(
        default="",
        description="置信度判断依据"
    )
    disagreement_analysis: DisagreementAnalysis = Field(
        default_factory=DisagreementAnalysis,
        description="与现有编码的分歧分析"
    )
    confidence_escalation: ConfidenceEscalation = Field(
        default_factory=ConfidenceEscalation,
        description="低置信度时的升级建议"
    )
