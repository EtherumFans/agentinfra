# Disagreement Reasoning — taxonomy, correction model, DRG sensitivity
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DisagreementType(str, Enum):
    """Taxonomy of disagreement types between AI coding and gold/existing codes."""

    CODE_SPECIFICITY = "code_specificity"
    CODE_SELECTION = "code_selection"
    DIAGNOSIS_INTERPRET = "diagnosis_interpret"
    PRIMARY_VS_SECONDARY = "primary_vs_secondary"
    RULE_VIOLATION = "rule_violation"
    EVIDENCE_CONTRADICTION = "evidence_contradiction"
    DRG_SENSITIVE = "drg_sensitive"
    DOCUMENTATION_GAP = "documentation_gap"


class CorrectionRecord(BaseModel):
    """A single coding correction with structured metadata for learning."""

    case_id: str = Field(description="Encounter/case ID")
    code_ai: str = Field(description="What AI suggested")
    code_ai_name: str = Field(default="")
    code_correct: str = Field(description="What is correct (human-confirmed or gold)")
    code_correct_name: str = Field(default="")
    disagreement_type: DisagreementType = Field(description="Why they differ")
    type_rationale: str = Field(default="", description="Explanation of the type classification")
    drg_impacted: bool = Field(default=False)
    drg_before: str = Field(default="", description="DRG with AI code")
    drg_after: str = Field(default="", description="DRG with corrected code")
    rw_delta: float = Field(default=0.0, description="Relative weight change")
    rule_reference: list[str] = Field(default_factory=list, description="Rules that explain the correction")
    evidence_support: str = Field(default="", description="Evidence that supports the correction")
    reviewer: str = Field(default="system", description="Who made the correction")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    learnable: bool = Field(default=True, description="Can this pattern be reused for future cases?")


class DisagreementSummary(BaseModel):
    """Aggregate statistics across all disagreements in a review."""

    total_codes: int = 0
    agreements: int = 0
    disagreements: int = 0
    disagreement_rate: float = 0.0
    drg_impacted_count: int = 0
    drg_impact_rate: float = 0.0
    type_distribution: dict = Field(default_factory=dict, description="DisagreementType → count")
    learnable_corrections: int = 0


class DisagreementAnalysisResult(BaseModel):
    """Complete disagreement analysis output for a review."""

    corrections: list[CorrectionRecord] = Field(default_factory=list)
    summary: DisagreementSummary = Field(default_factory=DisagreementSummary)
