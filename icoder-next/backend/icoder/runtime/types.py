"""Runtime data contracts (pydantic v2) — shared across runner / experts / API / report.

Evidence uses Corti-compatible char-span semantics: start inclusive, end exclusive,
so the literal span is always ``text[start:end]`` (never text-search to locate).
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["Critical", "Moderate", "Informational"]
CodeStatus = Literal["code", "candidate"]
CodeType = Literal["diagnosis", "procedure"]
NoteKind = Literal["includes", "excludes1", "excludes2", "code_first", "use_additional"]


class Evidence(BaseModel):
    context_index: int = 0
    start: int  # inclusive
    end: int  # exclusive
    text: str


class CodeNote(BaseModel):
    """Instructional note surfaced by the Verify tool (Includes / Excludes / Code First / Use Additional)."""
    kind: NoteKind
    text: str


class Alternative(BaseModel):
    """A code the engine considered but did not assign (≈ 鉴别诊断), from differentiation hints."""
    code: str
    display: str = ""
    reason: str = ""


class CodeResult(BaseModel):
    system: str
    code: str
    display: str
    code_type: CodeType = "diagnosis"
    status: CodeStatus = "code"
    confidence: float = 0.0
    is_primary: bool = False
    high_risk: bool = False
    evidences: list[Evidence] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
    notes: list[CodeNote] = Field(default_factory=list)


class RuleHit(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    code: Optional[str] = None


class ComplianceGate(BaseModel):
    rule_set: str
    passed: bool
    human_review_required: bool
    hits: list[RuleHit] = Field(default_factory=list)


class StageObservation(BaseModel):
    stage: str
    tool: str
    tool_run_id: str
    duration_ms: float
    summary: str = ""


class DrgRoute(BaseModel):
    adrg: Optional[str] = None
    drg: Optional[str] = None
    group_name: Optional[str] = None
    # DRG/DIP grouping detail (filled by GroupingExpert)
    mdc: Optional[str] = None
    mdc_name: Optional[str] = None
    surgical: bool = False
    cc_mcc: Optional[str] = None  # None | "CC" | "MCC"
    dip_code: Optional[str] = None
    dip_name: Optional[str] = None
    dip_score: Optional[float] = None
    rationale: list[str] = Field(default_factory=list)
    note: str = ""


class Versions(BaseModel):
    # model_version is a domain field, not a pydantic-managed namespace
    model_config = ConfigDict(protected_namespaces=())

    runtime_version: str
    agent_version: str
    ruleset_version: str
    catalog_version: str
    model_version: str


class RunResult(BaseModel):
    run_id: str
    agent_id: str
    agent_version: str
    coding_system: str
    created_at: float
    # de-identified input the report/embed renders (never raw PHI)
    redaction: dict
    codes: list[CodeResult] = Field(default_factory=list)
    candidates: list[CodeResult] = Field(default_factory=list)
    compliance: ComplianceGate
    drg_route: Optional[DrgRoute] = None
    stages: list[StageObservation] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)
    versions: Versions
    production_writeback_blocked: bool = True
    human_review: Optional[dict] = None


def new_id(prefix: str = "run") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
