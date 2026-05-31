"""Type definitions for iCoDer Python SDK."""

from __future__ import annotations
from typing import Optional, Any
from dataclasses import dataclass, field


@dataclass
class User:
    id: str
    username: str
    email: str
    full_name: str = ""
    role: str = "coder"
    department: str = ""
    is_active: bool = True


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Optional[User] = None


@dataclass
class FactDiagnosis:
    diagnosis: str
    icd10cm_code: Optional[str] = None
    status: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class FactProcedure:
    procedure: str
    icd9cm3_code: Optional[str] = None
    status: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class FactExtractionResult:
    chief_complaint: Optional[str] = None
    diagnosis_facts: list[FactDiagnosis] = field(default_factory=list)
    procedure_facts: list[FactProcedure] = field(default_factory=list)
    negated_findings: list[dict] = field(default_factory=list)
    timing_facts: dict = field(default_factory=dict)
    documentation_overview: dict = field(default_factory=dict)


@dataclass
class FactExtractResponse:
    facts: FactExtractionResult
    raw_output: str = ""
    credits_consumed: float = 0


@dataclass
class Review:
    id: Optional[str] = None
    encounter_id: Optional[str] = None
    status: Optional[str] = None
    primary_diagnosis: Optional[dict] = None
    main_procedure: Optional[dict] = None
    candidates: list[dict] = field(default_factory=list)
    evidences: list[dict] = field(default_factory=list)
    processing_time_ms: Optional[int] = None


@dataclass
class Expert:
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_published: bool = False


@dataclass
class AgentTemplate:
    id: str
    name: str
    description: str = ""
    category: str = "general"
    system_prompt: Optional[str] = None
    expert_ids: list[str] = field(default_factory=list)


@dataclass
class UsageSummary:
    total_requests: int = 0
    credits_used: float = 0
    avg_response_time_ms: float = 0
    tokens_used: Optional[int] = None


@dataclass
class iCoDerConfig:
    base_url: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    timeout: int = 120
