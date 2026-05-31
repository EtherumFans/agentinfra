# Evidence Ranking & Support Validation Schemas
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class EvidenceCategory(str, Enum):
    DIRECT = "direct"
    INFERRED = "inferred"
    WEAK = "weak"
    CONFLICTING = "conflicting"
    UNSUPPORTED = "unsupported"


class EvidenceRank(BaseModel):
    """A single evidence piece with strength score and category."""

    evidence_id: str = Field(default="", description="Unique ID for this evidence entry")
    text: str = Field(description="Evidence text snippet")
    source_document: str = Field(description="Document type the evidence came from")
    source_section: str = Field(default="", description="admission_reason / treatment / history / discharge")
    related_code: str = Field(default="", description="ICD or procedure code this evidence supports")
    strength_score: float = Field(default=0.5, ge=0.0, le=1.0)
    category: EvidenceCategory = Field(default=EvidenceCategory.WEAK)
    certainty: str = Field(default="confirmed")
    temporal_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    coding_relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    conflict_flag: bool = Field(default=False)
    unsupported_flag: bool = Field(default=False)
    rationale: str = Field(default="")


class ConflictType(str, Enum):
    DIAG_TREATMENT_MISMATCH = "diagnosis_treatment_mismatch"
    DISCHARGE_PROGRESS_CONTRADICTION = "discharge_progress_contradiction"
    PROCEDURE_RECORD_MISMATCH = "procedure_record_mismatch"
    PRIMARY_DIAG_ADMISSION_MISMATCH = "primary_diag_admission_mismatch"
    DIAG_OUTCOME_MISMATCH = "diagnosis_outcome_mismatch"


class ConflictResult(BaseModel):
    """A detected evidence conflict."""

    conflict_type: ConflictType
    conflict_summary: str = Field(description="Human-readable conflict description in Chinese")
    affected_codes: list[str] = Field(default_factory=list)
    review_required: bool = Field(default=True)


class UnsupportedCodeResult(BaseModel):
    """A code flagged as lacking adequate evidence support."""

    code: str
    name: str
    reason: str = Field(description="Why this code is unsupported")
    strength_best: float = Field(default=0.0, description="Best evidence strength found")
    unsupported_flag: bool = True
    review_required: bool = True


class EvidenceRankingResult(BaseModel):
    """Complete evidence ranking output."""

    top_supporting_evidence: list[EvidenceRank] = Field(default_factory=list)
    weak_evidence: list[EvidenceRank] = Field(default_factory=list)
    conflicting_evidence: list[EvidenceRank] = Field(default_factory=list)
    unsupported_codes: list[UnsupportedCodeResult] = Field(default_factory=list)
    conflicts: list[ConflictResult] = Field(default_factory=list)
    evidence_strength_avg: float = Field(default=0.0)
    unsupported_code_rate: float = Field(default=0.0)
    conflict_rate: float = Field(default=0.0)
