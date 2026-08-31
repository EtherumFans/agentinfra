# iCoDer - Review Schemas
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    encounter_id: str = Field(..., description="Encounter database ID or encounter_id string")


class CodeCandidateResponse(BaseModel):
    id: str
    finding: str
    code_system: str
    code: str
    name: str
    score: float
    chapter: Optional[str] = None
    evidence_ids: list = []
    status: str
    rule_checks: Optional[list] = None
    human_decision: Optional[str] = None
    human_reason: Optional[str] = None
    modified_code: Optional[str] = None
    modified_name: Optional[str] = None
    model_config = {"from_attributes": True}


class EvidenceResponse(BaseModel):
    id: str
    doc_type: str
    text: str
    entity_type: str
    supports_codes: list = []
    certainty: str
    negation: bool
    confidence: float
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    model_config = {"from_attributes": True}


class PrimaryDiagResult(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    confidence: float = 0.0
    evidence_ids: list = []
    judgment: str = "needs_review"
    reasoning: Optional[dict] = None


class MainProcedureResult(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    confidence: float = 0.0
    evidence_ids: list = []
    judgment: str = "needs_review"


class ReviewResponse(BaseModel):
    id: str
    review_id: str
    encounter_id: str
    agent_version: str
    model_used: str
    primary_diagnosis: Optional[dict] = None
    main_procedure: Optional[dict] = None
    secondary_diagnoses: Optional[list] = None
    other_procedures: Optional[list] = None
    diagnosis_analysis: Optional[list] = None
    procedure_analysis: Optional[list] = None
    documentation_gaps: Optional[list] = None
    uncodable_items: Optional[list] = None
    drg_impact: Optional[dict] = None
    human_checklist: Optional[list] = None
    validation_summary: Optional[dict] = None
    report_markdown: Optional[str] = None
    report_html: Optional[str] = None
    human_review_status: str
    reviewed_by: Optional[str] = None
    reviewer_notes: Optional[str] = None
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    cross_table_view: Optional[dict] = None
    evidence_ranking: Optional[dict] = None
    confidence_calibration: Optional[dict] = None
    pipeline_health: str = "healthy"
    candidates: List[CodeCandidateResponse] = []
    evidences: List[EvidenceResponse] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": False, "protected_namespaces": ()}


class HumanReviewInput(BaseModel):
    candidate_id: str = Field(...)
    decision: str = Field(..., description="confirmed / rejected / modified")
    reason: str = Field(..., min_length=1, description="修改或确认原因")
    modified_code: Optional[str] = None
    modified_name: Optional[str] = None


class ReviewCompleteInput(BaseModel):
    reviewer_notes: Optional[str] = None
    human_review_status: str = "completed"


class ReviewListResponse(BaseModel):
    items: List[ReviewResponse]
    total: int
    page: int
    page_size: int
