"""T2 — PHI redactor (SPEC §6.3)."""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.phi_redactor import (
    PHIPayloadRedactionResult,
    PHIRedactionError,
    PHIRedactionResult,
    PHIRedactor,
    redact_payload,
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
    assert r.redacted_text.startswith("医保号: ")
    assert "<REDACTED:INSURANCE_NO>" in r.redacted_text
    assert "B98765432" not in r.redacted_text


def test_prior_authorization_labels_survive_redaction_without_phi_values() -> None:
    text = (
        "患者姓名：张三\n出生日期：1975-06-20\n"
        "参保人编号：MEMBER-001\n申请医师：李医生\n"
        "申请医师资质：主任医师\n医师执业编号：PHYSICIAN-001\n"
        "支付方：示例省医保\n申请类型：药品预授权\n"
        "申请药品：阿达木单抗\n给药途径：皮下注射\n"
        "申请原因：继续使用已记录药品\n支付方要求：提供既往治疗\n"
        "支付政策编号：PA-001\n支付政策版本：2026.1"
    )
    result = PHIRedactor().redact(text)

    for label in (
        "患者姓名：", "出生日期：", "参保人编号：", "申请医师：",
        "申请医师资质：", "医师执业编号：", "支付方：", "申请类型：",
        "申请药品：", "给药途径：", "申请原因：", "支付方要求：",
        "支付政策编号：", "支付政策版本：",
    ):
        assert label in result.redacted_text
    for secret in ("张三", "1975-06-20", "MEMBER-001", "李医生", "PHYSICIAN-001"):
        assert secret not in result.redacted_text
    for clinical_or_policy_text in (
        "阿达木单抗", "皮下注射", "继续使用已记录药品",
        "提供既往治疗", "PA-001", "2026.1",
    ):
        assert clinical_or_policy_text in result.redacted_text


def test_claim_check_labels_survive_redaction_without_phi_values() -> None:
    text = (
        "结算单号：CLAIM-001\n结算类型：医保住院结算\n服务日期：2026-08-20\n"
        "患者姓名：张某\n参保人编号：TEST-MEMBER-001\n医疗机构：示例医院\n"
        "申请医师：李医生\n医师执业编号：TEST-PHYSICIAN-001\n支付方：示例市医保\n"
        "统筹区：示例市\n拟报诊断：K35.80 急性阑尾炎\n"
        "申报总金额：16800.00\n"
        "临床文书摘录：入院记录记载急性阑尾炎\n支付方要求：条款A要求提交入院记录\n"
        "支付政策编号：POLICY-1\n支付政策版本：2026.1\n政策生效日期：2026-01-01\n"
        "政策来源：用户提供规则"
    )
    result = PHIRedactor().redact(text)

    for label in (
        "结算单号：", "结算类型：", "服务日期：", "患者姓名：", "参保人编号：",
        "医疗机构：", "申请医师：", "医师执业编号：", "支付方：", "统筹区：",
        "拟报诊断：", "申报总金额：", "临床文书摘录：", "支付方要求：", "支付政策编号：",
        "支付政策版本：", "政策生效日期：", "政策来源：",
    ):
        assert label in result.redacted_text
    for secret in ("张某", "TEST-MEMBER-001", "李医生", "TEST-PHYSICIAN-001"):
        assert secret not in result.redacted_text
    assert PHIRedactor().redact(result.redacted_text).redacted_text == result.redacted_text
    for clinical_or_policy_text in (
        "医保住院结算", "示例医院", "示例市医保", "K35.80 急性阑尾炎",
        "入院记录记载急性阑尾炎", "条款A要求提交入院记录", "POLICY-1", "2026.1",
    ):
        assert clinical_or_policy_text in result.redacted_text


def test_denial_appeal_labels_and_workflow_facts_survive_redaction() -> None:
    text = (
        "拒付原因：支付方通知记录需要补充指定材料\n"
        "患者姓名：赵某\n参保人编号：TEST-MEMBER-001\n"
        "经治医师：陈医生\n医师执业编号：TEST-PHYSICIAN-001\n"
        "拒付明细：行1：示例项目，金额1200.00\n"
        "拟申诉诊断：示例已报诊断 TEST-DX\n"
        "拟申诉手术：示例已报手术 TEST-PROC\n"
        "拟申诉项目：示例项目 TEST-ITEM\n"
        "处理路径：申诉并附临床文档\n请求事项：请求人工复核该拒付记录"
    )
    result = PHIRedactor().redact(text)

    for phrase in (
        "支付方通知记录需要补充指定材料",
        "拒付明细：行1：示例项目，金额1200.00",
        "拟申诉诊断：示例已报诊断 TEST-DX",
        "拟申诉手术：示例已报手术 TEST-PROC",
        "拟申诉项目：示例项目 TEST-ITEM",
        "处理路径：申诉并附临床文档",
        "请求事项：请求人工复核该拒付记录",
    ):
        assert phrase in result.redacted_text
    for secret in ("赵某", "TEST-MEMBER-001", "陈医生", "TEST-PHYSICIAN-001"):
        assert secret not in result.redacted_text

    second = PHIRedactor().redact(result.redacted_text)
    assert second.redacted_text == result.redacted_text
    assert second.redaction_applied is False


def test_chinese_name_redacted():
    # Surname 张 + 2 given chars = 3-char name "张三丰"
    r = PHIRedactor().redact("张三丰入院治疗")
    assert "<REDACTED:NAME>" in r.redacted_text
    assert "张三丰" not in r.redacted_text
    assert "NAME" in r.entity_types


def test_common_chinese_clinical_terms_are_not_redacted_as_names() -> None:
    text = (
        "入院诊断:左侧肋骨骨折，高血压。查体正常，双肺清晰。"
        "心电图:窦性心律，前壁导联ST段抬高。心超:左室射血分数65%。"
    )
    result = PHIRedactor().redact(text)
    assert result.redacted_text == text
    assert "NAME" not in result.entity_types


def test_common_pathology_and_lab_terms_are_not_redacted_as_names() -> None:
    text = (
        "术前诊断：急性阑尾炎（单纯性，无穿孔）。Anti-HBs 阴性。"
        "心电图：ST 段抬高；双肺底湿啰音。"
    )
    result = PHIRedactor().redact(text)

    assert result.redacted_text == text
    assert "NAME" not in result.entity_types


def test_standalone_diuretic_treatment_is_not_redacted_as_name() -> None:
    text = "\u8bca\u7597\u7ecf\u8fc7\uff1a\u5229\u5c3f\u6cbb\u7597\u3002"
    result = PHIRedactor().redact(text)

    assert "\u5229\u5c3f\u6cbb\u7597" in result.redacted_text
    assert "<REDACTED:NAME>" not in result.redacted_text


def test_clinical_education_directive_is_not_redacted_as_name() -> None:
    text = "感染患者若出现器官功能障碍，应立即启动脓毒症评估流程"
    result = PHIRedactor().redact(text)

    assert result.redacted_text == text
    assert "<REDACTED:NAME>" not in result.redacted_text


def test_clinical_term_protection_does_not_exempt_real_name() -> None:
    result = PHIRedactor().redact("患者张三，高血压，查体正常。")
    assert "张三" not in result.redacted_text
    assert "高血压" in result.redacted_text
    assert "查体正常" in result.redacted_text
    assert "NAME" in result.entity_types


def test_anesthesia_terms_are_not_destroyed_by_chinese_name_detection() -> None:
    text = "手术记录：全麻下行腹腔镜胆囊切除术，局部麻醉备用。"
    result = PHIRedactor().redact(text)

    assert result.redacted_text == text
    assert "全麻" in result.redacted_text
    assert "局部麻醉" in result.redacted_text
    assert "NAME" not in result.entity_types


def test_anesthesia_term_protection_does_not_exempt_real_quan_surname() -> None:
    result = PHIRedactor().redact("全红婵接受全麻手术。")

    assert "全红婵" not in result.redacted_text
    assert "全麻" in result.redacted_text
    assert "NAME" in result.entity_types


def test_ambiguous_quan_ma_person_name_is_not_globally_allowlisted() -> None:
    result = PHIRedactor().redact("患者全麻入院。")

    assert "全麻" not in result.redacted_text
    assert "<REDACTED:NAME>" in result.redacted_text
    assert "NAME" in result.entity_types


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


# ---------------------------------------------------------------------------
# Recursive JSON-like payload boundary
# ---------------------------------------------------------------------------


def test_nested_payload_redacts_text_data_and_metadata_values():
    raw_phone = "13800138000"
    result = redact_payload({
        "parts": [
            {"kind": "text", "text": f"电话 {raw_phone}"},
            {
                "kind": "data",
                "data": {"patient": {"contacts": [raw_phone]}},
            },
        ],
        "metadata": {"callback": raw_phone},
    })

    assert isinstance(result, PHIPayloadRedactionResult)
    rendered = repr(result.value)
    assert raw_phone not in rendered
    assert rendered.count("<REDACTED:PHONE>") == 3
    assert result.entity_counts["PHONE"] == 3
    assert result.entity_types == ["PHONE"]
    assert result.redaction_applied is True


def test_payload_preserves_schema_keys_and_primitives():
    payload = {"patient_phone": 123, "active": True, "score": 0.5, "none": None}
    result = redact_payload(payload)
    assert result.value == payload
    assert result.redaction_applied is False


def test_payload_depth_limit_fails_closed():
    with pytest.raises(PHIRedactionError, match="maximum depth"):
        redact_payload({"a": {"b": "safe"}}, max_depth=1)


def test_payload_node_limit_fails_closed():
    with pytest.raises(PHIRedactionError, match="maximum node count"):
        redact_payload(["one", "two"], max_nodes=2)


def test_payload_unsupported_type_fails_closed_without_stringifying():
    class _ContainsSecret:
        def __repr__(self) -> str:
            return "13800138000"

    with pytest.raises(PHIRedactionError, match="unsupported type") as excinfo:
        redact_payload({"value": _ContainsSecret()})
    assert "13800138000" not in str(excinfo.value)
