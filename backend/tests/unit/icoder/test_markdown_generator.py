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
    assert "Medical Coding Agent Output" in md
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
