# iCoDer - Code & Rule Schemas
from typing import Optional, List
from pydantic import BaseModel, Field


class CodeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="搜索词，如疾病名称或手术名称")
    code_system: str = Field(default="ICD10_CN", description="ICD10_CN / ICD9_CM3 / INSURANCE_DIAG / INSURANCE_PROC / LOCAL")
    top_k: int = Field(default=10, ge=1, le=50)


class CodeSearchResult(BaseModel):
    code: str
    name: str
    score: float
    chapter: Optional[str] = None
    parent_code: Optional[str] = None
    valid: bool = True


class CodeSearchResponse(BaseModel):
    results: List[CodeSearchResult]
    query: str
    code_system: str
    total_found: int


class CodeExploreRequest(BaseModel):
    code: str = Field(..., min_length=1)
    code_system: str = Field(default="ICD10_CN")


class CodeTreeNode(BaseModel):
    code: str
    name: str
    level: int
    children: list = []
    includes: Optional[list] = None
    excludes: Optional[list] = None
    notes: Optional[str] = None


class CodeExploreResponse(BaseModel):
    code: str
    name: str
    code_system: str
    chapter: Optional[str] = None
    block: Optional[str] = None
    parent: Optional[str] = None
    children: list = []
    includes: Optional[list] = None
    excludes: Optional[list] = None
    notes: Optional[str] = None
    valid: bool = True


class RuleRetrieveRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    rule_sets: List[str] = Field(default=["住院病案首页数据填写质量规范", "ICD10编码规则"])


class RuleResult(BaseModel):
    rule_id: str
    rule_set: str
    title: str
    content: str
    relevance: float
    category: Optional[str] = None  # main_diag, main_proc, chapter, sequencing
    examples: Optional[str] = None


class RuleRetrieveResponse(BaseModel):
    topic: str
    results: List[RuleResult]
    total_found: int


class CodeVerifyRequest(BaseModel):
    encounter_id: str
    diagnosis_codes: List[str] = []
    procedure_codes: List[str] = []
    evidence_pack_id: Optional[str] = None


class CodeVerifyResult(BaseModel):
    code: str
    name: str
    status: str  # pass, warn, fail
    messages: List[str] = []
    evidence_support: bool = False
    rule_compliance: bool = False


class CodeVerifyResponse(BaseModel):
    encounter_id: str
    results: List[CodeVerifyResult]
    overall_status: str  # pass, needs_review, fail
    summary: str
