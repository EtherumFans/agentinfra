"""DRG/DIP Analyzer API.

Endpoints:
  POST /api/drg/analyze           — full DRG analysis on encoded codes
  POST /api/drg/grouper/group     — pure grouper (no rule validation)
  GET  /api/drg/rules             — list 7 DRG/DIP rules
  GET  /api/drg/list              — list all ADRG/DRG groups (CHS-DRG 1.1)
  GET  /api/drg/surgery/{code}    — look up surgery → DRG mapping
  POST /api/drg/check-gender      — gender consistency check (YA1 error group)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/api/drg", tags=["drg"])


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
    patient_gender: str = ""           # "M" | "F" | "" (unknown)
    patient_age: Optional[int] = None


class GenderCheckRequest(BaseModel):
    diagnosis_code: str
    patient_gender: str                # "M" | "F"


# ── Endpoints ──


@router.post("/analyze")
async def analyze_drg(body: AnalyzeRequest):
    """Run full DRG analysis: grouper + rule validation + DIP estimation.

    Deterministic pipeline — no LLM calls. Suitable for production audit
    workflows where reproducibility is required.
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
    return result.to_dict()


@router.post("/grouper/group")
async def grouper_group(
    primary_diagnosis: str = Query(..., description="ICD-10 主诊断编码"),
    procedure_code: Optional[str] = Query(None, description="ICD-9-CM-3 主手术编码(可选)"),
    secondary_diagnoses: str = Query("", description="次要诊断编码,逗号分隔"),
):
    """Pure grouper lookup (no rule validation)."""
    from app.services.drg_grouper import group_drg

    sec_list = [s.strip() for s in secondary_diagnoses.split(",") if s.strip()] if secondary_diagnoses else []
    diag_list = [primary_diagnosis] + sec_list if primary_diagnosis else sec_list

    result = group_drg(diag_list, procedure_code=procedure_code)
    return result


@router.get("/rules")
async def list_drg_rules():
    """List the 7 DRG/DIP compliance rules (DRG001-DRG004, DIP001-DIP003)."""
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
    }


@router.get("/list")
async def list_drg_groups(
    type: str = Query("all", pattern="^(all|adrg|drg)$"),
):
    """List all ADRG/DRG groups in bundled CHS-DRG 1.1 KB."""
    from app.services.drg_grouper import get_adrg_list, get_drg_list

    result: dict = {}
    if type in ("all", "adrg"):
        result["adrgs"] = get_adrg_list()
    if type in ("all", "drg"):
        result["drgs"] = get_drg_list()
    return result


@router.get("/surgery/{code}")
async def surgery_lookup(code: str):
    """Look up surgery ICD-9-CM-3 code → DRG mapping."""
    from app.services.drg_grouper import get_surgery_drg

    match = get_surgery_drg(code)
    if not match:
        raise HTTPException(status_code=404, detail=f"Surgery code {code} not found in DRG KB")
    return match


@router.post("/check-gender")
async def check_gender(body: GenderCheckRequest):
    """Check CHS-DRG 1.1 YA1 error group — primary diagnosis gender consistency.

    Returns:
      consistent: True / False
      message: 违规说明(中文)
    """
    from app.services.drg_grouper import check_gender_consistency

    return check_gender_consistency(body.diagnosis_code, body.patient_gender)
