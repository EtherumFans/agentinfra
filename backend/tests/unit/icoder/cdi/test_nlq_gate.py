"""Unit tests for CDI Non-leading Query Gate (Phase 5 Track D Gate 5).

Tests NLQ-001..009 rules from
``reports/phase5_track_d/CORTI_CDI_PROVIDER_QUERY_AUDIT.md``.

Each rule is exercised with both a PASS and a BLOCK fixture, then a
full Corti-compliant query is run as an integration smoke test.
"""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.cdi import (
    NLQGateResult,
    ProviderQueryForGate,
    RuleResult,
    evaluate_nlq,
)


# ---------------------------------------------------------------------------
# Compliant query (Corti example, zh-CN adapted from agent_pack.json)
# ---------------------------------------------------------------------------


COMPLIANT_QUERY = ProviderQueryForGate(
    topic="肺炎病原体",
    evidence_quote="诊断: 肺炎",
    query_text=(
        "入院记录诊断为'肺炎', 痰培养结果为'肺炎链球菌'. "
        "请根据您的临床判断回答:"
    ),
    response_options=[
        "A. 肺炎病原体为肺炎链球菌 (J13)",
        "B. 肺炎病原体为其他已知病原体 (请在自由文本中说明)",
        "C. 痰培养结果为定植菌, 不作为病原体",
        "D. 无法确定 (unable to determine)",
        "E. 临床不支持 (痰培养结果与临床表现不符)",
    ],
)


# ---------------------------------------------------------------------------
# NLQ-001 no_yes_no_opening
# ---------------------------------------------------------------------------


def test_nlq_001_pass_on_open_ended_query() -> None:
    result = evaluate_nlq(COMPLIANT_QUERY)
    nlq001 = next(r for r in result.rules_passed_detail if r.rule_id == "NLQ-001")
    assert nlq001.passed is True


@pytest.mark.parametrize(
    "leading_text",
    [
        "是否为肺炎链球菌性肺炎?",
        "是不是肺炎链球菌感染?",
        "Would you agree the patient has pneumonia?",
        "Is it bacterial pneumonia?",
    ],
)
def test_nlq_001_block_on_yes_no_opening(leading_text: str) -> None:
    q = ProviderQueryForGate(
        query_text=leading_text,
        response_options=["A", "B", "无法确定"],
        evidence_quote="肺炎",
    )
    result = evaluate_nlq(q)
    assert result.verdict == "BLOCK"
    assert "NLQ-001" in [r.rule_id for r in result.rules_failed]


# ---------------------------------------------------------------------------
# NLQ-003 / NLQ-004 / NLQ-005 structural rules
# ---------------------------------------------------------------------------


def test_nlq_003_block_on_missing_response_options() -> None:
    q = ProviderQueryForGate(
        query_text="请回答病原体是什么",
        response_options=[],
        evidence_quote="肺炎",
    )
    result = evaluate_nlq(q)
    assert "NLQ-003" in [r.rule_id for r in result.rules_failed]


def test_nlq_004_block_on_two_options() -> None:
    q = ProviderQueryForGate(
        query_text="请回答病原体",
        response_options=["A. 链球菌", "B. 其他"],
        evidence_quote="肺炎",
    )
    result = evaluate_nlq(q)
    assert "NLQ-004" in [r.rule_id for r in result.rules_failed]


def test_nlq_005_block_on_missing_escape_hatch() -> None:
    q = ProviderQueryForGate(
        query_text="请回答病原体",
        response_options=[
            "A. 肺炎链球菌",
            "B. 其他病原体",
            "C. 定植菌",
        ],  # 3 options, but no 无法确定 / 临床不支持
        evidence_quote="肺炎",
    )
    result = evaluate_nlq(q)
    assert "NLQ-005" in [r.rule_id for r in result.rules_failed]


def test_nlq_005_accepts_english_escape_hatch() -> None:
    q = ProviderQueryForGate(
        query_text="please clarify etiology",
        response_options=[
            "A. prerenal",
            "B. ATN",
            "C. clinically undetermined at this time",
        ],
        evidence_quote="AKI",
    )
    result = evaluate_nlq(q)
    nlq005 = next(r for r in result.rules_passed_detail if r.rule_id == "NLQ-005")
    assert nlq005.passed is True


# ---------------------------------------------------------------------------
# NLQ-006 no_treatment_advice
# ---------------------------------------------------------------------------


def test_nlq_006_block_on_treatment_advice_zh() -> None:
    q = ProviderQueryForGate(
        query_text="建议治疗: 静脉头孢曲松 2g q24h",
        response_options=["A", "B", "无法确定"],
        evidence_quote="肺炎",
    )
    result = evaluate_nlq(q)
    assert "NLQ-006" in [r.rule_id for r in result.rules_failed]


def test_nlq_006_block_on_treatment_advice_en() -> None:
    q = ProviderQueryForGate(
        query_text="Patient should be treated with ceftriaxone",
        response_options=["A", "B", "unable to determine"],
        evidence_quote="pneumonia",
    )
    result = evaluate_nlq(q)
    assert "NLQ-006" in [r.rule_id for r in result.rules_failed]


# ---------------------------------------------------------------------------
# NLQ-007 no_undiagnosed_condition_in_query (evidence_required)
# ---------------------------------------------------------------------------


def test_nlq_007_block_when_evidence_quote_empty() -> None:
    q = ProviderQueryForGate(
        query_text="请澄清病原体",
        response_options=["A", "B", "无法确定"],
        evidence_quote="",
    )
    result = evaluate_nlq(q)
    assert "NLQ-007" in [r.rule_id for r in result.rules_failed]


# ---------------------------------------------------------------------------
# NLQ-008 no_single_diagnosis_suggested
# ---------------------------------------------------------------------------


def test_nlq_008_block_on_marked_correct_option() -> None:
    q = ProviderQueryForGate(
        query_text="请回答病原体",
        response_options=[
            "A. 肺炎链球菌 (正确)",
            "B. 其他",
            "C. 无法确定",
        ],
        evidence_quote="肺炎",
    )
    result = evaluate_nlq(q)
    assert "NLQ-008" in [r.rule_id for r in result.rules_failed]


# ---------------------------------------------------------------------------
# NLQ-009 no_payment_terms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_text",
    [
        "为提升 DRG 权重, 请澄清病原体",
        "建议补编 J13 以优化医保结算",
        "Maximize reimbursement by clarifying etiology",
    ],
)
def test_nlq_009_block_on_payment_terms(bad_text: str) -> None:
    q = ProviderQueryForGate(
        query_text=bad_text,
        response_options=["A", "B", "无法确定"],
        evidence_quote="肺炎",
    )
    result = evaluate_nlq(q)
    assert "NLQ-009" in [r.rule_id for r in result.rules_failed]


# ---------------------------------------------------------------------------
# Full compliant query integration
# ---------------------------------------------------------------------------


def test_compliant_query_passes_all_9_rules() -> None:
    result = evaluate_nlq(COMPLIANT_QUERY)
    assert isinstance(result, NLQGateResult)
    assert result.verdict == "PASS"
    assert result.rules_evaluated == 9
    assert result.rules_passed == 9
    assert len(result.rules_failed) == 0
    assert result.block_reasons == []


def test_block_reasons_include_evidence() -> None:
    """Each failed rule's block_reason entry must include rule_id + name +
    evidence (so reviewers can see WHY the query was blocked)."""

    q = ProviderQueryForGate(
        query_text="是否为肺炎?",
        response_options=[],
        evidence_quote="",
    )
    result = evaluate_nlq(q)
    assert result.verdict == "BLOCK"
    for reason in result.block_reasons:
        # format: "<rule_id> (<name>): <evidence>"
        assert reason.startswith("NLQ-")
        assert "(" in reason and ")" in reason
        assert ":" in reason


def test_rule_result_dataclass_shape() -> None:
    """RuleResult is the audit trail unit. Verify it has the 5 required fields."""

    r = RuleResult(
        rule_id="NLQ-999",
        name="test_rule",
        description="test",
        passed=True,
        evidence="test",
        action="PASS",
    )
    assert r.rule_id and r.name and r.description and isinstance(r.passed, bool)
    assert r.action in {"PASS", "BLOCK"}
