"""Compliance API — rule engine validation for various compliance domains.

Endpoints:
  GET  /api/compliance/rule-engine/status
  POST /api/compliance/rule-engine/validate
  GET  /api/compliance/rule-engine/rules
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


class ValidateRequest(BaseModel):
    rule_set: str = "medical_coding"
    structured_output: dict
    context: dict = {}


@router.get("/rule-engine/status")
async def rule_engine_status():
    """Get RuleEngine health and loaded rule sets."""
    from compliance_services.rule_engine import RuleEngine
    from compliance_services.medical_coding_rules import MedicalCodingRuleSet
    from compliance_services.drg_dip_rules import DRGDIPRuleSet
    from compliance_services.insurance_rules import InsuranceAuditRuleSet, ChargeComplianceRuleSet, DocumentEvidenceRuleSet

    engine = RuleEngine()
    engine.register(MedicalCodingRuleSet())
    engine.register(DRGDIPRuleSet())
    engine.register(InsuranceAuditRuleSet())
    engine.register(ChargeComplianceRuleSet())
    engine.register(DocumentEvidenceRuleSet())
    return engine.health_check()


@router.post("/rule-engine/validate")
async def rule_engine_validate(body: ValidateRequest):
    """Validate structured output against a named rule_set."""
    SUPPORTED = ("medical_coding", "drg_dip", "insurance_audit", "charge_compliance", "document_evidence")
    if body.rule_set not in SUPPORTED:
        raise HTTPException(status_code=400,
            detail=f"Unsupported rule_set: {body.rule_set}. Supported: {', '.join(SUPPORTED)}")

    from compliance_services.rule_engine import RuleEngine
    from compliance_services.medical_coding_rules import MedicalCodingRuleSet
    from compliance_services.drg_dip_rules import DRGDIPRuleSet
    from compliance_services.insurance_rules import InsuranceAuditRuleSet, ChargeComplianceRuleSet, DocumentEvidenceRuleSet

    engine = RuleEngine()
    engine.register(MedicalCodingRuleSet())
    engine.register(DRGDIPRuleSet())
    engine.register(InsuranceAuditRuleSet())
    engine.register(ChargeComplianceRuleSet())
    engine.register(DocumentEvidenceRuleSet())

    result = engine.validate(body.rule_set, body.structured_output, body.context)
    return result.to_dict()


@router.get("/rule-engine/rules")
async def rule_engine_rules(rule_set: str = "medical_coding"):
    """List rules for a rule_set."""
    if rule_set != "medical_coding":
        raise HTTPException(status_code=400, detail=f"Unsupported rule_set: {rule_set}")

    from compliance_services.medical_coding_rules import MEDICAL_CODING_RULES
    rules = [{"id": rid, "name": r["name"], "severity": r["severity"], "category": r["category"]}
             for rid, r in MEDICAL_CODING_RULES.items()]
    return {"rule_set": rule_set, "rules": rules, "total": len(rules)}
