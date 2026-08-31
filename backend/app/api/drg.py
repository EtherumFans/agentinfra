"""Authenticated DRG/DIP development risk-review API.

All grouping-like values are non-authoritative candidates.  The bundled rule
pack cannot be used for payment or settlement and cloud use fails closed until
an independently verified regional/hospital rule pack is installed.

Endpoints:
  POST /api/drg/analyze           — full DRG analysis on encoded codes
  POST /api/drg/grouper/group     — pure grouper (no rule validation)
  GET  /api/drg/rules             — list 7 DRG/DIP rules
  GET  /api/drg/list              — list development candidate terminology
  GET  /api/drg/surgery/{code}    — look up surgery → DRG mapping
  POST /api/drg/check-gender      — gender consistency check (YA1 error group)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional

from app.middleware.auth import get_current_user

router = APIRouter(
    prefix="/api/drg",
    tags=["drg"],
    dependencies=[Depends(get_current_user)],
)


def _governance() -> dict:
    from app.config import settings
    from app.services.clinical_asset_governance import (
        ClinicalAssetGovernanceError,
        get_drg_risk_governance,
    )

    try:
        return get_drg_risk_governance(
            deployment_mode=settings.ICODER_DEPLOYMENT_MODE,
        )
    except ClinicalAssetGovernanceError as exc:
        raise HTTPException(
            status_code=503,
            detail="DRG/DIP clinical asset governance gate is not satisfied",
        ) from exc


# ── Request / Response Models ──


class DiagnosisCode(BaseModel):
    code: str
    name: str = ""
    description: str = ""
    confidence: float = 1.0


class ProcedureCode(BaseModel):
    code: str
    name: str = ""
    description: str = ""
    confidence: float = 1.0


class AnalyzeRequest(BaseModel):
    primary_diagnosis: DiagnosisCode
    secondary_diagnoses: list[DiagnosisCode] = Field(default_factory=list)
    procedures: list[ProcedureCode] = Field(default_factory=list)
    patient_gender: Literal["M", "F", ""] = ""
    patient_age: Optional[int] = Field(default=None, ge=0, le=150)


class GenderCheckRequest(BaseModel):
    diagnosis_code: str
    patient_gender: str                # "M" | "F"


class GovernanceResponse(BaseModel):
    asset_id: Literal["cn.drg_dip.risk_heuristics"]
    version: Literal["1.0.0-development"]
    asset_type: Literal["risk_review_rule_pack"]
    jurisdiction: Literal["CN_GENERIC_DEVELOPMENT"]
    authority_status: Literal["experimental_unverified"]
    license_status: Literal["external_review_required"]
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    billing_authoritative: Literal[False]
    manual_review_required: Literal[True]
    use_restriction: Literal[
        "development_risk_review_only_not_for_grouping_payment_or_settlement"
    ]


class DRGImpactResponse(BaseModel):
    predicted_drg: str
    drg_name: str
    mdc: str
    mdc_name: str
    adrg: str
    cc_level: str
    grouping_method: str
    coverage: bool
    payment_weight: Literal[0.0]
    payment_estimate_yuan: Literal[0.0]
    billing_authoritative: Literal[False]
    result_status: Literal["experimental_candidate"]


class DIPImpactResponse(BaseModel):
    dip_score: Literal[0.0]
    dip_score_ceiling: Literal[0.0]
    payment_estimate_yuan: Literal[0.0]
    note: str
    billing_authoritative: Literal[False]


class DRGRiskResponse(BaseModel):
    rule_id: str
    severity: str
    risk_type: str
    message: str
    suggestion: str


class AnalyzeResponse(BaseModel):
    primary_diagnosis: DiagnosisCode
    secondary_diagnoses: list[DiagnosisCode]
    procedures: list[ProcedureCode]
    drg_impact: DRGImpactResponse
    dip_impact: DIPImpactResponse
    risks: list[DRGRiskResponse]
    recommendations: list[str]
    quality_flags: dict[str, Any]
    governance: GovernanceResponse
    manual_review_required: Literal[True]
    review_conclusion: Literal["WARNING", "FAIL"]
    confidence: float
    notes: str
    provider: str
    model: str
    is_mock: bool
    error: Literal[False]
    error_reason: Literal[""]


class RuleItemResponse(BaseModel):
    id: str
    name: str
    severity: str
    category: str
    description: str


class RulesResponse(BaseModel):
    rule_set: Literal["drg_dip"]
    total: int
    rules: list[RuleItemResponse]
    governance: GovernanceResponse


# ── Endpoints ──


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_drg(body: AnalyzeRequest):
    """Run deterministic, non-authoritative DRG/DIP risk review.

    No LLM is called.  The result always requires human review and contains no
    official weight, score, payment or settlement calculation.
    """
    from app.services.drg_analyzer_service import DRGAnalysisAdapter

    adapter = DRGAnalysisAdapter()
    context = {
        "patient_gender": body.patient_gender,
        "patient_age": body.patient_age,
    }
    result = await adapter.analyze_async(
        primary_diagnosis=body.primary_diagnosis.model_dump(),
        secondary_diagnoses=[d.model_dump() for d in body.secondary_diagnoses],
        procedures=[p.model_dump() for p in body.procedures],
        context=context,
    )
    if result.error:
        raise HTTPException(
            status_code=503,
            detail="DRG/DIP risk review did not complete; no result is usable",
        )
    return result.to_dict()


@router.post("/grouper/group")
async def grouper_group(
    primary_diagnosis: str = Query(..., description="ICD-10 主诊断编码"),
    procedure_code: Optional[str] = Query(None, description="ICD-9-CM-3 主手术编码(可选)"),
    secondary_diagnoses: str = Query("", description="次要诊断编码,逗号分隔"),
):
    """Development candidate lookup (no official grouping or payment use)."""
    from app.services.drg_grouper import group_drg

    sec_list = [s.strip() for s in secondary_diagnoses.split(",") if s.strip()] if secondary_diagnoses else []
    diag_list = [primary_diagnosis] + sec_list if primary_diagnosis else sec_list

    try:
        return group_drg(diag_list, procedure_code=procedure_code)
    except Exception as exc:
        from app.services.clinical_asset_governance import (
            ClinicalAssetGovernanceError,
        )
        if isinstance(exc, ClinicalAssetGovernanceError):
            raise HTTPException(
                status_code=503,
                detail="DRG/DIP clinical asset governance gate is not satisfied",
            ) from exc
        raise


@router.get("/rules", response_model=RulesResponse)
async def list_drg_rules():
    """List the seven development-only DRG/DIP risk heuristics."""
    from compliance_services.drg_dip_rules import DRG_DIP_RULES

    rules = [
        {
            "id": rid,
            "name": info["name"],
            "severity": info["severity"],
            "category": info["category"],
            "description": info["description"],
        }
        for rid, info in DRG_DIP_RULES.items()
    ]
    return {
        "rule_set": "drg_dip",
        "total": len(rules),
        "rules": rules,
        "governance": _governance(),
    }


@router.get("/list")
async def list_drg_groups(
    type: str = Query("all", pattern="^(all|adrg|drg)$"),
):
    """List bundled candidate terminology; entries are not authoritative."""
    from app.services.drg_grouper import get_adrg_list, get_drg_list

    result: dict = {}
    if type in ("all", "adrg"):
        result["adrgs"] = get_adrg_list()
    if type in ("all", "drg"):
        result["drgs"] = get_drg_list()
    result["governance"] = _governance()
    return result


@router.get("/surgery/{code}")
async def surgery_lookup(code: str):
    """Look up a development-only surgery → candidate mapping."""
    from app.services.drg_grouper import get_surgery_drg

    match = get_surgery_drg(code)
    if not match:
        raise HTTPException(status_code=404, detail=f"Surgery code {code} not found in DRG KB")
    return {**match, "governance": _governance()}


@router.post("/check-gender")
async def check_gender(body: GenderCheckRequest):
    """Run a non-authoritative diagnosis/gender consistency heuristic.

    Returns:
      consistent: True / False
      message: 违规说明(中文)
    """
    from app.services.drg_grouper import check_gender_consistency

    return {
        **check_gender_consistency(body.diagnosis_code, body.patient_gender),
        "governance": _governance(),
    }


@router.get("/governance", response_model=GovernanceResponse)
async def drg_governance():
    """Return the active rule-pack authority, licence and use restrictions."""
    return _governance()
