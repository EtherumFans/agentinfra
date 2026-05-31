# Case Reasoning Report — unified clinical cognition chain report
from datetime import datetime, UTC
from typing import Optional
from pydantic import BaseModel, Field


class CaseOverview(BaseModel):
    encounter_id: str = ""
    department: str = ""
    admission_reason: str = ""
    doc_count: int = 0
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TimelineSection(BaseModel):
    summary: str = ""
    anchor_count: int = 0
    event_count: int = 0
    unresolved_count: int = 0
    key_events: list[str] = Field(default_factory=list)


class EvidenceSection(BaseModel):
    top_count: int = 0
    weak_count: int = 0
    conflicting_count: int = 0
    unsupported_code_count: int = 0
    strength_avg: float = 0.0
    unsupported_codes: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class PrincipalDiagnosisSection(BaseModel):
    code: str = ""
    name: str = ""
    why_selected: str = ""
    why_not_selected: list[str] = Field(default_factory=list)
    rule_basis: list[str] = Field(default_factory=list)
    confidence_level: str = "medium"
    timeline_evidence: str = ""


class DisagreementSection(BaseModel):
    has_disagreement: bool = False
    correction_count: int = 0
    drg_impacted_count: int = 0
    type_distribution: dict = Field(default_factory=dict)
    top_corrections: list[str] = Field(default_factory=list)


class ConfidenceSection(BaseModel):
    auto_count: int = 0
    review_count: int = 0
    escalate_count: int = 0
    auto_accept_rate: float = 0.0
    override_count: int = 0


class AuditSection(BaseModel):
    total_events: int = 0
    state_path: list[str] = Field(default_factory=list)
    gate_outcomes: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CaseReasoningReport(BaseModel):
    """Unified clinical cognition report — aggregates all cognitive chain outputs."""

    case_overview: CaseOverview = Field(default_factory=CaseOverview)
    clinical_timeline: TimelineSection = Field(default_factory=TimelineSection)
    evidence_assessment: EvidenceSection = Field(default_factory=EvidenceSection)
    principal_diagnosis: PrincipalDiagnosisSection = Field(default_factory=PrincipalDiagnosisSection)
    disagreement_analysis: DisagreementSection = Field(default_factory=DisagreementSection)
    confidence_routing: ConfidenceSection = Field(default_factory=ConfidenceSection)
    audit_summary: AuditSection = Field(default_factory=AuditSection)
    clinical_narrative: str = Field(
        default="",
        description="完整临床叙事：就诊经过→诊断演化→治疗过程→主诊断选择，像高级编码员审核笔记"
    )
    evidence_story: str = Field(
        default="",
        description="证据故事：按来源重要性排列，说明当前编码建议基于哪些关键证据，标记弱证据和冲突"
    )
    final_recommendation: str = Field(
        default="",
        description="最终审核建议：建议确认/复核/升级，DRG风险标记，证据不足警告"
    )
    human_readable_summary: str = Field(
        default="",
        description="Natural language summary in Chinese, 3-5 paragraphs telling the complete clinical reasoning story"
    )
