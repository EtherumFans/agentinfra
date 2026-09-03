"""Unit tests for CDI Clinician Response Workflow (Phase 5 Track D Gate 6).

Tests:
    - ClinicianResponseValue category classification
    - process_clinician_response drives VIEWED → RESPONDED → DOCUMENTATION_UPDATED
    - escape_hatch response escalates instead of marking chart updated
    - revalidate_gap handles 4 response categories
    - compute_document_diff produces correct hash + delta metadata
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.icoder.agent_runtime.cdi import (
    ClinicianResponseValue,
    DocumentationGap,
    EvidenceSpan,
    compute_document_diff,
    process_clinician_response,
    revalidate_gap,
)
from app.icoder.agent_runtime.cdi import ProviderQuery


# ---------------------------------------------------------------------------
# ClinicianResponseValue category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "selected_option,expected_category",
    [
        ("A. 肺炎病原体为肺炎链球菌 (J13)", "specific_clinical_answer"),
        ("B. 其他已知病原体, 请说明", "free_text_fallback"),
        ("C. 痰培养为定植菌", "colonization_or_non_pathological"),
        ("D. 无法确定", "escape_hatch"),
        ("E. 临床不支持", "escape_hatch"),
    ],
)
def test_clinician_response_value_category(
    selected_option: str, expected_category: str
) -> None:
    r = ClinicianResponseValue(selected_option=selected_option)
    assert r.category == expected_category


# ---------------------------------------------------------------------------
# process_clinician_response — happy path
# ---------------------------------------------------------------------------


def _make_query_in_viewed_state(query_id: str = "q1") -> ProviderQuery:
    return ProviderQuery(
        query_id=query_id,
        gap_id="g1",
        topic="病原体",
        reason="test",
        evidence_span=EvidenceSpan(document_id="d", quote="肺炎"),
        query_text="请回答病原体",
        response_options=["A", "B", "无法确定"],
        lifecycle_state="VIEWED",
    )


def test_process_clinician_response_specific_answer_advances_to_documentation_updated() -> None:
    query = _make_query_in_viewed_state()
    response = ClinicianResponseValue(
        selected_option="A. 肺炎病原体为肺炎链球菌 (J13)",
    )
    r1, r2 = process_clinician_response(query, response)
    assert r1.accepted is True  # VIEWED → RESPONDED
    assert r1.from_state == "VIEWED" and r1.to_state == "RESPONDED"
    assert r2 is not None and r2.accepted is True  # RESPONDED → DOCUMENTATION_UPDATED
    assert r2.from_state == "RESPONDED" and r2.to_state == "DOCUMENTATION_UPDATED"


def test_process_clinician_response_escape_hatch_escalates() -> None:
    """When clinician selects 'unable to determine', the query escalates
    rather than marking the chart updated — because no clarification
    means no documentation change."""

    query = _make_query_in_viewed_state()
    response = ClinicianResponseValue(selected_option="D. 无法确定")
    r1, r2 = process_clinician_response(query, response)
    assert r1.accepted is True  # VIEWED → RESPONDED
    assert r2 is not None and r2.accepted is True
    assert r2.to_state == "ESCALATED"  # NOT DOCUMENTATION_UPDATED


def test_process_clinician_response_colonization_advances_to_documentation_updated() -> None:
    """Colonization response is actionable — chart should be revised to
    reflect that the lab result is not clinically relevant."""

    query = _make_query_in_viewed_state()
    response = ClinicianResponseValue(
        selected_option="C. 痰培养为定植菌, 不作为病原体",
    )
    r1, r2 = process_clinician_response(query, response)
    assert r1.accepted is True
    assert r2 is not None and r2.accepted is True
    assert r2.to_state == "DOCUMENTATION_UPDATED"


def test_process_clinician_response_free_text_advances_to_documentation_updated() -> None:
    """Free-text response is treated as actionable (LLM validation
    happens later in revalidation)."""

    query = _make_query_in_viewed_state()
    response = ClinicianResponseValue(
        selected_option="B. 其他已知病原体: 假单胞菌",
    )
    r1, r2 = process_clinician_response(query, response)
    assert r1.accepted is True
    assert r2 is not None and r2.accepted is True
    assert r2.to_state == "DOCUMENTATION_UPDATED"


# ---------------------------------------------------------------------------
# revalidate_gap
# ---------------------------------------------------------------------------


def test_revalidate_gap_specific_answer_closes_gap() -> None:
    gap = DocumentationGap(
        gap_id="g1",
        description="肺炎病原体未记录",
        why_it_matters="影响 J18.9 vs J13",
        evidence_span=EvidenceSpan(document_id="d", quote="肺炎"),
        minimal_clarification_needed="病原体",
    )
    response = ClinicianResponseValue(
        selected_option="A. 肺炎病原体为肺炎链球菌",
    )
    result = revalidate_gap(gap, response, revalidation_run_id="rr1")
    assert result.outcome == "GAP_CLOSED"
    assert "g1" in result.closed_gap_ids


def test_revalidate_gap_escape_hatch_rejected() -> None:
    gap = DocumentationGap(
        gap_id="g1",
        description="test",
        why_it_matters="test",
        evidence_span=EvidenceSpan(document_id="d", quote="x"),
    )
    response = ClinicianResponseValue(selected_option="D. 无法确定")
    result = revalidate_gap(gap, response)
    assert result.outcome == "RESPONSE_REJECTED"
    assert result.closed_gap_ids == []


def test_revalidate_gap_free_text_partial_close() -> None:
    gap = DocumentationGap(
        gap_id="g1",
        description="test",
        why_it_matters="test",
        evidence_span=EvidenceSpan(document_id="d", quote="x"),
    )
    response = ClinicianResponseValue(
        selected_option="B. 其他病原体, 请说明: 假单胞菌",
    )
    result = revalidate_gap(gap, response)
    assert result.outcome == "GAP_PARTIALLY_CLOSED"


def test_revalidate_gap_colonization_keeps_gap_open() -> None:
    gap = DocumentationGap(
        gap_id="g1",
        description="test",
        why_it_matters="test",
        evidence_span=EvidenceSpan(document_id="d", quote="x"),
    )
    response = ClinicianResponseValue(selected_option="C. 痰培养为定植菌")
    result = revalidate_gap(gap, response)
    assert result.outcome == "GAP_STILL_OPEN"


# ---------------------------------------------------------------------------
# compute_document_diff
# ---------------------------------------------------------------------------


def test_compute_document_diff_unchanged_returns_unchanged_summary() -> None:
    text = "患者主诉: 咳嗽 3 天。"
    diff = compute_document_diff("d1", text, text)
    assert diff.content_hash_before == diff.content_hash_after
    assert diff.diff_summary.get("unchanged") is True


def test_compute_document_diff_changed_records_delta() -> None:
    before = "诊断: 肺炎"
    after = "诊断: 肺炎链球菌性肺炎"
    diff = compute_document_diff("d1", before, after)
    assert diff.content_hash_before != diff.content_hash_after
    assert diff.diff_summary["delta_chars"] == len(after) - len(before)
    assert diff.diff_summary["delta_chars"] > 0
    assert diff.diff_summary["before_length"] == len(before)
    assert diff.diff_summary["after_length"] == len(after)


def test_compute_document_diff_hash_is_sha256_hex() -> None:
    diff = compute_document_diff("d", "a", "b")
    # SHA-256 hex = 64 chars
    assert len(diff.content_hash_before) == 64
    assert len(diff.content_hash_after) == 64
    assert all(c in "0123456789abcdef" for c in diff.content_hash_before)


# ---------------------------------------------------------------------------
# Integration: response → revalidate → diff
# ---------------------------------------------------------------------------


def test_integration_response_to_diff_charts_revised_correctly() -> None:
    """End-to-end Gate 6 scenario:
        1. Clinician responds with specific answer
        2. process_clinician_response drives to DOCUMENTATION_UPDATED
        3. revalidate_gap confirms closure
        4. compute_document_diff captures the before/after chart state
    """

    query = _make_query_in_viewed_state()
    response = ClinicianResponseValue(
        selected_option="A. 肺炎病原体为肺炎链球菌 (J13)",
    )

    # 1. Process response
    r1, r2 = process_clinician_response(query, response)
    assert r1.accepted and r2 is not None and r2.accepted
    assert r2.to_state == "DOCUMENTATION_UPDATED"

    # 2. Revalidate
    gap = DocumentationGap(
        gap_id="g1",
        description="肺炎病原体未记录",
        why_it_matters="影响 J18.9 vs J13",
        evidence_span=EvidenceSpan(document_id="入院记录", quote="诊断: 肺炎"),
        minimal_clarification_needed="病原体",
    )
    revalidation = revalidate_gap(gap, response, revalidation_run_id="rr_e2e")
    assert revalidation.outcome == "GAP_CLOSED"

    # 3. Diff
    before = "入院记录: 诊断: 肺炎。"
    after = "入院记录: 诊断: 肺炎链球菌性肺炎。"
    diff = compute_document_diff("入院记录", before, after)
    assert diff.content_hash_before != diff.content_hash_after
    assert diff.diff_summary["delta_chars"] > 0
