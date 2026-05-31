# iCoDer — Gold Case Schemas (Phase 10 extended)
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class GoldCaseCreate(BaseModel):
    # Case metadata
    department: str
    diagnosis_group: str
    difficulty: str = "medium"  # easy | medium | hard
    specialty: Optional[str] = None  # e.g. 肿瘤内科
    risk_tags: Optional[list[str]] = None  # e.g. ["drg_sensitive", "mcc_cc", "rare_disease"]
    source: str = "manual"

    # Original codes (before review)
    original_primary_diagnosis: str = ""
    original_primary_diag_name: str = ""
    original_main_procedure: Optional[str] = None
    original_main_proc_name: Optional[str] = None

    # Expected gold standard codes
    expected_principal_diagnosis: str
    expected_principal_diag_name: str = ""
    expected_principal_procedure: Optional[str] = None
    expected_principal_proc_name: Optional[str] = None
    expected_secondary_diagnoses: Optional[list[str]] = None
    expected_procedure_codes: Optional[list[str]] = None
    expected_drg_group: Optional[str] = None

    # Acceptable alternatives (soft match)
    acceptable_alternatives: Optional[list[str]] = None  # valid alternative codes

    # Reasoning expectations
    reasoning_expectations: Optional[list[str]] = None  # e.g. ["should cite R013"]

    # Evidence annotations
    evidence_spans: Optional[list] = None

    # Known issues (for precision/recall evaluation)
    missing_codes: Optional[list] = None
    unsupported_codes: Optional[list] = None
    documentation_gaps: Optional[list] = None

    # Full encounter data for pipeline execution
    full_case_data: Optional[dict] = None

    # Reviewer info
    reviewer: Optional[str] = None


class GoldCaseResponse(BaseModel):
    id: str
    case_id: str
    department: str
    diagnosis_group: str
    difficulty: str
    specialty: Optional[str] = None
    risk_tags: Optional[list] = None
    source: str

    # Original
    original_primary_diagnosis: str = ""
    original_primary_diag_name: str = ""
    original_main_procedure: Optional[str] = None
    original_main_proc_name: Optional[str] = None

    # Expected
    expected_principal_diagnosis: str
    expected_principal_diag_name: str = ""
    expected_principal_procedure: Optional[str] = None
    expected_principal_proc_name: Optional[str] = None
    expected_secondary_diagnoses: Optional[list] = None
    expected_procedure_codes: Optional[list] = None
    expected_drg_group: Optional[str] = None
    acceptable_alternatives: Optional[list] = None
    reasoning_expectations: Optional[list] = None

    # Evidence
    evidence_spans: Optional[list] = None

    # Issues
    missing_codes: Optional[list] = None
    unsupported_codes: Optional[list] = None
    documentation_gaps: Optional[list] = None

    # Evaluation
    reviewer: Optional[str] = None
    agent_accuracy: Optional[float] = None
    last_evaluated_at: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class EvaluationResult(BaseModel):
    case_id: str
    agent_primary_diag: Optional[str] = None
    agent_main_proc: Optional[str] = None
    primary_diag_match: bool = False
    primary_diag_soft_match: bool = False  # matches acceptable_alternatives
    main_proc_match: bool = False
    secondary_diag_recall: float = 0.0  # % expected secondaries found
    procedure_recall: float = 0.0
    drg_match: bool = False
    reasoning_expectations_met: list[str] = []
    reasoning_score: float = 0.0  # completeness of CaseReasoningReport
    missing_codes_found: list = []
    unsupported_codes_identified: list = []
    documentation_gaps_found: list = []
    hallucinated_codes: list = []
    evidence_completeness: float = 0.0
    overall_score: float = 0.0


class EvaluationSummary(BaseModel):
    total_cases: int
    primary_diag_accuracy: float
    primary_diag_soft_accuracy: float  # includes acceptable alternatives
    main_proc_accuracy: float
    secondary_diag_recall_avg: float
    procedure_recall_avg: float
    drg_match_rate: float
    reasoning_score_avg: float
    missing_code_recall: float
    unsupported_code_precision: float
    documentation_gap_recall: float
    evidence_completeness_avg: float
    hallucination_rate: float
    avg_overall_score: float
    per_case_results: list = []
