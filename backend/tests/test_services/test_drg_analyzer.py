"""Tests for DRG/DIP Analyzer — grouper + rule validation + adapter + API.

Coverage:
  - grouper: surgical case (PCI), medical case (AMI no procedure), unknown procedure
  - rules: DRG001 missing primary, DRG004 gender error, DIP001 specificity
  - adapter: end-to-end analysis pipeline
  - API: /api/drg/analyze, /api/drg/rules, /api/drg/list, /api/drg/check-gender
"""
import pytest
import pytest_asyncio


# ── Grouper tests ──


def test_grouper_surgical_pci_for_ami():
    """PCI 00.66 (经皮冠状动脉支架植入) → MDCE / EC1 / EC13 with CC."""
    from app.services.drg_grouper import group_drg

    result = group_drg(
        diagnosis_codes=["I21.0", "I10"],   # AMI + 高血压
        procedure_code="00.66",
    )
    assert result["coverage"] is True
    assert result["grouping_method"] == "surgical"
    assert result["mdc"] == "MDCE"
    assert "EC1" in result["adrg"]
    # With CC (I10 is CC indicator), should be EC13 (with CC), not EC15 (without)
    assert "EC13" == result["drg"] or "EC11" == result["drg"]
    assert "经皮冠状动脉" in result["drg_name"] or "冠状动脉" in result["drg_name"]


def test_grouper_medical_ami_no_procedure():
    """Medical case: AMI without procedure → MDCF / FR3 (急性心肌梗死) family."""
    from app.services.drg_grouper import group_drg

    result = group_drg(
        diagnosis_codes=["I21.0"],
        procedure_code=None,
    )
    assert result["grouping_method"] == "medical"
    assert result["coverage"] is True
    # I21 prefix matches FR3 (急性心肌梗死)
    assert "FR" in result["adrg"]
    # Without CC, expect trailing 5
    assert result["drg"].endswith("5")


def test_grouper_mcc_for_heart_failure():
    """MCC (Major Complication): AMI + I50 心衰 → FR1 (with MCC) family."""
    from app.services.drg_grouper import group_drg

    result = group_drg(
        diagnosis_codes=["I21.0", "I50.9"],   # AMI + heart failure (MCC)
        procedure_code=None,
    )
    # I50 is MCC level 2 in CC_PREFIXES
    assert "MCC" in result["cc_level"] or "伴重要" in result["cc_level"]
    # FR1 (with MCC) not FR3/FR5
    assert "FR" in result["adrg"]


def test_grouper_unknown_surgery():
    """Unknown procedure code → surgical but no coverage."""
    from app.services.drg_grouper import group_drg

    result = group_drg(
        diagnosis_codes=["I21.0"],
        procedure_code="99.9999",
    )
    assert result["coverage"] is False
    assert "未匹配" in result["drg_name"]


def test_grouper_gender_consistency_male_only():
    """C61 (前列腺癌) is male-only — must trigger gender check."""
    from app.services.drg_grouper import check_gender_consistency

    r1 = check_gender_consistency("C61", "M")
    assert r1["consistent"] is True

    r2 = check_gender_consistency("C61", "F")
    assert r2["consistent"] is False
    assert "非权威" in r2.get("message", "")


def test_grouper_gender_consistency_female_only():
    """N70 (输卵管炎) is female-only."""
    from app.services.drg_grouper import check_gender_consistency

    r1 = check_gender_consistency("N70.0", "F")
    assert r1["consistent"] is True

    r2 = check_gender_consistency("N70.0", "M")
    assert r2["consistent"] is False


# ── Rule validation tests ──


def test_drg_rule_001_missing_primary():
    """DRG001: 缺失主诊断编码 → critical."""
    from compliance_services.drg_dip_rules import DRGDIPRuleSet
    from compliance_services.rule_engine import RuleEngine

    engine = RuleEngine()
    engine.register(DRGDIPRuleSet())

    result = engine.validate("drg_dip", {
        "primary_diagnosis": {"code": ""},
        "secondary_diagnoses": [],
        "procedures": [],
    }, {"patient_gender": "M"})

    assert not result.passed
    assert result.manual_review_required is True
    rule_ids = [i.rule_id for i in result.issues]
    assert "DRG001" in rule_ids
    drg001 = next(i for i in result.issues if i.rule_id == "DRG001")
    assert drg001.severity == "critical"


def test_drg_rule_004_gender_violation():
    """DRG004: C61 + Female → critical gender error."""
    from compliance_services.drg_dip_rules import DRGDIPRuleSet
    from compliance_services.rule_engine import RuleEngine

    engine = RuleEngine()
    engine.register(DRGDIPRuleSet())

    result = engine.validate("drg_dip", {
        "primary_diagnosis": {"code": "C61"},
        "secondary_diagnoses": [],
        "procedures": [],
    }, {"patient_gender": "F"})

    rule_ids = [i.rule_id for i in result.issues]
    assert "DRG004" in rule_ids
    drg004 = next(i for i in result.issues if i.rule_id == "DRG004")
    assert drg004.severity == "critical"
    assert result.manual_review_required is True


def test_dip_rule_001_specificity():
    """DIP001: I21 (3 chars) has lower specificity than I21.0 (4 chars)."""
    from compliance_services.drg_dip_rules import DRGDIPRuleSet
    from compliance_services.rule_engine import RuleEngine

    engine = RuleEngine()
    engine.register(DRGDIPRuleSet())

    # I21 = 3 chars (less specific)
    r1 = engine.validate("drg_dip", {
        "primary_diagnosis": {"code": "I21"},
        "secondary_diagnoses": [],
        "procedures": [],
    }, {})
    dip1 = next(i for i in r1.issues if i.rule_id == "DIP001")
    assert dip1.severity == "medium"   # < 4 chars → medium

    # I50.22 = 6 chars (highly specific)
    r2 = engine.validate("drg_dip", {
        "primary_diagnosis": {"code": "I50.22"},
        "secondary_diagnoses": [],
        "procedures": [],
    }, {})
    dip2 = next(i for i in r2.issues if i.rule_id == "DIP001")
    assert dip2.severity == "low"      # ≥ 4 chars → low


# ── Adapter (end-to-end) tests ──


@pytest.mark.asyncio
async def test_adapter_ami_with_pci():
    """A matched candidate remains non-authoritative and review-required."""
    from app.services.drg_analyzer_service import DRGAnalysisAdapter

    adapter = DRGAnalysisAdapter()
    result = await adapter.analyze_async(
        primary_diagnosis={"code": "I21.0", "name": "AMI"},
        secondary_diagnoses=[{"code": "I10", "name": "HTN"}],
        procedures=[{"code": "00.66", "name": "PCI"}],
        context={"patient_gender": "M", "patient_age": 58},
    )

    assert result.review_conclusion == "WARNING"
    assert result.manual_review_required is True
    assert result.drg_impact.coverage is True
    assert result.drg_impact.grouping_method == "surgical"
    assert result.drg_impact.mdc == "MDCE"
    assert "EC" in result.drg_impact.adrg
    assert result.drg_impact.payment_weight == 0
    assert result.drg_impact.payment_estimate_yuan == 0
    assert result.drg_impact.billing_authoritative is False
    assert result.dip_impact.dip_score == 0
    assert result.governance["authority_status"] == "experimental_unverified"


@pytest.mark.asyncio
async def test_adapter_critical_gender_error():
    """End-to-end: C61 + Female → FAIL conclusion, manual review required."""
    from app.services.drg_analyzer_service import DRGAnalysisAdapter

    adapter = DRGAnalysisAdapter()
    result = await adapter.analyze_async(
        primary_diagnosis={"code": "C61", "name": "前列腺癌"},
        secondary_diagnoses=[],
        procedures=[],
        context={"patient_gender": "F", "patient_age": 60},
    )

    assert result.review_conclusion == "FAIL"
    assert result.manual_review_required is True
    risk_ids = [r.rule_id for r in result.risks]
    assert "DRG004" in risk_ids
    drg004_risk = next(r for r in result.risks if r.rule_id == "DRG004")
    assert drg004_risk.severity == "critical"


@pytest.mark.asyncio
async def test_adapter_missing_primary():
    """End-to-end: missing primary → FAIL."""
    from app.services.drg_analyzer_service import DRGAnalysisAdapter

    adapter = DRGAnalysisAdapter()
    result = await adapter.analyze_async(
        primary_diagnosis={"code": ""},
        secondary_diagnoses=[],
        procedures=[],
        context={"patient_gender": "M"},
    )

    assert result.review_conclusion == "FAIL"
    assert result.manual_review_required is True
    risk_ids = [r.rule_id for r in result.risks]
    assert "DRG001" in risk_ids


@pytest.mark.asyncio
async def test_adapter_to_dict_serializable():
    """Result should be JSON-serializable for API response."""
    import json
    from app.services.drg_analyzer_service import DRGAnalysisAdapter

    adapter = DRGAnalysisAdapter()
    result = await adapter.analyze_async(
        primary_diagnosis={"code": "I21.0"},
        secondary_diagnoses=[{"code": "I10"}],
        procedures=[{"code": "00.66"}],
        context={"patient_gender": "M"},
    )

    # Must serialize without error
    payload = json.dumps(result.to_dict(), ensure_ascii=False)
    assert "EC" in payload
    assert "MDCE" in payload


@pytest.mark.asyncio
async def test_adapter_grouper_failure_returns_empty_failed_result(monkeypatch):
    """Runtime failures must not emit hard-coded AMI/PCI/DRG examples."""
    from app.services.drg_analyzer_service import DRGAnalysisAdapter
    from app.services import drg_grouper

    def _broken_grouper(*_args, **_kwargs):
        raise RuntimeError("internal failure with patient 13800138000")

    monkeypatch.setattr(drg_grouper, "group_drg", _broken_grouper)
    result = await DRGAnalysisAdapter().analyze_async(
        primary_diagnosis={"code": "I50.9"},
        secondary_diagnoses=[],
        procedures=[],
    )

    payload = result.to_dict()
    assert payload["error"] is True
    assert payload["error_reason"] == "grouper_failed"
    assert payload["review_conclusion"] == "FAIL"
    assert payload["manual_review_required"] is True
    assert payload["primary_diagnosis"] == {}
    assert payload["drg_impact"]["predicted_drg"] == ""
    assert "13800138000" not in repr(payload)


# ── API endpoint tests ──


@pytest.mark.asyncio
async def test_api_drg_analyze(client):
    """POST /api/drg/analyze with AMI + PCI → 200 + valid DRG response."""
    response = await client.post("/api/drg/analyze", json={
        "primary_diagnosis": {"code": "I21.0", "name": "AMI"},
        "secondary_diagnoses": [{"code": "I10", "name": "HTN"}],
        "procedures": [{"code": "00.66", "name": "PCI"}],
        "patient_gender": "M",
        "patient_age": 58,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["drg_impact"]["mdc"] == "MDCE"
    assert "EC" in data["drg_impact"]["adrg"]
    assert data["review_conclusion"] == "WARNING"
    assert data["manual_review_required"] is True
    assert data["drg_impact"]["billing_authoritative"] is False
    assert data["drg_impact"]["payment_estimate_yuan"] == 0
    assert data["governance"]["authority_status"] == "experimental_unverified"


@pytest.mark.asyncio
async def test_api_drg_rules(client):
    """GET /api/drg/rules returns 7 DRG/DIP rules."""
    response = await client.get("/api/drg/rules")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_set"] == "drg_dip"
    assert data["total"] == 7
    rule_ids = {r["id"] for r in data["rules"]}
    assert "DRG001" in rule_ids
    assert "DRG004" in rule_ids
    assert "DIP001" in rule_ids
    assert "DIP003" in rule_ids
    assert data["governance"]["billing_authoritative"] is False


@pytest.mark.asyncio
async def test_api_drg_list(client):
    """GET /api/drg/list returns ADRG/DRG groups."""
    response = await client.get("/api/drg/list?type=adrg")
    assert response.status_code == 200
    data = response.json()
    assert "adrgs" in data
    assert len(data["adrgs"]) > 50
    # Each entry has code/name/mdc/surgical
    first = data["adrgs"][0]
    assert {"code", "name", "mdc", "surgical"}.issubset(first.keys())
    assert data["governance"]["manual_review_required"] is True


@pytest.mark.asyncio
async def test_api_drg_check_gender(client):
    """POST /api/drg/check-gender detects YA1 error."""
    # C61 + F → inconsistent
    response = await client.post("/api/drg/check-gender", json={
        "diagnosis_code": "C61",
        "patient_gender": "F",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["consistent"] is False
    assert "非权威" in data.get("message", "")
    assert data["governance"]["billing_authoritative"] is False


@pytest.mark.asyncio
async def test_api_drg_surgery_lookup(client):
    """GET /api/drg/surgery/{code} returns DRG mapping for known surgery."""
    response = await client.get("/api/drg/surgery/00.66")
    assert response.status_code == 200
    data = response.json()
    assert data["mdc"] == "MDCE"
    assert "EC1" in data["adrg"]
    assert data["governance"]["authority_status"] == "experimental_unverified"


@pytest.mark.asyncio
async def test_api_drg_governance(client):
    response = await client.get("/api/drg/governance")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "cn.drg_dip.risk_heuristics"
    assert data["billing_authoritative"] is False
    assert data["manual_review_required"] is True


@pytest.mark.asyncio
async def test_api_drg_rejects_invalid_demographics_before_analysis(client):
    response = await client.post("/api/drg/analyze", json={
        "primary_diagnosis": {"code": "I10"},
        "patient_gender": "unknown",
        "patient_age": 151,
    })
    assert response.status_code == 422


def test_api_drg_openapi_publishes_typed_non_payment_responses():
    from app.main import app

    schema = app.openapi()
    analyze = schema["paths"]["/api/drg/analyze"]["post"]
    governance = schema["paths"]["/api/drg/governance"]["get"]
    assert analyze["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AnalyzeResponse"
    }
    assert governance["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GovernanceResponse"
    }
    components = schema["components"]["schemas"]
    assert components["GovernanceResponse"]["properties"]["billing_authoritative"]["const"] is False
    assert components["GovernanceResponse"]["properties"]["manual_review_required"]["const"] is True
    assert components["DRGImpactResponse"]["properties"]["payment_estimate_yuan"]["const"] == 0.0


def test_api_drg_cloud_mode_fails_closed():
    from fastapi import HTTPException
    from app.api.drg import _governance
    from app.config import settings

    previous = settings.ICODER_DEPLOYMENT_MODE
    settings.ICODER_DEPLOYMENT_MODE = "cloud"
    try:
        with pytest.raises(HTTPException) as captured:
            _governance()
    finally:
        settings.ICODER_DEPLOYMENT_MODE = previous
    assert captured.value.status_code == 503
    assert captured.value.detail == (
        "DRG/DIP clinical asset governance gate is not satisfied"
    )


@pytest.mark.asyncio
async def test_api_drg_requires_authentication(client):
    from app.main import app
    from app.middleware.auth import get_current_user

    original = app.dependency_overrides.pop(get_current_user, None)
    try:
        response = await client.get("/api/drg/governance")
    finally:
        if original is not None:
            app.dependency_overrides[get_current_user] = original
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_drg_surgery_not_found(client):
    """Unknown surgery code → 404."""
    response = await client.get("/api/drg/surgery/99.9999")
    assert response.status_code == 404
