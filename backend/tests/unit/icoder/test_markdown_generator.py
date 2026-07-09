"""Phase 3-B2 Loop 3 — Markdown generator unit tests (Gap 4.3).

Verifies the 6-section template completeness per Loop 3 acceptance:
"模板表头完整性" — every section's table header is always rendered,
even when the input is empty or partial.
"""
from __future__ import annotations

import os
import sys

# Allow running from repo root or backend/
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.icoder.markdown_generator import generate_markdown  # noqa: E402

# 6 sections that must always appear, by header marker.
EXPECTED_SECTION_HEADERS = [
    "## 1. Encounter Summary",
    "## 2. Documentation Analysis",
    "## 3. Code Assignment",
    "## 4. Documentation Gaps & Uncodable Items",
    "## 5. Validation Summary",
    "## 6. Human Review & Trace Refs",
]

# Required table headers per section (subset that must always be present).
EXPECTED_TABLE_HEADERS = [
    # Section 1
    "Field", "Value",
    # Section 2 (4 buckets)
    "Evidence Bucket", "Count", "Sample Text",
    # Section 3
    "Code", "Description", "Confidence", "Category", "Evidence",
    # Section 4
    "Gap Type", "Item Type",
    # Section 5
    "Passed", "Issues", "Manual Review Required",
    # Section 6
    "Review Conclusion", "Review Required", "Run ID",
]


def test_empty_v2_dict_still_renders_all_6_sections():
    """An empty v2 dict must still produce all 6 section headers + tables."""
    md = generate_markdown({})
    for header in EXPECTED_SECTION_HEADERS:
        assert header in md, f"missing section header: {header!r}"


def test_all_required_table_headers_present():
    """Every required table header must appear in the generated markdown,
    regardless of input data (template completeness)."""
    md = generate_markdown({})
    for header in EXPECTED_TABLE_HEADERS:
        assert header in md, f"missing table header: {header!r}"


def test_markdown_has_table_separators():
    """Each section must have a Markdown table separator (---) row."""
    md = generate_markdown({})
    # At least 6 separator rows (one per section table minimum).
    sep_count = md.count("| --- |")
    assert sep_count >= 6, f"expected ≥6 table separators, got {sep_count}"


def test_primary_diagnosis_row_rendered():
    """When code_assignment.primary_diagnosis is populated, it must appear
    in the rendered markdown."""
    v2 = {
        "code_assignment": {
            "primary_diagnosis": {
                "code": "I50.900",
                "description": "心功能不全",
                "confidence": 0.92,
                "category": "principal",
                "evidence": [{"text": "心功能不全"}],
            },
            "secondary_diagnoses": [],
            "procedures": [],
        },
    }
    md = generate_markdown(v2)
    assert "I50.900" in md, "primary diagnosis code must appear in markdown"
    assert "心功能不全" in md, "primary diagnosis description must appear"


def test_secondary_diagnoses_and_procedures_rows_rendered():
    """Multiple secondary diagnoses + procedures must each get a row."""
    v2 = {
        "code_assignment": {
            "primary_diagnosis": {"code": "I21.0"},
            "secondary_diagnoses": [
                {"code": "I10", "description": "高血压"},
                {"code": "E11", "description": "糖尿病"},
            ],
            "procedures": [
                {"code": "00.66", "description": "PCI"},
            ],
        },
    }
    md = generate_markdown(v2)
    assert "I10" in md
    assert "I21.0" in md
    assert "00.66" in md
    assert "PCI" in md


def test_evidence_buckets_section_lists_all_4():
    """Section 2 must list all 4 evidence buckets even when empty."""
    md = generate_markdown({})
    assert "Diagnosis Evidence" in md
    assert "Procedure Evidence" in md
    assert "Negated Findings" in md
    assert "Historical Conditions" in md


def test_validation_summary_issues_section_rendered_when_present():
    """When validation_summary.issues_found is non-empty, the Issues Found
    sub-table must render with one row per issue."""
    v2 = {
        "validation_summary": {
            "passed": False,
            "issues_found": [
                {"code": "MC-R-M80-001", "severity": "high",
                 "message": "Primary dx confidence below 0.85", "category": "safety"},
                {"code": "R005", "severity": "medium",
                 "message": "Procedure evidence missing", "category": "evidence"},
            ],
            "manual_review_required": True,
            "rule_set": "MedCodERRetrievalRuleSet",
            "fired_rules": ["MC-R-M80-001", "R005"],
        },
    }
    md = generate_markdown(v2)
    assert "### Issues Found" in md
    assert "MC-R-M80-001" in md
    assert "R005" in md


def test_human_review_focus_subsection_when_present():
    """When human_review.review_focus is non-empty, the Review Focus
    sub-table must render."""
    v2 = {
        "human_review": {
            "review_conclusion": "WARNING",
            "review_required": True,
            "review_focus": [
                "Primary dx confidence is 0.82 (below 0.85 threshold)",
                "Procedure evidence insufficient for 00.66",
            ],
            "notes": "",
        },
    }
    md = generate_markdown(v2)
    assert "### Review Focus" in md
    assert "Primary dx confidence" in md


def test_pipe_in_value_escaped():
    """A pipe character in a value must be escaped so it doesn't break the
    Markdown table layout."""
    v2 = {
        "encounter_summary": {
            "chief_complaint": "胸痛 | 心悸",
        },
    }
    md = generate_markdown(v2)
    # The pipe must be escaped, not literal.
    assert "胸痛 \\| 心悸" in md, f"pipe not escaped in: {md!r}"


def test_string_input_returns_graceful_fallback():
    """If the v2 data is not a dict (degraded path), return a top-level
    'no output' message rather than crashing."""
    md = generate_markdown("not a dict")  # type: ignore[arg-type]
    assert "医学编码智能体输出" in md
    assert "No structured output available" in md


def test_degraded_partial_v2_dict():
    """A partial v2 dict (some fields missing) must still render all 6
    sections with '—' placeholders, not crash."""
    v2 = {
        "code_assignment": {
            "primary_diagnosis": {"code": "I50.900"},
            # secondary_diagnoses + procedures missing entirely
        },
        # All other sections missing
    }
    md = generate_markdown(v2)
    # All 6 section headers still present
    for header in EXPECTED_SECTION_HEADERS:
        assert header in md
    # Primary diagnosis row rendered
    assert "I50.900" in md


def test_round_trip_does_not_crash_on_real_v2_dict():
    """Run generate_markdown against a full MedicalCodingAgentOutputV2
    dict (built via from_legacy_v1) to catch any shape-mismatch issues
    that unit-shape tests might miss."""
    try:
        from official_agents.medical_coding.schema import (
            MedicalCodingOutputSchema,
            MedicalCodingAgentOutputV2,
        )
    except Exception:
        # Schema module unavailable — skip this test.
        import pytest
        pytest.skip("medical_coding.schema not importable")

    v1 = MedicalCodingOutputSchema.mock_result()
    v2 = MedicalCodingAgentOutputV2.from_legacy_v1(v1, run_id="run-test-1")
    v2_dict = v2.to_dict()
    md = generate_markdown(v2_dict)
    # Should contain all 6 sections
    for header in EXPECTED_SECTION_HEADERS:
        assert header in md
    # And the run_id should appear
    assert "run-test-1" in md


# ── Phase 3-D2 Task 4 — per-agent markdown generators ──────────────


def test_code_validation_markdown_has_5_sections():
    """Code Validation markdown must render all 5 sections per spec."""
    from app.icoder.markdown_generator import generate_code_validation_markdown
    sample = {
        "review_conclusion": "WARNING",
        "issues_found": [
            {"rule_id": "R004", "severity": "high", "code": "I50.9",
             "message": "low confidence", "suggestion": "请补充证据"},
        ],
        "manual_review_required": True,
        "rule_set": "medical_coding",
        "fired_rules": ["R001", "R004", "MC-R-M80-001"],
        "trace_refs": {"run_id": "cv-1", "agent_ref": "icoder/code-validation-agent@1.0.0"},
    }
    md = generate_code_validation_markdown(sample)
    expected_sections = [
        "## 1. Review Conclusion",
        "## 2. Fired Rules",
        "## 3. Issue Codes",
        "## 4. Modification Suggestions",
        "## 5. Manual Review Advice",
    ]
    for s in expected_sections:
        assert s in md, f"missing section: {s}"
    # Should surface fired rules
    assert "R001" in md
    assert "MC-R-M80-001" in md
    # Should surface issue code + suggestion
    assert "R004" in md
    assert "请补充证据" in md
    # Manual review advice should fire (manual_review_required=True)
    assert "人工复核" in md
    # Run ID footer
    assert "cv-1" in md


def test_compliance_guardrail_markdown_has_5_sections():
    """Compliance Guardrail markdown must render all 5 sections per spec."""
    from app.icoder.markdown_generator import generate_compliance_guardrail_markdown
    sample = {
        "review_conclusion": "WARNING",
        "issues_found": [
            {"rule_id": "CG-001", "severity": "high", "code": "I50.9",
             "message": "DRG 跳跃风险"},
            {"rule_id": "CG-002", "severity": "medium", "code": "I10",
             "message": "次要诊断影响 DIP 分值"},
        ],
        "manual_review_required": True,
        "drg_suggestion": "建议核查主要诊断编码",
        "compliance_checks": [
            {"check_id": "CG-001", "passed": False, "severity": "high", "detail": "..."},
        ],
        "rule_set": "medical_coding",
        "fired_rules": ["CG-001", "CG-002"],
        "trace_refs": {"run_id": "cg-1", "agent_ref": "icoder/compliance-guardrail-agent@1.0.0"},
    }
    md = generate_compliance_guardrail_markdown(sample)
    expected_sections = [
        "## 1. Risk Conclusion",
        "## 2. DRG/DIP Sensitive Items",
        "## 3. Compliance Checks",
        "## 4. Risk Level",
        "## 5. Audit Advice",
    ]
    for s in expected_sections:
        assert s in md, f"missing section: {s}"
    # Should surface DRG/DIP sensitive items
    assert "CG-001" in md
    assert "DRG 跳跃风险" in md
    # Should surface risk level (WARNING → MEDIUM)
    assert "MEDIUM" in md
    # Audit advice should fire (manual_review_required=True)
    assert "审计" in md
    # Run ID footer
    assert "cg-1" in md


def test_note_completeness_markdown_has_5_sections():
    """Note Completeness markdown must render all 5 sections per spec."""
    from app.icoder.markdown_generator import generate_note_completeness_markdown
    sample = {
        "review_conclusion": "WARNING",
        "completeness_score": 0.6,
        "missing_sections": ["主诉", "查体"],
        "present_sections": ["现病史", "诊断"],
        "documentation_gaps": [
            {"section": "主诉", "gap_type": "missing_section",
             "suggestion": "请补充 主诉 章节"},
        ],
        "manual_review_required": True,
        "is_surgical_case": False,
        "trace_refs": {"run_id": "nc-1", "agent_ref": "icoder/note-completeness-agent@1.0.0"},
    }
    md = generate_note_completeness_markdown(sample)
    expected_sections = [
        "## 1. Completeness Score",
        "## 2. Missing Sections",
        "## 3. Present Sections",
        "## 4. Supplement Suggestions",
        "## 5. Coding/DRG/DIP Impact",
    ]
    for s in expected_sections:
        assert s in md, f"missing section: {s}"
    # Should surface score as percentage
    assert "60.0%" in md
    # Should surface missing sections
    assert "主诉" in md
    assert "查体" in md
    # Should surface present sections
    assert "现病史" in md
    # Coding impact should fire (missing sections present)
    assert "DRG" in md
    assert "DIP" in md
    # Run ID footer
    assert "nc-1" in md


def test_generate_markdown_for_dispatches_by_agent_id():
    """generate_markdown_for() dispatches to the right per-agent generator."""
    from app.icoder.markdown_generator import generate_markdown_for
    # Code Validation
    md_cv = generate_markdown_for("code-validation-agent", {"review_conclusion": "PASS"})
    assert "编码校验智能体输出" in md_cv
    # Compliance Guardrail
    md_cg = generate_markdown_for("compliance-guardrail-agent", {"review_conclusion": "PASS"})
    assert "合规护栏智能体输出" in md_cg
    # Note Completeness
    md_nc = generate_markdown_for("note-completeness-agent", {"completeness_score": 1.0})
    assert "病历完整性智能体输出" in md_nc
    # Unknown agent_id → fallback
    md_unknown = generate_markdown_for("mystery-agent", {"foo": "bar"})
    assert "Agent Output" in md_unknown
    assert "foo" in md_unknown  # JSON dump fallback
