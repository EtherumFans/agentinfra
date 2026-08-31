"""Unit tests for CDI Orchestrator (Phase 5 Track D Gate 3 + Gate 6 skeleton).

Tests the orchestrator wiring:
    - Stub runner completes all 6 stages without exception
    - AUTO_PASS when no gaps and no risk_flags
    - REVIEW_REQUIRED when gaps exist but no queries
    - REVIEW_RECOMMENDED when queries + risk_flags
    - NLQ-blocked drafts are withheld into the rewrite audit queue
    - Per-stage run_id/trace_id capture
"""

from __future__ import annotations

import asyncio
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
    RiskFlag,
    SpecialistTraceEntry,
)
from app.icoder.agent_runtime.cdi.necessity_semantic import (
    SemanticNecessityResult,
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


def test_encounter_synthesis_withholds_key_point_with_ungrounded_quantity() -> None:
    case = CDICase(case_id="quantity-summary", chart_excerpt="诊断：肺炎。")

    def runner(stage: str, _case: CDICase, _kwargs: dict[str, Any]):
        assert stage == "encounter_synthesis"
        return {
            "key_points": ["诊断：肺炎", "血压降至52 mmHg"],
            "encounter_metadata": {},
        }

    CDIOrchestrator(runner=runner)._stage_encounter_synthesis(case)

    assert case.encounter_summary is not None
    assert case.encounter_summary.key_points == ["诊断：肺炎"]
    assert case.stage_run_ids["encounter_synthesis::ungrounded_removed"] == "1"


def test_gap_identification_withholds_non_verbatim_evidence() -> None:
    case = CDICase(case_id="invalid-gap-anchor", chart_excerpt="诊断：肺炎。")

    def runner(stage: str, _case: CDICase, _kwargs: dict[str, Any]):
        assert stage == "gap_identification"
        return {
            "gaps": [{
                "gap_id": "gap-1",
                "description": "严重程度未记录",
                "why_it_matters": "影响编码",
                "evidence_span": {"quote": "病历明确重症肺炎"},
            }],
        }

    CDIOrchestrator(runner=runner)._stage_gap_identification(case)

    assert case.documentation_gaps == []
    assert "withheld=1" in case.stage_run_ids["gap_identification_risk_flags"]


def test_specialist_trace_redacts_chart_absent_quantity() -> None:
    case = CDICase(case_id="specialist-quantity", chart_excerpt="诊断：糖尿病。")
    case.specialist_trace = [SpecialistTraceEntry(
        expert_id="coding-expert",
        consulted=True,
        rationale="建议仅在糖化血红蛋白超过7.2%时采用该判断",
    )]

    CDIOrchestrator(runner=lambda *_args: {})._stage_specialist_trace_emit(case)

    assert "7.2%" not in case.specialist_trace[0].rationale
    assert "病历未提供的定量值" in case.specialist_trace[0].rationale


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


def test_stages_tuple_is_corti_compatible_11_steps() -> None:
    assert STAGES == (
        "encounter_synthesis",
        "gap_identification",
        "expert_consultation",
        "query_generation",
        "query_eligibility_gate",         # Phase 5 Track H3.5
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
    query_result = _runner_with_compliant_query(
        "query_generation", CDICase(case_id="fixture"), {}
    )
    evidence = query_result["queries"][0]["evidence_span"]["quote"]
    case = CDICase(case_id="c_review_rec", chart_excerpt=evidence)
    orch = CDIOrchestrator(runner=_runner_with_compliant_query)
    out = orch.run(case)
    # gaps + queries passed NLQ; no risk_flags yet → REVIEW_REQUIRED
    # (REVIEW_RECOMMENDED requires risk_flags presence; tested elsewhere)
    assert out.completion_state in {"REVIEW_RECOMMENDED", "REVIEW_REQUIRED"}
    assert out.proposed_provider_queries[0].nlq_gate_verdict == "PASS"


def test_nlq_blocked_query_is_withheld_for_rewrite() -> None:
    query_result = _runner_with_leading_query(
        "query_generation", CDICase(case_id="fixture"), {}
    )
    evidence = query_result["queries"][0]["evidence_span"]["quote"]
    case = CDICase(
        case_id="c_blocked",
        chart_excerpt=f"诊断: {evidence}",
    )
    orch = CDIOrchestrator(runner=_runner_with_leading_query)
    out = orch.run(case)
    assert out.completion_state == "REVIEW_REQUIRED"
    assert out.proposed_provider_queries == []
    assert len(out.query_rewrite_queue) == 1
    blocked = out.query_rewrite_queue[0]
    assert blocked["status"] == "NEEDS_NON_LEADING_REWRITE"
    assert any("NLQ-001" in reason for reason in blocked["gate_reasons"])


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
    query_result = _runner_with_compliant_query(
        "query_generation", CDICase(case_id="fixture"), {}
    )
    evidence = query_result["queries"][0]["evidence_span"]["quote"]
    case = CDICase(case_id="c_q_hydrate", chart_excerpt=evidence)
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


def test_orchestrator_records_content_free_stage_durations() -> None:
    case = CDICase(case_id="c-stage-timing")

    CDIOrchestrator(runner=_runner_no_gaps).run(
        case,
        stages=("encounter_synthesis", "gap_identification"),
    )

    assert set(case.stage_duration_ms) == {
        "encounter_synthesis",
        "gap_identification",
    }
    assert all(
        isinstance(duration, int) and duration >= 0
        for duration in case.stage_duration_ms.values()
    )


def test_gate_internal_llm_calls_are_accounted_without_clinical_content() -> None:
    class FakeLLM:
        provider = "deepseek"
        model = "deepseek-chat"

        async def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "content": '{"claims": [], "verdict": "PASS"}',
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 3,
                    "total_tokens": 14,
                },
            }

    query = ProviderQuery(
        query_id="q-gate-accounting",
        gap_id="g1",
        topic="severity",
        reason="test",
        evidence_span=EvidenceSpan(document_id="d", quote="documented fact"),
        query_text="Please clarify severity.",
    )
    case = CDICase(
        case_id="c-gate-accounting",
        chart_excerpt="documented fact",
        proposed_provider_queries=[query],
    )
    orchestrator = CDIOrchestrator(runner=stub_runner, llm=FakeLLM())

    orchestrator._stage_claim_evidence_alignment_gate(case)
    orchestrator._stage_semantic_necessity_gate(case)

    assert [trace.stage for trace in case.safety_gate_model_traces] == [
        "claim_evidence_alignment_gate",
        "semantic_necessity_gate",
    ]
    for trace in case.safety_gate_model_traces:
        assert trace.provider == "deepseek"
        assert trace.model == "deepseek-chat"
        assert trace.prompt_tokens == 11
        assert trace.completion_tokens == 3
        assert trace.total_tokens == 14
        assert trace.latency_ms >= 0
        assert trace.degraded is False
        assert not hasattr(trace, "prompt")
        assert not hasattr(trace, "completion")


@pytest.mark.parametrize(
    ("configured_limit", "expected_max_active"),
    [(3, 3), (99, 4), (0, 1)],
)
def test_per_query_gate_calls_use_bounded_concurrency_and_preserve_order(
    monkeypatch, configured_limit: int, expected_max_active: int,
) -> None:
    from app.config import settings
    from app.icoder.agent_runtime.cdi import claim_evidence_gate

    active = 0
    max_active = 0

    async def _extract(query, *, chart, llm):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return ([query.query_id], [])

    monkeypatch.setattr(
        settings,
        "ICODER_CDI_GATE_MAX_CONCURRENCY",
        configured_limit,
    )
    monkeypatch.setattr(claim_evidence_gate, "extract_claims", _extract)
    queries = [
        ProviderQuery(
            query_id=f"q-{index}",
            gap_id="g1",
            topic="severity",
            reason="test",
            evidence_span=EvidenceSpan(document_id="d", quote="fact"),
            query_text="clarify",
        )
        for index in range(5)
    ]

    results = asyncio.run(CDIOrchestrator._extract_claims_bulk(
        queries,
        "fact",
        object(),
    ))

    assert max_active == expected_max_active
    assert [claims[0] for claims, _ in results] == [
        query.query_id for query in queries
    ]


def test_semantic_necessity_block_is_preserved_in_audit_queue(monkeypatch) -> None:
    query = ProviderQuery(
        query_id="q_semantic_block",
        gap_id="g1",
        topic="unsupported diagnosis",
        reason="test",
        evidence_span=EvidenceSpan(document_id="d", quote="documented symptom"),
        query_text="Please provide a new unsupported diagnosis.",
    )
    case = CDICase(
        case_id="c_semantic_block",
        chart_excerpt="documented symptom",
        proposed_provider_queries=[query],
    )
    orchestrator = CDIOrchestrator(runner=stub_runner)

    async def _blocked(*args: Any, **kwargs: Any) -> list[SemanticNecessityResult]:
        return [SemanticNecessityResult(
            verdict="BLOCK",
            reason_codes=["POSSIBLE_DIAGNOSIS_INVENTION"],
        )]

    monkeypatch.setattr(orchestrator, "_review_necessity_bulk", _blocked)
    orchestrator._stage_semantic_necessity_gate(case)

    assert case.proposed_provider_queries == []
    assert len(case.query_rewrite_queue) == 1
    rejected = case.query_rewrite_queue[0]
    assert rejected["query_id"] == "q_semantic_block"
    assert rejected["status"] == "REJECTED_BY_SEMANTIC_NECESSITY"
    assert rejected["gate_reasons"] == ["POSSIBLE_DIAGNOSIS_INVENTION"]


def test_semantic_block_cannot_silently_drop_a_real_contradiction(monkeypatch) -> None:
    gap = DocumentationGap(
        gap_id="g-conflict",
        gap_type="severity",
        description="入院、病程和出院诊断的严重程度不一致",
        why_it_matters="冲突会影响最终编码",
        evidence_span=EvidenceSpan(document_id="d", quote="重度/轻度/中度"),
    )
    query = ProviderQuery(
        query_id="q-conflict",
        gap_id=gap.gap_id,
        topic="COPD急性加重严重程度",
        reason="严重程度冲突",
        evidence_span=gap.evidence_span,
        query_text="请明确本次COPD急性加重的最终严重程度。",
    )
    case = CDICase(
        case_id="c-conflict",
        chart_excerpt="入院重度，病程轻度，出院中度。",
        documentation_gaps=[gap],
        risk_flags=[RiskFlag(category="contradiction", description="严重程度冲突")],
        proposed_provider_queries=[query],
    )
    orchestrator = CDIOrchestrator(runner=stub_runner)

    async def _blocked(*args: Any, **kwargs: Any) -> list[SemanticNecessityResult]:
        return [SemanticNecessityResult(
            verdict="BLOCK",
            reason_codes=["BEYOND_MINIMAL_DOCUMENTATION_NEED"],
        )]

    monkeypatch.setattr(orchestrator, "_review_necessity_bulk", _blocked)
    orchestrator._stage_semantic_necessity_gate(case)

    assert case.proposed_provider_queries == [query]
    assert query.semantic_necessity_verdict == "REVIEW_REQUIRED"
    assert "CONTRADICTION_REQUIRES_PROVIDER_REVIEW" in query.semantic_necessity_reason_codes
    assert case.query_rewrite_queue == []


def test_semantic_gate_degradation_is_structured_on_case(monkeypatch) -> None:
    query = ProviderQuery(
        query_id="q-degraded",
        gap_id="g1",
        topic="severity",
        reason="test",
        evidence_span=EvidenceSpan(document_id="d", quote="documented fact"),
        query_text="Please clarify severity.",
    )
    case = CDICase(
        case_id="c-semantic-degraded",
        chart_excerpt="documented fact",
        proposed_provider_queries=[query],
    )
    orchestrator = CDIOrchestrator(runner=stub_runner)

    async def _degraded(*args: Any, **kwargs: Any) -> list[SemanticNecessityResult]:
        return [SemanticNecessityResult(
            verdict="DEGRADED",
            degraded=True,
            error_reason="provider unavailable",
        )]

    monkeypatch.setattr(orchestrator, "_review_necessity_bulk", _degraded)
    orchestrator._stage_semantic_necessity_gate(case)

    assert case.proposed_provider_queries == [query]
    assert case.degraded_safety_gates == {
        "semantic_necessity_gate": "degraded_queries=1",
    }


def test_claim_evidence_gate_degradation_is_structured_on_case(
    monkeypatch,
) -> None:
    query = ProviderQuery(
        query_id="q-claim-degraded",
        gap_id="g1",
        topic="severity",
        reason="test",
        evidence_span=EvidenceSpan(document_id="d", quote="documented fact"),
        query_text="Please clarify severity.",
    )
    case = CDICase(
        case_id="c-claim-degraded",
        chart_excerpt="documented fact",
        proposed_provider_queries=[query],
    )
    orchestrator = CDIOrchestrator(runner=stub_runner)

    async def _no_claims(*args: Any, **kwargs: Any) -> list[tuple[list, list]]:
        return [([], [])]

    monkeypatch.setattr(orchestrator, "_extract_claims_bulk", _no_claims)
    orchestrator._stage_claim_evidence_alignment_gate(case)

    assert case.proposed_provider_queries == [query]
    assert case.degraded_safety_gates == {
        "claim_evidence_alignment_gate": "degraded_queries=1",
    }
    assert "degraded=1" in case.stage_run_ids["claim_evidence_alignment_gate"]


def test_compliance_gate_bounds_options_and_rechecks_all_rules() -> None:
    query = ProviderQuery(
        query_id="q-options", gap_id="g1", topic="感染源", reason="gap",
        evidence_span=EvidenceSpan(document_id="d", quote="脓毒症"),
        query_text="请明确该患者脓毒症的感染源。",
        response_options=["A. 肺部", "B. 泌尿系", "C. 腹腔", "D. 皮肤", "E. 其他", "F. 无法确定"],
    )
    case = CDICase(case_id="c-options", chart_excerpt="脓毒症", proposed_provider_queries=[query])
    CDIOrchestrator(runner=stub_runner)._stage_query_compliance_gate(case)
    assert case.proposed_provider_queries == [query]
    assert len(query.response_options) == 5
    assert any("无法确定" in option for option in query.response_options)
    assert case.query_rewrite_queue[0]["rewrite_kind"] == "BOUND_RESPONSE_OPTIONS"


def test_compliance_gate_removes_only_redundant_yes_no_tail() -> None:
    query = ProviderQuery(
        query_id="q-tail", gap_id="g1", topic="病因", reason="gap",
        evidence_span=EvidenceSpan(document_id="d", quote="胆总管直径9mm"),
        query_text="胆总管扩张的病因是什么？是否与结石相关？",
        response_options=["A. 结石", "B. 炎症", "C. 其他", "D. 无法确定"],
    )
    case = CDICase(case_id="c-tail", chart_excerpt="胆总管直径9mm", proposed_provider_queries=[query])
    CDIOrchestrator(runner=stub_runner)._stage_query_compliance_gate(case)
    assert case.proposed_provider_queries == [query]
    assert query.query_text == "胆总管扩张的病因是什么？"
    assert case.query_rewrite_queue[0]["rewrite_kind"] == "REMOVE_REDUNDANT_YES_NO_TAIL"


def test_compliance_gate_keeps_pure_yes_no_query_blocked() -> None:
    query = ProviderQuery(
        query_id="q-leading", gap_id="g1", topic="病因", reason="gap",
        evidence_span=EvidenceSpan(document_id="d", quote="胆总管直径9mm"),
        query_text="是否为胆总管结石？",
        response_options=["A. 是", "B. 否", "C. 其他", "D. 无法确定"],
    )
    case = CDICase(case_id="c-leading", chart_excerpt="胆总管直径9mm", proposed_provider_queries=[query])
    CDIOrchestrator(runner=stub_runner)._stage_query_compliance_gate(case)
    assert case.proposed_provider_queries == []
    assert case.query_rewrite_queue[0]["status"] == "NEEDS_NON_LEADING_REWRITE"


def test_necessity_focus_keeps_one_query_for_one_symptom_evidence_span() -> None:
    evidence = EvidenceSpan(document_id="d", quote="间断胸闷")
    queries = [
        ProviderQuery(
            query_id="q-features", gap_id="g1", topic="胸闷症状特征", reason="gap",
            evidence_span=evidence, query_text="请明确胸闷的症状特征。",
        ),
        ProviderQuery(
            query_id="q-type", gap_id="g2", topic="胸闷性质", reason="gap",
            evidence_span=evidence, query_text="请明确胸闷的性质。",
        ),
    ]
    case = CDICase(
        case_id="c-symptom-focus",
        chart_excerpt="间断胸闷。查体正常。建议随访。",
        documentation_gaps=[
            DocumentationGap(gap_id="g1", description="症状特征", why_it_matters="w", evidence_span=evidence),
            DocumentationGap(gap_id="g2", description="症状性质", why_it_matters="w", evidence_span=evidence),
        ],
        proposed_provider_queries=queries,
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)
    assert [query.query_id for query in case.proposed_provider_queries] == ["q-features"]
    assert case.query_rewrite_queue[-1]["status"] == "DEFERRED_SYMPTOM_REFINEMENT"


def test_necessity_focus_does_not_collapse_distinct_evidence_spans() -> None:
    queries = [
        ProviderQuery(
            query_id="q-one", gap_id="g1", topic="胸闷", reason="gap",
            evidence_span=EvidenceSpan(document_id="d", quote="间断胸闷"), query_text="请明确胸闷。",
        ),
        ProviderQuery(
            query_id="q-two", gap_id="g2", topic="体重减轻", reason="gap",
            evidence_span=EvidenceSpan(document_id="d", quote="体重减轻5kg"), query_text="请明确体重减轻。",
        ),
    ]
    case = CDICase(
        case_id="c-distinct-evidence", chart_excerpt="间断胸闷，体重减轻5kg。建议进一步检查。",
        documentation_gaps=[
            DocumentationGap(gap_id="g1", description="胸闷", why_it_matters="w", evidence_span=queries[0].evidence_span),
            DocumentationGap(gap_id="g2", description="体重", why_it_matters="w", evidence_span=queries[1].evidence_span),
        ],
        proposed_provider_queries=queries,
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)
    assert len(case.proposed_provider_queries) == 2


def _compound_pancreatitis_case() -> CDICase:
    chart = "入院诊断：急性胰腺炎。既往：胆石症。"
    gap = DocumentationGap(
        gap_id="g-etiology",
        gap_type="etiology unspecified",
        description="急性胰腺炎病因未明确",
        why_it_matters="病因影响临床记录准确性",
        evidence_span=EvidenceSpan(
            document_id="chart", quote="入院诊断：急性胰腺炎",
        ),
    )
    compound = ProviderQuery(
        query_id="q-compound",
        gap_id=gap.gap_id,
        topic="急性胰腺炎病因和严重程度",
        reason="需要分别澄清",
        evidence_span=gap.evidence_span,
        query_text="请说明急性胰腺炎的病因和严重程度。",
        response_options=["A", "B", "C", "D. 无法确定"],
    )
    return CDICase(
        case_id="c-rewrite",
        chart_excerpt=chart,
        documentation_gaps=[gap],
        proposed_provider_queries=[compound],
    )


def test_laterality_conflict_gets_deterministic_site_only_rewrite() -> None:
    chart = (
        "入院诊断:左侧肋骨骨折。出院诊断:右侧肋骨骨折。"
        "手术记录:右胸第5肋骨折固定术。CT报告:右侧肋骨骨折。"
    )
    spans = [
        EvidenceSpan(
            document_id="chart",
            quote="入院诊断:左侧肋骨骨折。出院诊断:右侧肋骨骨折。",
            char_start=0,
            char_end=24,
        ),
        EvidenceSpan(
            document_id="chart",
            quote="手术记录:右胸第5肋骨折固定术。CT报告:右侧肋骨骨折。",
            char_start=24,
            char_end=len(chart),
        ),
    ]
    gap = DocumentationGap(
        gap_id="g-site",
        gap_type="anatomical site unspecified",
        description="不同记录中的左右侧别矛盾",
        why_it_matters="最终诊断侧别影响编码",
        evidence_span=spans[0],
    )
    query = ProviderQuery(
        query_id="q-site-compound",
        gap_id=gap.gap_id,
        topic="明确最终诊断及左右侧不一致的原因",
        reason="记录中的左右侧别矛盾",
        evidence_span=spans[0],
        evidence_spans=spans,
        query_text="请明确最终诊断的侧别及导致不一致的原因。",
        response_options=[
            "A. 左侧，其他记录有误",
            "B. 右侧，入院记录有误",
            "C. 双侧",
            "D. 无法确定",
        ],
    )
    case = CDICase(
        case_id="c-laterality-conflict",
        chart_excerpt=chart,
        documentation_gaps=[gap],
        proposed_provider_queries=[query],
    )

    def provider_must_not_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("deterministic laterality repair must not call provider")

    CDIOrchestrator(runner=provider_must_not_run)._stage_query_single_dimension_gate(case)

    assert len(case.proposed_provider_queries) == 1
    rewritten = case.proposed_provider_queries[0]
    assert rewritten.topic == "最终诊断的侧别"
    assert rewritten.query_text == "请明确最终诊断中所记录病变的侧别。"
    assert len(rewritten.all_evidence_spans()) == 2
    audit = case.query_rewrite_queue[0]
    assert audit["rewrite_kind"] == "LATERALITY_CONFLICT_SITE_ONLY"
    assert audit["rewrite_attempt_status"] == "ACCEPTED_FOR_DOWNSTREAM_GATES"
    assert "rewrite_accepted=1" in case.stage_run_ids["query_single_dimension_gate"]


def test_aecopd_abnormal_blood_gas_gets_missing_respiratory_failure_coverage() -> None:
    chart = "入院诊断:慢阻肺急性加重。血气:pH 7.34, PaCO2 62, PaO2 55。"
    gap = DocumentationGap(
        gap_id="g-abg",
        gap_type="diagnostic specificity",
        description="血气异常的临床意义尚未形成明确诊断",
        why_it_matters="需要明确呼吸衰竭诊断及类型",
        evidence_span=EvidenceSpan(
            document_id="chart", quote="血气:pH 7.34, PaCO2 62, PaO2 55"
        ),
    )
    generic = ProviderQuery(
        query_id="q-generic-severity",
        gap_id=gap.gap_id,
        topic="COPD急性加重的严重程度",
        reason="未记录严重程度",
        evidence_span=EvidenceSpan(document_id="chart", quote="入院诊断:慢阻肺急性加重"),
        query_text="本次COPD急性加重的严重程度如何评估？",
        response_options=["A. 轻度", "B. 中度", "C. 重度", "D. 无法确定"],
    )
    case = CDICase(
        case_id="c-aecopd-rf",
        chart_excerpt=chart,
        documentation_gaps=[gap],
        proposed_provider_queries=[generic],
    )

    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)

    assert len(case.proposed_provider_queries) == 1
    query = case.proposed_provider_queries[0]
    assert query.topic == "呼吸衰竭类型"
    assert "II型呼吸衰竭" in " ".join(query.response_options)
    coverage = next(
        item for item in case.query_rewrite_queue
        if item.get("status") == "DETERMINISTIC_COVERAGE_GENERATED"
    )
    assert coverage["rewrite_kind"] == "AECOPD_RESPIRATORY_FAILURE_TYPE"


def test_absent_dimension_rewrite_keeps_truthful_trace_placeholders() -> None:
    case = CDICase(
        case_id="c-no-dimension-rewrite",
        chart_excerpt="去标识化合成病历，未生成 Provider Query。",
    )

    CDIOrchestrator(runner=stub_runner)._stage_query_single_dimension_gate(case)

    assert case.stage_run_ids["query_dimension_rewrite"] == "not_executed"
    assert case.stage_trace_ids["query_dimension_rewrite"] == ""
    assert "rewrite_attempted=0" in case.stage_run_ids[
        "query_single_dimension_gate"
    ]


def test_query_generation_removes_chart_ungrounded_quantitative_options() -> None:
    chart = "入院记录：血清肌酐210μmol/L，基线不详。"

    def runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
        assert stage == "query_generation"
        return {
            "run_id": "run-query-quantities",
            "trace_id": "trace-query-quantities",
            "queries": [{
                "query_id": "q-aki",
                "gap_id": "g-aki",
                "topic": "肾功能变化的临床判断",
                "reason": "基线不详",
                "evidence_span": {
                    "document_id": "chart",
                    "quote": "血清肌酐210μmol/L",
                },
                "query_text": "请根据病历说明本次肾功能变化的临床判断。",
                "response_options": [
                    "较基线升高110μmol/L",
                    "尿量低于0.5ml持续6小时",
                    "其他临床判断（请说明）",
                    "无法确定",
                ],
            }],
        }

    case = CDICase(case_id="c-query-quantities", chart_excerpt=chart)

    CDIOrchestrator(runner=runner)._stage_query_generation(case)

    assert len(case.proposed_provider_queries) == 1
    options = case.proposed_provider_queries[0].response_options
    assert len(options) >= 4
    assert all("110μmol/L" not in option for option in options)
    assert all("0.5ml" not in option for option in options)
    assert any("无法确定" in option for option in options)


def test_pneumonia_type_and_severity_gets_deterministic_type_only_rewrite() -> None:
    chart = "胸片示右下肺浸润影。入院诊断:肺炎。"
    gap = DocumentationGap(
        gap_id="g-pneumonia-type",
        gap_type="diagnostic specificity",
        description="肺炎类型和严重程度未明确",
        why_it_matters="诊断类型影响编码",
        evidence_span=EvidenceSpan(document_id="chart", quote="入院诊断:肺炎"),
    )
    query = ProviderQuery(
        query_id="q-pneumonia-compound",
        gap_id=gap.gap_id,
        topic="肺炎类型与严重程度",
        reason="类型和严重度未明确",
        evidence_span=gap.evidence_span,
        query_text="请明确肺炎的具体类型和严重程度。",
        response_options=[
            "A. 社区获得性肺炎，轻度", "B. 社区获得性肺炎，重度",
            "C. 吸入性肺炎", "D. 无法确定",
        ],
    )
    case = CDICase(
        case_id="c-pneumonia-type",
        chart_excerpt=chart,
        documentation_gaps=[gap],
        proposed_provider_queries=[query],
    )

    def provider_must_not_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("deterministic pneumonia repair must not call provider")

    CDIOrchestrator(runner=provider_must_not_run)._stage_query_single_dimension_gate(case)

    assert len(case.proposed_provider_queries) == 1
    rewritten = case.proposed_provider_queries[0]
    assert rewritten.topic == "肺炎类型"
    assert rewritten.query_text == "请明确本次肺炎的具体类型。"
    assert case.query_rewrite_queue[0]["rewrite_kind"] == "PNEUMONIA_TYPE_ONLY"


def test_dka_yes_no_confirmation_is_rewritten_to_open_diagnosis_request() -> None:
    span = EvidenceSpan(
        document_id="chart",
        quote="pH 7.30, HCO3 16, 酮体阳性。入院诊断:2型糖尿病。",
    )
    query = ProviderQuery(
        query_id="q-dka",
        gap_id="g-dka",
        topic="糖尿病酮症酸中毒的诊断",
        reason="酸中毒和酮体阳性但未记录DKA",
        evidence_span=span,
        query_text="请明确本次入院时是否诊断为糖尿病酮症酸中毒？",
        response_options=[
            "A. 是，诊断为糖尿病酮症酸中毒",
            "B. 否，不考虑糖尿病酮症酸中毒",
            "C. 其他急性并发症（请注明）",
            "D. 无法确定",
        ],
    )
    case = CDICase(
        case_id="c-dka-compliance",
        chart_excerpt=span.quote,
        proposed_provider_queries=[query],
    )

    CDIOrchestrator(runner=stub_runner)._stage_query_compliance_gate(case)

    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].query_text == (
        "请明确本次入院应记录的糖尿病急性并发症。"
    )
    assert case.proposed_provider_queries[0].nlq_gate_verdict == "PASS"
    assert case.query_rewrite_queue[0]["rewrite_kind"] == "OPEN_DKA_DIAGNOSIS_REQUEST"


def test_pneumonia_and_dka_core_coverage_are_added_when_model_misses_them() -> None:
    pneumonia_chart = "胸片示右下肺浸润影。WBC 14.5。入院诊断:肺炎。"
    pneumonia_gap = DocumentationGap(
        gap_id="g-pna-core", gap_type="diagnostic specificity",
        description="Pneumonia type and severity are not specified",
        why_it_matters="Type affects documentation",
        evidence_span=EvidenceSpan(document_id="chart", quote="入院诊断:肺炎"),
    )
    pneumonia_case = CDICase(
        case_id="c-pna-core", chart_excerpt=pneumonia_chart,
        documentation_gaps=[pneumonia_gap], proposed_provider_queries=[],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(pneumonia_case)
    assert [q.topic for q in pneumonia_case.proposed_provider_queries] == ["肺炎类型"]

    dka_chart = "FPG 12.5, pH 7.30, HCO3 16, 酮体阳性。入院诊断:2型糖尿病。"
    dka_gap = DocumentationGap(
        gap_id="g-dka-core", gap_type="diagnostic specificity",
        description="Ketoacidosis is present but not documented as diabetic ketoacidosis",
        why_it_matters="DKA changes coding",
        evidence_span=EvidenceSpan(document_id="chart", quote=dka_chart),
    )
    dka_case = CDICase(
        case_id="c-dka-core", chart_excerpt=dka_chart,
        documentation_gaps=[dka_gap], proposed_provider_queries=[],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(dka_case)
    assert len(dka_case.proposed_provider_queries) == 1
    assert "糖尿病急性并发症" == dka_case.proposed_provider_queries[0].topic
    assert "糖尿病酮症酸中毒" in " ".join(dka_case.proposed_provider_queries[0].response_options)


def test_iron_deficiency_with_occult_blood_gets_causal_diagnosis_query() -> None:
    chart = (
        "患者男性, 60岁, 乏力1月。Hb 65, MCV 72。"
        "血清铁 4.5, 铁蛋白 8。便潜血阳性。入院诊断:贫血。"
    )
    gap = DocumentationGap(
        gap_id="g-ida-blood-loss", gap_type="etiology unspecified",
        description="贫血病因未明确，便潜血阳性提示慢性消化道失血可能",
        why_it_matters="D50.0 与 D50.9 的编码不同",
        evidence_span=EvidenceSpan(document_id="chart", quote="入院诊断:贫血"),
    )
    existing = ProviderQuery(
        query_id="q-ida-type", gap_id=gap.gap_id, topic="贫血病因",
        reason="缺铁指标异常但仅记录贫血，需要明确出血来源",
        evidence_span=EvidenceSpan(
            document_id="chart", quote="Hb 65, MCV 72。血清铁 4.5, 铁蛋白 8"
        ),
        query_text="贫血的病因及可能的出血来源是什么？",
        response_options=[
            "A. 缺铁性贫血，考虑消化道出血可能", "B. 慢性病性贫血",
            "C. 其他类型（请注明）", "D. 无法确定",
        ],
    )
    case = CDICase(
        case_id="c-ida-blood-loss", chart_excerpt=chart,
        documentation_gaps=[gap], proposed_provider_queries=[existing],
    )

    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)

    assert len(case.proposed_provider_queries) == 2
    normalized = next(query for query in case.proposed_provider_queries if query.query_id == "q-ida-type")
    assert normalized.topic == "贫血类型"
    assert normalized.query_text == "请明确本次贫血的诊断类型。"
    assert "出血来源" not in " ".join(normalized.response_options)
    causal = next(
        query for query in case.proposed_provider_queries
        if query.query_id.startswith("Q-IDA-BL-")
    )
    assert causal.query_text == "请明确本次缺铁性贫血与慢性消化道失血的诊断关系。"
    assert len(causal.all_evidence_spans()) == 2
    assert causal.all_evidence_spans()[1].quote == "便潜血阳性"
    audit = next(
        item for item in case.query_rewrite_queue
        if item.get("rewrite_kind") == "IRON_DEFICIENCY_CHRONIC_BLOOD_LOSS_RELATION"
    )
    assert audit["status"] == "DETERMINISTIC_COVERAGE_GENERATED"


def test_existing_dka_severity_yes_no_draft_is_normalized_before_later_gates() -> None:
    chart = "FPG 12.5, pH 7.30, HCO3 16, 酮体阳性。入院诊断:2型糖尿病。"
    span = EvidenceSpan(document_id="chart", quote="pH 7.30, HCO3 16, 酮体阳性")
    gap = DocumentationGap(
        gap_id="g-dka-existing", gap_type="diagnostic specificity",
        description="DKA diagnosis and severity are undocumented",
        why_it_matters="DKA changes coding", evidence_span=span,
    )
    query = ProviderQuery(
        query_id="q-dka-existing", gap_id=gap.gap_id,
        topic="DKA诊断及严重程度", reason="DKA未明确",
        evidence_span=span,
        query_text="请明确患者是否存在糖尿病酮症酸中毒及其严重程度。",
        response_options=["A. 轻度", "B. 中度", "C. 重度", "D. 无法确定"],
    )
    case = CDICase(
        case_id="c-dka-existing", chart_excerpt=chart,
        documentation_gaps=[gap], proposed_provider_queries=[query],
    )

    orchestrator = CDIOrchestrator(runner=stub_runner)
    orchestrator._stage_query_necessity_gate(case)
    orchestrator._stage_query_single_dimension_gate(case)
    orchestrator._stage_query_compliance_gate(case)

    assert len(case.proposed_provider_queries) == 1
    rewritten = case.proposed_provider_queries[0]
    assert rewritten.topic == "糖尿病急性并发症"
    assert rewritten.query_text == "请明确本次入院应记录的糖尿病急性并发症。"
    assert rewritten.nlq_gate_verdict == "PASS"
    audit = next(
        item for item in case.query_rewrite_queue
        if item.get("rewrite_kind") == "FOCUS_DKA_DIAGNOSIS"
    )
    assert audit["rewrite_attempt_status"] == "ACCEPTED_FOR_DOWNSTREAM_GATES"


def test_document_conflict_and_biliary_obstruction_get_core_coverage() -> None:
    pancreatitis_chart = (
        "入院诊断:胆源性胰腺炎。MRI:未见胆总管结石。"
        "饮酒史:每日白酒100ml。出院诊断:特发性胰腺炎。"
    )
    pancreatitis_gap = DocumentationGap(
        gap_id="g-panc-conflict", gap_type="etiology unspecified",
        description="胆源性与特发性胰腺炎诊断冲突",
        why_it_matters="病因影响最终诊断", evidence_span=EvidenceSpan(document_id="chart", quote="入院诊断:胆源性胰腺炎"),
    )
    pancreatitis_case = CDICase(
        case_id="c-panc-conflict", chart_excerpt=pancreatitis_chart,
        documentation_gaps=[pancreatitis_gap], proposed_provider_queries=[],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(pancreatitis_case)
    assert [q.topic for q in pancreatitis_case.proposed_provider_queries] == ["急性胰腺炎病因"]
    assert len(pancreatitis_case.proposed_provider_queries[0].all_evidence_spans()) == 2

    biliary_chart = (
        "B超:胆囊壁增厚，胆囊多发结石，胆总管直径 9mm。"
        "肝功能:ALT 120, AST 95, ALP 280, TBIL 45。入院诊断:急性胆囊炎。"
    )
    biliary_gap = DocumentationGap(
        gap_id="g-cbd", gap_type="diagnostic specificity",
        description="胆总管扩张和肝功能异常的临床关联未明确",
        why_it_matters="可能存在胆总管结石或胆管炎",
        evidence_span=EvidenceSpan(document_id="chart", quote="胆总管直径9mm"),
    )
    biliary_case = CDICase(
        case_id="c-cbd", chart_excerpt=biliary_chart,
        documentation_gaps=[biliary_gap], proposed_provider_queries=[],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(biliary_case)
    assert [q.topic for q in biliary_case.proposed_provider_queries] == ["胆道梗阻相关诊断"]


def test_gate8_gap004_gallstone_history_gets_open_pancreatitis_etiology_coverage() -> None:
    chart = (
        "患者女性, 55岁, 上腹痛2天, 淀粉酶 580。"
        "CT:胰腺肿胀伴渗出。入院诊断:急性胰腺炎。既往:胆石症。"
    )
    gap = DocumentationGap(
        gap_id="g-gate8-gap004",
        gap_type="etiology unspecified",
        description="胆石症与急性胰腺炎的病因关联未明确",
        why_it_matters="病因特异性影响诊断记录",
        evidence_span=EvidenceSpan(document_id="chart", quote="既往:胆石症"),
    )
    case = CDICase(
        case_id="G8-CDI-GAP-004",
        chart_excerpt=chart,
        documentation_gaps=[gap],
        proposed_provider_queries=[],
    )

    orchestrator = CDIOrchestrator(runner=stub_runner)
    orchestrator._stage_query_necessity_gate(case)
    orchestrator._stage_query_single_dimension_gate(case)
    orchestrator._stage_query_compliance_gate(case)

    assert len(case.proposed_provider_queries) == 1
    query = case.proposed_provider_queries[0]
    assert query.topic == "急性胰腺炎病因"
    assert query.query_text == "请明确本次急性胰腺炎的最终病因诊断。"
    assert len(query.all_evidence_spans()) == 2
    assert "无法确定" in " ".join(query.response_options)
    assert query.nlq_gate_verdict == "PASS"


def test_pancreatitis_etiology_coverage_does_not_duplicate_resolved_biliary_diagnosis() -> None:
    chart = "入院诊断:胆源性急性胰腺炎。既往:胆石症。"
    gap = DocumentationGap(
        gap_id="g-resolved-etiology",
        gap_type="etiology unspecified",
        description="急性胰腺炎病因",
        why_it_matters="病因影响诊断记录",
        evidence_span=EvidenceSpan(document_id="chart", quote="胆源性急性胰腺炎"),
    )
    case = CDICase(
        case_id="resolved-pancreatitis-etiology",
        chart_excerpt=chart,
        documentation_gaps=[gap],
        proposed_provider_queries=[],
    )

    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)

    assert case.proposed_provider_queries == []


def test_gate8_conflict032_historical_three_drafts_are_focused_to_duration() -> None:
    chart = (
        "患者女性, 65岁, 入院诊断:2型糖尿病。"
        "入院记录:既往无糖尿病史, 本次为初次发现。"
        "出院小结:糖尿病史10年, 平素血糖控制不佳。门诊病历:新发糖尿病。"
    )
    drafts = [
        ProviderQuery(
            query_id="q-duration",
            gap_id="g-duration",
            topic="糖尿病病程",
            reason="病程记录冲突",
            evidence_span=EvidenceSpan(document_id="chart", quote="本次为初次发现"),
            query_text="请明确患者糖尿病的实际病程。",
            response_options=["A. 本次新发", "B. 已有10年", "C. 其他", "D. 无法确定"],
        ),
        ProviderQuery(
            query_id="q-control",
            gap_id="g-control",
            topic="血糖控制量化指标",
            reason="控制不佳",
            evidence_span=EvidenceSpan(document_id="chart", quote="平素血糖控制不佳"),
            query_text="请提供反映血糖控制水平的具体量化指标。",
            response_options=["A. HbA1c", "B. 空腹血糖", "C. 其他", "D. 无法确定"],
        ),
        ProviderQuery(
            query_id="q-type",
            gap_id="g-type",
            topic="糖尿病类型",
            reason="类型确认",
            evidence_span=EvidenceSpan(document_id="chart", quote="入院诊断:2型糖尿病"),
            query_text="请明确患者糖尿病的具体类型。",
            response_options=["A. 1型", "B. 2型", "C. 其他", "D. 无法确定"],
        ),
    ]
    gaps = [
        DocumentationGap(
            gap_id=query.gap_id,
            description=query.topic,
            why_it_matters="诊断记录一致性",
            evidence_span=query.evidence_span,
        )
        for query in drafts
    ]
    case = CDICase(
        case_id="G8-CDI-CONFLICT-032",
        chart_excerpt=chart,
        documentation_gaps=gaps,
        proposed_provider_queries=drafts,
    )

    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)

    assert [query.query_id for query in case.proposed_provider_queries] == ["q-duration"]


def test_english_acidosis_type_draft_with_dka_option_is_normalized() -> None:
    chart = "FPG 12.5, pH 7.30, HCO3 16, 酮体阳性。入院诊断:2型糖尿病。"
    span = EvidenceSpan(document_id="chart", quote="pH 7.30, HCO3 16, 酮体阳性")
    gap = DocumentationGap(
        gap_id="g-acidosis-en", gap_type="diagnostic specificity",
        description="Possible diabetic ketoacidosis (DKA) is not specified",
        why_it_matters="DKA changes coding", evidence_span=span,
    )
    query = ProviderQuery(
        query_id="q-acidosis-en", gap_id=gap.gap_id,
        topic="Acidosis type specification", reason="Acidosis is unspecified",
        evidence_span=span,
        query_text="Please clarify the specific type of acidosis.",
        response_options=["A. Diabetic ketoacidosis (DKA)", "B. Lactic acidosis", "C. Other", "D. Unable to determine"],
    )
    case = CDICase(
        case_id="c-acidosis-en", chart_excerpt=chart,
        documentation_gaps=[gap], proposed_provider_queries=[query],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)
    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].topic == "糖尿病急性并发症"


def test_existing_biliary_yes_no_draft_is_normalized_to_open_diagnosis_query() -> None:
    chart = (
        "B超:胆囊多发结石，胆总管直径 9mm。"
        "肝功能:ALT 120, AST 95, ALP 280, TBIL 45。入院诊断:急性胆囊炎。"
    )
    span = EvidenceSpan(document_id="chart", quote="胆总管直径 9mm")
    gap = DocumentationGap(
        gap_id="g-biliary-existing", gap_type="diagnostic specificity",
        description="Biliary obstruction or choledocholithiasis is not diagnosed",
        why_it_matters="Additional diagnosis affects coding", evidence_span=span,
    )
    query = ProviderQuery(
        query_id="q-biliary-existing", gap_id=gap.gap_id,
        topic="胆道梗阻或胆总管结石的诊断", reason="胆总管扩张",
        evidence_span=span,
        query_text="请明确是否存在胆道梗阻及其病因。",
        response_options=["A. 胆总管结石", "B. 胆管炎", "C. 其他", "D. 无法确定"],
    )
    case = CDICase(
        case_id="c-biliary-existing", chart_excerpt=chart,
        documentation_gaps=[gap], proposed_provider_queries=[query],
    )
    orchestrator = CDIOrchestrator(runner=stub_runner)
    orchestrator._stage_query_necessity_gate(case)
    orchestrator._stage_query_single_dimension_gate(case)
    orchestrator._stage_query_compliance_gate(case)
    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].topic == "胆道梗阻相关诊断"
    assert case.proposed_provider_queries[0].nlq_gate_verdict == "PASS"


def test_biliary_core_query_defers_liver_abnormality_cause_refinement() -> None:
    chart = (
        "B超:胆囊多发结石，胆总管直径 9mm。"
        "肝功能:ALT 120, AST 95, ALP 280, TBIL 45。入院诊断:急性胆囊炎。"
    )
    span = EvidenceSpan(document_id="chart", quote="胆总管直径 9mm")
    gap = DocumentationGap(
        gap_id="g-biliary-focus", gap_type="diagnostic specificity",
        description="Biliary obstruction is not diagnosed",
        why_it_matters="Additional diagnosis affects coding", evidence_span=span,
    )
    liver = ProviderQuery(
        query_id="q-liver-cause", gap_id=gap.gap_id,
        topic="肝功能异常原因", reason="肝功能异常",
        evidence_span=EvidenceSpan(document_id="chart", quote="ALP 280, TBIL 45"),
        query_text="请明确肝功能异常的临床原因。",
        response_options=["A. 胆道梗阻", "B. 肝细胞损伤", "C. 其他", "D. 无法确定"],
    )
    case = CDICase(
        case_id="c-biliary-focus", chart_excerpt=chart,
        documentation_gaps=[gap], proposed_provider_queries=[liver],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)
    assert [q.topic for q in case.proposed_provider_queries] == ["胆道梗阻相关诊断"]


def test_progress_note_comorbidity_omission_is_focused_to_one_discharge_query() -> None:
    chart = (
        "入院诊断:原发性高血压，2型糖尿病。"
        "病程记录:高血压，糖尿病，慢性肾病，高脂血症。"
        "出院诊断:高血压，糖尿病。"
    )
    gaps = [
        DocumentationGap(
            gap_id="g-ckd", gap_type="diagnostic specificity",
            description="慢性肾病未明确分期", why_it_matters="影响编码",
            evidence_span=EvidenceSpan(document_id="chart", quote="慢性肾病"),
        )
    ]
    secondary = ProviderQuery(
        query_id="q-ckd-stage", gap_id="g-ckd", topic="慢性肾病分期或严重程度",
        reason="未分期", evidence_span=gaps[0].evidence_span,
        query_text="请明确慢性肾病分期或严重程度。",
        response_options=["A. 1期", "B. 2期", "C. 3期", "D. 无法确定"],
    )
    case = CDICase(
        case_id="c-comorbidity-omission", chart_excerpt=chart,
        documentation_gaps=gaps, proposed_provider_queries=[secondary],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)
    assert [q.topic for q in case.proposed_provider_queries] == ["出院诊断合并症完整性"]


def test_split_yes_no_omission_drafts_are_replaced_by_one_open_combined_query() -> None:
    chart = (
        "病程记录:高血压，糖尿病，慢性肾病，高脂血症。"
        "出院诊断:高血压，糖尿病。"
    )
    gaps = [DocumentationGap(
        gap_id="g-omission", gap_type="diagnostic specificity",
        description="慢性肾病和高脂血症未纳入出院诊断", why_it_matters="诊断完整性",
        evidence_span=EvidenceSpan(document_id="chart", quote="慢性肾病，高脂血症"),
    )]
    drafts = [
        ProviderQuery(
            query_id=f"q-{name}", gap_id="g-omission", topic=f"出院诊断是否包含{name}",
            reason="可能遗漏", evidence_span=EvidenceSpan(document_id="chart", quote=name),
            query_text=f"请明确出院时{name}是否仍存在。",
            response_options=["A. 是", "B. 否", "C. 其他", "D. 无法确定"],
        ) for name in ("慢性肾病", "高脂血症")
    ]
    case = CDICase(
        case_id="c-split-omission", chart_excerpt=chart,
        documentation_gaps=gaps, proposed_provider_queries=drafts,
    )
    orchestrator = CDIOrchestrator(runner=stub_runner)
    orchestrator._stage_query_necessity_gate(case)
    orchestrator._stage_query_compliance_gate(case)
    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].topic == "出院诊断合并症完整性"
    assert case.proposed_provider_queries[0].nlq_gate_verdict == "PASS"


def test_low_risk_cough_keeps_one_symptom_query_and_defers_hypertension_history() -> None:
    chart = (
        "咳嗽1周。否认发热、咳脓痰、咯血、胸痛。既往:高血压。"
        "查体:双肺清晰。胸片:未见活动性病变。"
    )
    cough = ProviderQuery(
        query_id="q-cough", gap_id="g-cough", topic="咳嗽类型",
        reason="未描述", evidence_span=EvidenceSpan(document_id="chart", quote="咳嗽1周"),
        query_text="请描述咳嗽的具体类型及特点。",
        response_options=["A. 干咳", "B. 湿咳", "C. 其他", "D. 无法确定"],
    )
    hypertension = ProviderQuery(
        query_id="q-htn", gap_id="g-htn", topic="高血压管理",
        reason="既往高血压", evidence_span=EvidenceSpan(document_id="chart", quote="既往:高血压"),
        query_text="请提供本次血压水平及高血压管理情况。",
        response_options=["A. 控制良好", "B. 控制不佳", "C. 其他", "D. 无法确定"],
    )
    gaps = [
        DocumentationGap(gap_id="g-cough", description="咳嗽类型未明确", why_it_matters="症状记录", evidence_span=cough.evidence_span),
        DocumentationGap(gap_id="g-htn", description="高血压管理未明确", why_it_matters="慢病记录", evidence_span=hypertension.evidence_span),
    ]
    case = CDICase(
        case_id="c-low-risk-cough-focus", chart_excerpt=chart,
        documentation_gaps=gaps, proposed_provider_queries=[cough, hypertension],
    )
    CDIOrchestrator(runner=stub_runner)._stage_query_necessity_gate(case)
    assert [q.query_id for q in case.proposed_provider_queries] == ["q-cough"]
    assert any(item.get("status") == "DEFERRED_LOW_RISK_SYMPTOM_FOCUS" for item in case.query_rewrite_queue)


def test_compound_query_gets_one_bounded_single_dimension_rewrite() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
        calls.append((stage, kwargs))
        if stage != "query_dimension_rewrite":
            return {}
        return {
            "queries": [{
                "source_query_id": "q-compound",
                "query_id": "q-etiology-rewrite",
                "gap_id": "g-etiology",
                "topic": "急性胰腺炎病因",
                "reason": "病因尚未明确",
                "evidence_span": {
                    "document_id": "chart",
                    "quote": "入院诊断：急性胰腺炎",
                },
                "query_text": "请根据临床判断说明本次急性胰腺炎的病因。",
                "response_options": [
                    "A. 胆源性", "B. 酒精相关", "C. 其他", "D. 无法确定",
                ],
            }],
            "run_id": "rewrite-run",
            "trace_id": "rewrite-trace",
        }

    case = _compound_pancreatitis_case()
    orchestrator = CDIOrchestrator(runner=runner)
    orchestrator._stage_query_single_dimension_gate(case)

    assert [q.query_id for q in case.proposed_provider_queries] == [
        "q-etiology-rewrite"
    ]
    assert [stage for stage, _ in calls] == ["query_dimension_rewrite"]
    assert calls[0][1]["rewrite_items"][0]["gap_id"] == "g-etiology"
    assert calls[0][1]["rewrite_items"][0]["target_axis"] == "etiology"
    audit = case.query_rewrite_queue[0]
    assert audit["status"] == "REWRITE_CANDIDATE_GENERATED"
    assert audit["replacement_query_id"] == "q-etiology-rewrite"
    assert "rewrite_attempted=1" in case.stage_run_ids[
        "query_single_dimension_gate"
    ]
    assert "rewrite_accepted=1" in case.stage_run_ids[
        "query_single_dimension_gate"
    ]


def test_compound_rewrite_cannot_change_gap_or_bypass_later_nlq_gate() -> None:
    def wrong_gap_runner(
        stage: str, case: CDICase, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        return {"queries": [{
            "source_query_id": "q-compound",
            "query_id": "q-wrong-gap",
            "gap_id": "g-invented",
            "topic": "急性胰腺炎病因",
            "evidence_span": {
                "document_id": "chart", "quote": "入院诊断：急性胰腺炎",
            },
            "query_text": "请说明急性胰腺炎病因。",
            "response_options": ["A", "B", "C", "D. 无法确定"],
        }]}

    case = _compound_pancreatitis_case()
    orchestrator = CDIOrchestrator(runner=wrong_gap_runner)
    orchestrator._stage_query_single_dimension_gate(case)
    assert case.proposed_provider_queries == []
    assert case.query_rewrite_queue[0]["rewrite_attempt_status"] == (
        "REJECTED_BY_SAFETY_GATES"
    )
    assert any(
        "changed the source gap_id" in reason
        for reason in case.query_rewrite_queue[0]["rewrite_attempt_reasons"]
    )

    def leading_runner(
        stage: str, case: CDICase, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        return {"queries": [{
            "source_query_id": "q-compound",
            "query_id": "q-leading-rewrite",
            "gap_id": "g-etiology",
            "topic": "急性胰腺炎病因",
            "evidence_span": {
                "document_id": "chart", "quote": "入院诊断：急性胰腺炎",
            },
            "query_text": "是否为胆源性急性胰腺炎？",
            "response_options": ["A. 是", "B. 否", "C. 其他", "D. 无法确定"],
        }]}

    case = _compound_pancreatitis_case()
    orchestrator = CDIOrchestrator(runner=leading_runner)
    orchestrator._stage_query_single_dimension_gate(case)
    assert len(case.proposed_provider_queries) == 1
    orchestrator._stage_query_compliance_gate(case)
    assert case.proposed_provider_queries == []
    assert case.query_rewrite_queue[-1]["status"] == (
        "NEEDS_NON_LEADING_REWRITE"
    )


def test_compound_rewrite_must_match_source_gap_dimension() -> None:
    def wrong_axis_runner(
        stage: str, case: CDICase, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        return {"queries": [{
            "source_query_id": "q-compound",
            "query_id": "q-severity-for-etiology-gap",
            "gap_id": "g-etiology",
            "topic": "急性胰腺炎严重程度",
            "evidence_span": {
                "document_id": "chart", "quote": "入院诊断：急性胰腺炎",
            },
            "query_text": "请说明本次急性胰腺炎的严重程度。",
            "response_options": ["A. 轻症", "B. 中重症", "C. 重症", "D. 无法确定"],
        }]}

    case = _compound_pancreatitis_case()
    orchestrator = CDIOrchestrator(runner=wrong_axis_runner)
    orchestrator._stage_query_single_dimension_gate(case)

    assert case.proposed_provider_queries == []
    reasons = case.query_rewrite_queue[0]["rewrite_attempt_reasons"]
    assert any("does not match source gap" in reason for reason in reasons)
    assert any("server-selected target axis" in reason for reason in reasons)


def test_compound_rewrite_provider_failure_stays_fail_closed() -> None:
    def failing_runner(
        stage: str, case: CDICase, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        raise RuntimeError("provider unavailable")

    case = _compound_pancreatitis_case()
    orchestrator = CDIOrchestrator(runner=failing_runner)
    orchestrator._stage_query_single_dimension_gate(case)

    assert case.proposed_provider_queries == []
    audit = case.query_rewrite_queue[0]
    assert audit["status"] == "NEEDS_CDI_REWRITE"
    assert audit["rewrite_attempt_status"] == "DEGRADED"
    assert audit["rewrite_attempt_reasons"] == [
        "rewrite provider unavailable: RuntimeError"
    ]
    assert "rewrite_attempted=1" in case.stage_run_ids[
        "query_single_dimension_gate"
    ]
    assert "rewrite_accepted=0" in case.stage_run_ids[
        "query_single_dimension_gate"
    ]


def test_compound_rewrite_degraded_result_is_not_treated_as_empty_success() -> None:
    def degraded_runner(
        stage: str, case: CDICase, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "queries": [],
            "run_id": "rewrite-run",
            "trace_id": "rewrite-trace",
            "degraded": True,
            "error_reason": "llm_call_failed:ConnectionError",
        }

    case = _compound_pancreatitis_case()
    orchestrator = CDIOrchestrator(runner=degraded_runner)
    orchestrator._stage_query_single_dimension_gate(case)

    audit = case.query_rewrite_queue[0]
    assert case.proposed_provider_queries == []
    assert audit["rewrite_attempt_status"] == "DEGRADED"
    assert audit["rewrite_attempt_reasons"] == [
        "llm_call_failed:ConnectionError"
    ]
