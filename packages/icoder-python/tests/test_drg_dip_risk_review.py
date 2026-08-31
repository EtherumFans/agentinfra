import json

import httpx
import pytest

from icoder_sdk import iCoDerClient, iCoDerConfig


GOVERNANCE = {
    "asset_id": "cn.drg_dip.risk_heuristics",
    "version": "1.0.0-development",
    "asset_type": "risk_review_rule_pack",
    "jurisdiction": "CN_GENERIC_DEVELOPMENT",
    "authority_status": "experimental_unverified",
    "license_status": "external_review_required",
    "effective_from": None,
    "effective_to": None,
    "billing_authoritative": False,
    "manual_review_required": True,
    "use_restriction": (
        "development_risk_review_only_not_for_grouping_payment_or_settlement"
    ),
}


def _client(handler):
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_drg_dip_governance_is_authenticated_and_development_only():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json=GOVERNANCE)

    client = _client(handler)
    try:
        result = client.drg_dip_risk_review.get_governance()
    finally:
        client.close()

    assert calls == [("GET", "/api/drg/governance")]
    assert result["billing_authoritative"] is False
    assert result["manual_review_required"] is True


def test_drg_dip_analysis_normalizes_input_and_accepts_zero_payment_candidate():
    captured = {}
    payload = {
        "primary_diagnosis": {
            "code": "I10", "name": "", "description": "", "confidence": 1
        },
        "secondary_diagnoses": [],
        "procedures": [],
        "drg_impact": {
            "predicted_drg": "FR19", "drg_name": "candidate", "mdc": "MDCF",
            "mdc_name": "", "adrg": "FR1", "cc_level": "",
            "grouping_method": "medical", "coverage": True, "payment_weight": 0,
            "payment_estimate_yuan": 0, "billing_authoritative": False,
            "result_status": "experimental_candidate",
        },
        "dip_impact": {
            "dip_score": 0, "dip_score_ceiling": 0, "payment_estimate_yuan": 0,
            "note": "not available", "billing_authoritative": False,
        },
        "risks": [], "recommendations": [], "quality_flags": {},
        "governance": GOVERNANCE, "manual_review_required": True,
        "review_conclusion": "WARNING", "confidence": 0.5,
        "notes": "development only", "provider": "drg-analyzer",
        "model": "development", "is_mock": False, "error": False,
        "error_reason": "",
    }

    def handler(request):
        captured.update({
            "method": request.method,
            "path": request.url.path,
            "json": json.loads(request.content),
        })
        return httpx.Response(200, json=payload)

    client = _client(handler)
    try:
        result = client.drg_dip_risk_review.analyze({"code": "I10"})
    finally:
        client.close()

    assert captured == {
        "method": "POST", "path": "/api/drg/analyze",
        "json": {
            "primary_diagnosis": {"code": "I10"},
            "secondary_diagnoses": [], "procedures": [],
            "patient_gender": "", "patient_age": None,
        },
    }
    assert result["drg_impact"]["payment_estimate_yuan"] == 0


def test_drg_dip_resource_fails_closed_on_billing_claim():
    bad = {**GOVERNANCE, "billing_authoritative": True}
    client = _client(lambda request: httpx.Response(200, json=bad))
    try:
        with pytest.raises(ValueError, match="development-only"):
            client.drg_dip_risk_review.get_governance()
    finally:
        client.close()


def test_drg_dip_resource_rejects_invalid_age_before_transport():
    client = _client(lambda request: pytest.fail("transport must not be called"))
    try:
        with pytest.raises(ValueError, match="patient_age"):
            client.drg_dip_risk_review.analyze({"code": "I10"}, patient_age=151)
    finally:
        client.close()
