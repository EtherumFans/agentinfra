"""Phase 3-D1 Task 5 — 3 Runnable Agents unit tests.

Tests the 3 simple runnable agents (v1 — pure RuleEngine, no LLM):
  - code-validation-agent: RuleEngine (R001-R010 + MC-R-M80-001) on a coding set
  - compliance-guardrail-agent: RuleEngine + guardrail heuristics (CG-001..CG-004)
  - note-completeness-agent: regex-based EMR section detection

Phase 4-C: code-validation-agent was migrated to LLMWithToolsProvider
(v2 shape — ``validated_codes`` + ``cross_code_issues``). To keep
testing the v1 RuleEngine shape (``fired_rules`` +
``code_assignment_summary``), these tests now import from
``agent_legacy.py``. The v2 LLM path is tested in
``test_code_validation_v2.py``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

# Phase 4-C: import from agent_legacy (v1 RuleEngine path) so the v1
# assertions (fired_rules / code_assignment_summary) still hold.
from official_agents.code_validation.agent_legacy import run as code_validation_run
from official_agents.compliance_guardrail.agent import run as compliance_guardrail_run
from official_agents.note_completeness.agent import run as note_completeness_run


def _run(coro, **_kwargs):
    """Run an async coroutine to completion (sync wrapper).

    The extra kwargs are ignored — they're a leftover from when the
    helper used to forward them; keeping the signature stable so the
    test bodies that pass run_id= don't break.
    """
    return asyncio.new_event_loop().run_until_complete(coro)


def _run_with_run_id(coro_factory, input_text: str, run_id: str):
    """Run an agent's run(input_text, run_id=...) and return the result."""
    return asyncio.new_event_loop().run_until_complete(
        coro_factory(input_text, run_id=run_id)
    )


# ── Code Validation Agent ────────────────────────────────────────────


def test_code_validation_passes_clean_coding_set():
    """A coding set with valid codes + evidence + confidence passes."""
    payload = json.dumps({
        "primary_diagnosis": {
            "code": "I50.9",
            "description": "心力衰竭",
            "confidence": 0.95,
            "category": "primary",
            "evidence": ["患者出现呼吸困难"],
        },
        "secondary_diagnoses": [
            {
                "code": "I10",
                "description": "高血压",
                "confidence": 0.9,
                "category": "secondary",
                "evidence": ["既往高血压史"],
            }
        ],
        "procedures": [],
    })
    result = _run(code_validation_run(payload))
    assert result["review_conclusion"] == "PASS"
    assert result["manual_review_required"] is False
    assert result["rule_set"] == "medical_coding"
    assert "R001" in result["fired_rules"]
    assert "MC-R-M80-001" in result["fired_rules"]
    assert result["code_assignment_summary"]["primary_diagnosis"]["code"] == "I50.9"
    assert result["trace_refs"]["agent_ref"] == "icoder/code-validation-agent@1.0.0"


def test_code_validation_fails_on_missing_primary():
    """Empty coding set → R001 fires critical → FAIL."""
    result = _run(code_validation_run('{"primary_diagnosis":{}, "procedures":[]}'))
    assert result["review_conclusion"] == "FAIL"
    assert result["manual_review_required"] is True
    rule_ids = [i["rule_id"] for i in result["issues_found"]]
    assert "R001" in rule_ids


def test_code_validation_parses_free_text_with_icd_codes():
    """Free text containing ICD-10 codes is parsed via regex."""
    result = _run(code_validation_run(
        "Patient diagnosed with I50.9 and J44.1, underwent 33.24"
    ))
    summary = result["code_assignment_summary"]
    assert summary["primary_diagnosis"]["code"] == "I50.9"
    secondary_codes = [d["code"] for d in summary["secondary_diagnoses"]]
    assert "J44.1" in secondary_codes
    assert summary["procedures"][0]["code"] == "33.24"


def test_code_validation_low_confidence_triggers_manual_review():
    """Confidence < 0.7 → R007 fires → manual_review_required True."""
    payload = json.dumps({
        "primary_diagnosis": {
            "code": "I50.9",
            "confidence": 0.5,
            "evidence": ["some evidence"],
        },
        "secondary_diagnoses": [],
        "procedures": [],
    })
    result = _run(code_validation_run(payload))
    rule_ids = [i["rule_id"] for i in result["issues_found"]]
    assert "R007" in rule_ids
    assert result["manual_review_required"] is True


def test_code_validation_run_id_propagates_to_trace_refs():
    """run_id kwarg flows through to trace_refs.run_id."""
    result = _run_with_run_id(
        code_validation_run,
        '{"primary_diagnosis":{"code":"I50.9","confidence":0.9,"evidence":["x"]}}',
        run_id="test-run-12345",
    )
    assert result["trace_refs"]["run_id"] == "test-run-12345"


# ── Compliance Guardrail Agent ───────────────────────────────────────


def test_compliance_guardrail_passes_complete_case():
    """Clean coding set + procedure → PASS, drg_readiness True."""
    payload = json.dumps({
        "primary_diagnosis": {
            "code": "I50.9",
            "confidence": 0.95,
            "evidence": ["心衰证据"],
            "category": "primary",
        },
        "secondary_diagnoses": [],
        "procedures": [
            {"code": "33.2400", "confidence": 0.9, "evidence": ["手术记录"]}
        ],
    })
    result = _run(compliance_guardrail_run(payload))
    assert result["review_conclusion"] == "PASS"
    assert result["compliance_checks"]["primary_dx_present"] is True
    assert result["compliance_checks"]["no_upcoding_risk"] is True
    assert result["compliance_checks"]["drg_readiness"] is True
    assert result["reviewed_codes"] == [
        {
            "code": "I50.9",
            "code_system": "ICD-10-CN",
            "role": "primary_diagnosis",
        },
        {
            "code": "33.2400",
            "code_system": "ICD-9-CM-3",
            "role": "procedure",
        },
    ]
    assert "DRG 就绪" in result["drg_suggestion"]


def test_compliance_guardrail_reviewed_codes_are_exact_deduplicated_inputs():
    payload = json.dumps({
        "primary_diagnosis": {"code": " I50.9 "},
        "secondary_diagnoses": [
            {"code": "E11.9"},
            {"code": "e11.9"},
            {"code": ""},
        ],
        "procedures": [{"code": "33.24"}, {"code": "33.24"}],
    })

    result = _run(compliance_guardrail_run(payload))

    assert result["reviewed_codes"] == [
        {
            "code": "I50.9",
            "code_system": "ICD-10-CN",
            "role": "primary_diagnosis",
        },
        {
            "code": "E11.9",
            "code_system": "ICD-10-CN",
            "role": "secondary_diagnosis",
        },
        {
            "code": "33.24",
            "code_system": "ICD-9-CM-3",
            "role": "procedure",
        },
    ]


def test_compliance_guardrail_fires_cg001_when_no_primary():
    """Missing primary dx → CG-001 critical → FAIL."""
    result = _run(compliance_guardrail_run('{"procedures":[{"code":"33.24"}]}'))
    rule_ids = [i["rule_id"] for i in result["issues_found"]]
    assert "CG-001" in rule_ids
    assert result["compliance_checks"]["primary_dx_present"] is False
    assert result["review_conclusion"] == "FAIL"


def test_compliance_guardrail_fires_cg002_upcoding_risk():
    """Osteoporosis + vertebral fracture + primary M48.x → CG-002 high."""
    emr_text = (
        "患者骨质疏松伴椎体压缩骨折，行椎体成形术。"
        "primary: M48.5, procedure: 81.99"
    )
    result = _run(compliance_guardrail_run(emr_text))
    rule_ids = [i["rule_id"] for i in result["issues_found"]]
    assert "CG-002" in rule_ids
    assert result["compliance_checks"]["no_upcoding_risk"] is False


def test_compliance_guardrail_no_cg002_when_no_osteoporosis():
    """M48.x without osteoporosis keywords → CG-002 does NOT fire."""
    result = _run(compliance_guardrail_run(
        "椎体其他疾患。primary: M48.5, procedure: 81.99"
    ))
    rule_ids = [i["rule_id"] for i in result["issues_found"]]
    assert "CG-002" not in rule_ids
    assert result["compliance_checks"]["no_upcoding_risk"] is True


def test_compliance_guardrail_fires_cg003_procedure_without_dx():
    """Procedure present + no primary dx → CG-003 high."""
    result = _run(compliance_guardrail_run(
        '{"procedures":[{"code":"33.24"}], "encounter_text":"行搭桥术"}'
    ))
    rule_ids = [i["rule_id"] for i in result["issues_found"]]
    assert "CG-003" in rule_ids
    assert result["compliance_checks"]["procedure_dx_consistency"] is False


def test_compliance_guardrail_drg_suggestion_no_procedure():
    """No procedure + valid primary → drg_suggestion mentions 内科 DRG."""
    payload = json.dumps({
        "primary_diagnosis": {"code": "J44.1", "confidence": 0.9, "evidence": ["x"]},
        "secondary_diagnoses": [],
        "procedures": [],
    })
    result = _run(compliance_guardrail_run(payload))
    assert "内科" in result["drg_suggestion"]


# ── Note Completeness Agent ──────────────────────────────────────────


COMPLETE_EMR = """入院记录
主诉：腰部疼痛 3 天。
现病史：患者 3 天前无明显诱因出现腰部疼痛。
既往史：高血压 10 年。
体格检查：腰骶部压痛阳性。
辅助检查：X线示椎体压缩骨折。
诊断：1. 椎体压缩骨折 2. 骨质疏松
治疗经过：行椎体成形术。
手术记录：常规消毒铺巾，行椎体成形术。
"""


PARTIAL_EMR = """入院记录
主诉：腰部疼痛 3 天。
诊断：椎体压缩骨折
"""


def test_note_completeness_flags_structurally_present_but_incomplete_surgical_emr():
    """All 7+1 headings score 1.0, but bounded surgical gaps prevent PASS."""
    result = _run(note_completeness_run(COMPLETE_EMR))
    assert result["review_conclusion"] == "WARNING"
    assert result["completeness_score"] == 1.0
    assert set(result["missing_sections"]) == set()
    # Surgical case detected (手术 keyword)
    assert result["is_surgical_case"] is True
    assert "手术记录" in result["present_sections"]
    assert "主诉" in result["present_sections"]
    assert {item["section"] for item in result["incomplete_sections"]} == {
        "诊断",
        "治疗经过",
    }
    assert result["manual_review_required"] is True


def test_note_completeness_fails_on_missing_sections():
    """Partial EMR missing most sections → FAIL, low score."""
    result = _run(note_completeness_run(PARTIAL_EMR))
    assert result["review_conclusion"] == "FAIL"
    assert result["completeness_score"] < 0.5
    missing = set(result["missing_sections"])
    # Should be missing most of the 7 required (no surgical since no 手术 keyword)
    assert "现病史" in missing
    assert "既往史" in missing
    assert "体格检查" in missing
    assert "辅助检查" in missing
    assert "治疗经过" in missing
    # Not surgical — 手术记录 not required
    assert "手术记录" not in result["required_sections"]


def test_note_completeness_surgical_adds_operation_record_requirement():
    """Surgical headings can be complete while bounded content gaps require review."""
    text = """主诉：阑尾炎。
现病史：转移性右下腹痛。
既往史：无。
体格检查：右下腹压痛。
辅助检查：WBC 升高。
诊断：急性阑尾炎
治疗经过：行阑尾切除术。
手术记录：常规开腹阑尾切除。
"""
    result = _run(note_completeness_run(text))
    assert result["is_surgical_case"] is True
    assert "手术记录" in result["required_sections"]
    assert "手术记录" in result["present_sections"]
    assert result["review_conclusion"] == "WARNING"
    assert {item["section"] for item in result["incomplete_sections"]} == {
        "诊断",
        "治疗经过",
    }


def test_note_completeness_surgical_missing_operation_record():
    """Surgical case but no 手术记录 section → that section missing."""
    text = """主诉：阑尾炎。
现病史：转移性右下腹痛。
既往史：无。
体格检查：右下腹压痛。
辅助检查：WBC 升高。
诊断：急性阑尾炎
治疗经过：行阑尾切除术。
"""
    result = _run(note_completeness_run(text))
    assert result["is_surgical_case"] is True
    assert "手术记录" in result["missing_sections"]


def test_note_completeness_empty_text_returns_fail():
    """Empty input → all sections missing, score 0, FAIL."""
    result = _run(note_completeness_run(""))
    assert result["review_conclusion"] == "FAIL"
    assert result["completeness_score"] == 0.0
    assert len(result["missing_sections"]) == len(result["required_sections"])


def test_note_completeness_documentation_gaps_match_public_contract():
    """Each documentation gap uses the strict public item allowlist."""
    result = _run(note_completeness_run("主诉：腹痛。"))
    assert len(result["documentation_gaps"]) > 0
    for gap in result["documentation_gaps"]:
        assert gap["gap_type"] == "missing_section"
        assert gap["section"]
        assert set(gap) == {"gap_type", "description", "section"}


def test_note_completeness_heading_without_body_is_incomplete():
    result = _run(note_completeness_run(
        "主诉：\n现病史：腹痛三天。\n既往史：无。\n体格检查：腹部压痛。"
    ))

    assert "主诉" not in result["present_sections"]
    assert "主诉" not in result["missing_sections"]
    assert result["incomplete_sections"] == [{
        "section": "主诉",
        "deficit_note": "主诉章节存在标题但未记录有效内容",
    }]
    assert result["manual_review_required"] is True


def test_note_completeness_negated_surgery_history_does_not_require_op_note():
    result = _run(note_completeness_run(
        "主诉：头晕。\n现病史：头晕一天。\n既往史：否认手术史。"
    ))

    assert result["is_surgical_case"] is False
    assert "手术记录" not in result["required_sections"]


def test_note_completeness_run_id_propagates():
    """run_id kwarg flows to trace_refs.run_id."""
    result = _run_with_run_id(note_completeness_run, "主诉：x", run_id="nc-run-1")
    assert result["trace_refs"]["run_id"] == "nc-run-1"
    assert result["trace_refs"]["agent_ref"] == "icoder/note-completeness-agent@1.0.0"
