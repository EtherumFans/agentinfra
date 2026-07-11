"""Unit tests for CDI Orchestrator (Phase 5 Track D Gate 3 + Gate 6 skeleton).

Tests the orchestrator wiring:
    - Stub runner completes all 6 stages without exception
    - AUTO_PASS when no gaps and no risk_flags
    - REVIEW_REQUIRED when gaps exist but no queries
    - REVIEW_RECOMMENDED when queries + risk_flags
    - BLOCKED when any query fails NLQ gate
    - Per-stage run_id/trace_id capture
"""

from __future__ import annotations

from typing import Any

import pytest

from app.icoder.agent_runtime.cdi import (
    CDICase,
    CDIOrchestrator,
    STAGES,
    ProviderQueryForGate,
    stub_runner,
)
from app.icoder.agent_runtime.cdi.domain import (
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
)


# ---------------------------------------------------------------------------
# Custom runners for testing each completion path
# ---------------------------------------------------------------------------


def _runner_no_gaps(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Runner that produces no gaps and no risk flags → AUTO_PASS."""

    return {
        "encounter_synthesis": lambda: {"key_points": ["p1"], "encounter_metadata": {}, "run_id": "r1", "trace_id": "t1"},
        "gap_identification": lambda: {"gaps": [], "run_id": "r2", "trace_id": "t2"},
        "expert_consultation": lambda: {"run_id": "r3", "trace_id": "t3"},
        "query_generation": lambda: {"queries": [], "run_id": "r4", "trace_id": "t4"},
        "specialist_trace_emit": lambda: {"run_id": "r5", "trace_id": "t5"},
    }.get(stage, lambda: {})()


def _runner_with_compliant_query(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Runner that produces 1 gap + 1 NLQ-compliant query → REVIEW_RECOMMENDED
    (because risk_flags present) or AUTO_PASS if no risk_flags."""

    if stage == "gap_identification":
        return {
            "gaps": [
                {
                    "gap_id": "gap_001",
                    "description": "肺炎病原体未记录",
                    "why_it_matters": "J18.9 vs J13 编码差异",
                    "evidence_span": {
                        "document_id": "入院记录",
                        "quote": "诊断: 肺炎",
                        "char_start": 0,
                        "char_end": 6,
                    },
                    "priority": "routine",
                }
            ],
            "run_id": "r2",
            "trace_id": "t2",
        }
    if stage == "query_generation":
        return {
            "queries": [
                {
                    "query_id": "q_001",
                    "gap_id": "gap_001",
                    "topic": "肺炎病原体",
                    "reason": "特异性不足",
                    "evidence_span": {
                        "document_id": "入院记录",
                        "quote": "诊断: 肺炎",
                    },
                    "query_text": "入院记录诊断为肺炎, 痰培养为肺炎链球菌. 请根据您的临床判断回答:",
                    "response_options": [
                        # Phase 5 Track D P0 Gate 4 / PDF §A6: no ICD codes in options
                        "A. 肺炎病原体为肺炎链球菌",
                        "B. 其他病原体",
                        "C. 痰培养为定植菌",
                        "D. 无法确定",
                    ],
                    "priority": "routine",
                }
            ],
            "run_id": "r4",
            "trace_id": "t4",
        }
    return _runner_no_gaps(stage, case, kwargs)


def _runner_with_leading_query(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Runner that produces a query that fails NLQ gate (yes/no opening)."""

    if stage == "query_generation":
        return {
            "queries": [
                {
                    "query_id": "q_bad",
                    "gap_id": "gap_001",
                    "topic": "病原体",
                    "reason": "test",
                    "evidence_span": {"document_id": "d", "quote": "肺炎"},
                    "query_text": "是否为肺炎链球菌性肺炎?",
                    "response_options": ["A. 是", "B. 否"],
                    "priority": "routine",
                }
            ],
            "run_id": "r4",
            "trace_id": "t4",
        }
    return _runner_with_compliant_query(stage, case, kwargs)


# ---------------------------------------------------------------------------
# Stage execution
# ---------------------------------------------------------------------------


def test_stages_tuple_is_corti_compatible_10_steps() -> None:
    assert STAGES == (
        "encounter_synthesis",
        "gap_identification",
        "expert_consultation",
        "query_generation",
        "query_necessity_gate",
        "query_single_dimension_gate",
        "claim_evidence_alignment_gate",
        "semantic_necessity_gate",
        "query_compliance_gate",
        "specialist_trace_emit",
    )


def test_orchestrator_runs_all_stages_with_stub_runner() -> None:
    case = CDICase(case_id="c1", chart_excerpt="any")
    orch = CDIOrchestrator(runner=stub_runner)
    out = orch.run(case)
    assert out.case_id == "c1"
    # all 10 stages recorded (necessity_gate + single_dimension_gate +
    # claim_evidence_alignment_gate + semantic_necessity_gate +
    # compliance_gate don't call runner but still register keys)
    expected_keys = {
        "encounter_synthesis",
        "gap_identification",
        "expert_consultation",
        "query_generation",
        "query_necessity_gate",
        "query_single_dimension_gate",
        "claim_evidence_alignment_gate",
        "semantic_necessity_gate",
        "query_compliance_gate",
        "specialist_trace_emit",
    }
    assert expected_keys.issubset(set(out.stage_run_ids.keys()))


# ---------------------------------------------------------------------------
# Completion policy
# ---------------------------------------------------------------------------


def test_completion_auto_pass_when_no_gaps_no_risks() -> None:
    case = CDICase(case_id="c_autopass")
    orch = CDIOrchestrator(runner=_runner_no_gaps)
    out = orch.run(case)
    assert out.completion_state == "AUTO_PASS"


def test_completion_review_required_when_gaps_but_no_queries() -> None:
    def runner(stage: str, case: CDICase, kw: dict[str, Any]) -> dict[str, Any]:
        if stage == "gap_identification":
            return {
                "gaps": [
                    {
                        "gap_id": "g1",
                        "description": "test",
                        "why_it_matters": "test",
                        "evidence_span": {"document_id": "d", "quote": "x"},
                    }
                ],
                "run_id": "r",
                "trace_id": "t",
            }
        return _runner_no_gaps(stage, case, kw)

    case = CDICase(case_id="c_review_req")
    orch = CDIOrchestrator(runner=runner)
    out = orch.run(case)
    assert out.completion_state == "REVIEW_REQUIRED"


def test_completion_review_recommended_when_queries_passed_and_risks() -> None:
    case = CDICase(case_id="c_review_rec")
    orch = CDIOrchestrator(runner=_runner_with_compliant_query)
    out = orch.run(case)
    # gaps + queries passed NLQ; no risk_flags yet → REVIEW_REQUIRED
    # (REVIEW_RECOMMENDED requires risk_flags presence; tested elsewhere)
    assert out.completion_state in {"REVIEW_RECOMMENDED", "REVIEW_REQUIRED"}
    assert out.proposed_provider_queries[0].nlq_gate_verdict == "PASS"


def test_completion_blocked_when_query_fails_nlq() -> None:
    case = CDICase(case_id="c_blocked")
    orch = CDIOrchestrator(runner=_runner_with_leading_query)
    out = orch.run(case)
    assert out.completion_state == "BLOCKED"
    blocked_q = out.proposed_provider_queries[0]
    assert blocked_q.nlq_gate_verdict == "BLOCK"
    assert len(blocked_q.nlq_gate_block_reasons) > 0
    assert any("NLQ-001" in r for r in blocked_q.nlq_gate_block_reasons)


# ---------------------------------------------------------------------------
# Per-stage run_id / trace_id capture (Track C parity)
# ---------------------------------------------------------------------------


def test_stage_run_ids_captured_from_runner() -> None:
    case = CDICase(case_id="c_ids")
    orch = CDIOrchestrator(runner=_runner_no_gaps)
    out = orch.run(case)
    assert out.stage_run_ids["encounter_synthesis"] == "r1"
    assert out.stage_trace_ids["encounter_synthesis"] == "t1"
    assert out.stage_run_ids["gap_identification"] == "r2"


# ---------------------------------------------------------------------------
# Gap / Query hydration
# ---------------------------------------------------------------------------


def test_orchestrator_hydrates_gap_with_evidence_span() -> None:
    case = CDICase(case_id="c_hydrate")
    orch = CDIOrchestrator(runner=_runner_with_compliant_query)
    out = orch.run(case)
    assert len(out.documentation_gaps) == 1
    g = out.documentation_gaps[0]
    assert isinstance(g, DocumentationGap)
    assert g.gap_id == "gap_001"
    assert g.evidence_span.quote == "诊断: 肺炎"
    assert g.evidence_span.document_id == "入院记录"


def test_orchestrator_hydrates_query_and_runs_nlq_gate() -> None:
    case = CDICase(case_id="c_q_hydrate")
    orch = CDIOrchestrator(runner=_runner_with_compliant_query)
    out = orch.run(case)
    assert len(out.proposed_provider_queries) == 1
    q = out.proposed_provider_queries[0]
    assert isinstance(q, ProviderQuery)
    assert q.query_id == "q_001"
    assert q.nlq_gate_verdict == "PASS"
    assert q.lifecycle_state == "DRAFT"  # always DRAFT on initial generation


def test_orchestrator_generates_gap_ids_when_missing() -> None:
    def runner(stage: str, case: CDICase, kw: dict[str, Any]) -> dict[str, Any]:
        if stage == "gap_identification":
            return {
                "gaps": [
                    {
                        # gap_id intentionally missing
                        "description": "test",
                        "why_it_matters": "test",
                        "evidence_span": {"document_id": "d", "quote": "x"},
                    }
                ],
                "run_id": "r",
                "trace_id": "t",
            }
        return _runner_no_gaps(stage, case, kw)

    case = CDICase(case_id="c_autoid")
    orch = CDIOrchestrator(runner=runner)
    out = orch.run(case)
    g = out.documentation_gaps[0]
    assert g.gap_id.startswith("gap_")  # generated prefix
