"""T2 — PHI redactor (SPEC §6.3)."""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.phi_redactor import (
    PHIRedactionError,
    PHIRedactionResult,
    PHIRedactor,
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_empty_text_returns_empty():
    r = PHIRedactor().redact("")
    assert r.redacted_text == ""
    assert r.entity_types == []
    assert r.redaction_applied is False


def test_no_phi_passes_through():
    text = "急性心梗患者，无特殊既往史"
    r = PHIRedactor().redact(text)
    assert r.redacted_text == text
    assert r.entity_types == []
    assert r.redaction_applied is False


def test_id_card_redacted():
    text = "患者身份证 110101199001011234"
    r = PHIRedactor().redact(text)
    assert "<REDACTED:ID_CARD>" in r.redacted_text
    assert "110101199001011234" not in r.redacted_text
    assert "ID_CARD" in r.entity_types
    assert r.entity_counts["ID_CARD"] >= 1


def test_mobile_phone_redacted():
    r = PHIRedactor().redact("联系电话 13800138000")
    assert "<REDACTED:PHONE>" in r.redacted_text
    assert "13800138000" not in r.redacted_text


def test_email_redacted():
    r = PHIRedactor().redact("联系 zhang.san@example.com 收报告")
    assert "<REDACTED:EMAIL>" in r.redacted_text
    assert "zhang.san@example.com" not in r.redacted_text


def test_address_province_redacted():
    r = PHIRedactor().redact("现住址北京市朝阳区建国路88号")
    assert "<REDACTED:ADDRESS>" in r.redacted_text
    assert "北京市" not in r.redacted_text


def test_medical_record_no_redacted():
    r = PHIRedactor().redact("病案号: A12345678")
    assert "<REDACTED:MEDICAL_RECORD_NO>" in r.redacted_text
    assert "A12345678" not in r.redacted_text


def test_insurance_no_redacted():
    r = PHIRedactor().redact("医保号: B98765432")
    assert "<REDACTED:INSURANCE_NO>" in r.redacted_text
    assert "B98765432" not in r.redacted_text


def test_chinese_name_redacted():
    # Surname 张 + 2 given chars = 3-char name "张三丰"
    r = PHIRedactor().redact("张三丰入院治疗")
    assert "<REDACTED:NAME>" in r.redacted_text
    assert "张三丰" not in r.redacted_text
    assert "NAME" in r.entity_types


def test_multiple_phi_in_one_text():
    text = "张三 (13800138000, 110101199001011234) 来自北京市朝阳区"
    r = PHIRedactor().redact(text)
    assert r.redaction_applied
    # All four entity types detected
    assert {"NAME", "PHONE", "ID_CARD", "ADDRESS"}.issubset(set(r.entity_types))
    # No raw PHI leaked
    for forbidden in ("张三", "13800138000", "110101199001011234", "北京市"):
        assert forbidden not in r.redacted_text


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_entity_counts_track_repetitions():
    text = "电话 13800138000 或 13900139000 或 13700137000"
    r = PHIRedactor().redact(text)
    assert r.entity_counts["PHONE"] == 3
    assert r.redacted_text.count("<REDACTED:PHONE>") == 3


def test_to_dict_serializes_result():
    r = PHIRedactor().redact("电话 13800138000")
    d = r.to_dict()
    assert d["redacted_text"] == r.redacted_text
    assert "PHONE" in d["entity_types"]
    assert d["entity_counts"]["PHONE"] >= 1


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_none_input_raises_phi_error():
    redactor = PHIRedactor()
    with pytest.raises(PHIRedactionError) as excinfo:
        redactor.redact(None)  # type: ignore[arg-type]
    assert excinfo.value.code == "phi_redaction_failed"
    assert excinfo.value.http_status == 500
    assert excinfo.value.retryable is False


def test_non_string_input_raises_phi_error():
    redactor = PHIRedactor()
    with pytest.raises(PHIRedactionError):
        redactor.redact(12345)  # type: ignore[arg-type]


def test_phi_error_is_orchestrator_error():
    err = PHIRedactionError("boom")
    from app.icoder.agent_runtime.orchestrator.errors import OrchestratorError

    assert isinstance(err, OrchestratorError)
    assert err.stage == "received"


# ---------------------------------------------------------------------------
# Idempotence + determinism
# ---------------------------------------------------------------------------


def test_redaction_is_deterministic():
    text = "张三 电话 13800138000"
    a = PHIRedactor().redact(text)
    b = PHIRedactor().redact(text)
    assert a.redacted_text == b.redacted_text
    assert a.entity_counts == b.entity_counts


def test_redacted_text_is_safe_to_re_redact():
    """Re-running the redactor on already-redacted text must NOT break it."""
    once = PHIRedactor().redact("张三 电话 13800138000")
    twice = PHIRedactor().redact(once.redacted_text)
    assert twice.redacted_text == once.redacted_text  # idempotent
    assert "张三" not in twice.redacted_text
    assert "13800138000" not in twice.redacted_text