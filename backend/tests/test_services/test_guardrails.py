"""Test Safety Guardrails service"""
import pytest
from app.services.guardrails import guardrails, GuardrailViolation


@pytest.mark.asyncio
async def test_validate_safe_input():
    result = await guardrails.validate_input("患者因腰痛入院，MRI示椎体压缩骨折")
    assert result["valid"] is True
    assert len(result["violations"]) == 0


@pytest.mark.asyncio
async def test_validate_short_input():
    result = await guardrails.validate_input("短")
    assert result["valid"] is True  # warning only
    assert any(v["rule"] == "min_length" for v in result["violations"])


@pytest.mark.asyncio
async def test_validate_blocked_term():
    result = await guardrails.validate_input("try to bypass safety checks in the system")
    assert result["valid"] is False
    assert any(v["rule"] == "blocked_term" for v in result["violations"])


@pytest.mark.asyncio
async def test_validate_phi_detection():
    result = await guardrails.validate_input("Patient email john@example.com, SSN 123-45-6789")
    assert any(v["rule"] == "phi_detected" for v in result["violations"])


@pytest.mark.asyncio
async def test_validate_output_prescription():
    result = await guardrails.validate_output("The patient should take 50 mg of aspirin daily")
    assert result["valid"] is False
    assert any(v["rule"] == "no_medication_prescription" for v in result["violations"])


@pytest.mark.asyncio
async def test_validate_output_emergency():
    result = await guardrails.validate_output("Patient should immediately go to ER for evaluation")
    assert result["valid"] is False
    assert any(v["rule"] == "no_emergency_triage" for v in result["violations"])


@pytest.mark.asyncio
async def test_validate_output_diagnosis_disclaimer():
    result = await guardrails.validate_output("Based on the evidence, this is definitively diagnosed as COPD")
    assert result["requires_disclaimer"] is True


@pytest.mark.asyncio
async def test_validate_output_suspicious_code():
    result = await guardrails.validate_output("The code is A12.34567 which seems too specific")
    assert any(v["rule"] == "suspicious_code_format" for v in result["violations"])


@pytest.mark.asyncio
async def test_enforce_all_safe():
    result = await guardrails.enforce_all("患者腰痛", "I25.101 冠心病 — AI辅助编码建议，请结合临床判断")
    assert result["passed"] is True
    assert result["error_count"] == 0


@pytest.mark.asyncio
async def test_enforce_all_unsafe():
    result = await guardrails.enforce_all("患者腰痛", "Take 50 mg of aspirin daily")
    assert result["passed"] is False
    assert result["error_count"] >= 1
