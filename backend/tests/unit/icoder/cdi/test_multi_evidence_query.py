"""Regression tests for fail-closed multi-span Provider Query evidence."""

from __future__ import annotations

from typing import Any

from app.icoder.agent_runtime.cdi.claim_evidence_gate import (
    anchor_query_evidence_spans,
)
from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
)
from app.icoder.agent_runtime.cdi.orchestrator import CDIOrchestrator


CHART = (
    "Admission diagnosis: biliary pancreatitis. "
    "The patient received fluids and analgesia for four days. "
    "Discharge diagnosis: idiopathic pancreatitis."
)
FIRST = "Admission diagnosis: biliary pancreatitis."
SECOND = "Discharge diagnosis: idiopathic pancreatitis."


def _query(*spans: EvidenceSpan) -> ProviderQuery:
    primary = spans[0] if spans else EvidenceSpan(document_id="note", quote="")
    return ProviderQuery(
        query_id="q_multi",
        gap_id="gap_conflict",
        topic="diagnostic conflict",
        reason="admission and discharge diagnoses conflict",
        evidence_span=primary,
        evidence_spans=list(spans),
        query_text="Please clarify the pancreatitis etiology documented for this stay.",
        response_options=["A. Biliary", "B. Idiopathic", "C. Other", "D. Unable to determine"],
    )


def test_two_separated_verbatim_evidence_spans_are_anchored_independently() -> None:
    query = _query(
        EvidenceSpan(document_id="note", quote=FIRST),
        EvidenceSpan(document_id="note", quote=SECOND, documented_at="2026-08-12T10:00:00Z"),
    )

    errors, snapped = anchor_query_evidence_spans(query, CHART)

    assert errors == []
    assert snapped == 0
    assert [span.quote for span in query.evidence_spans] == [FIRST, SECOND]
    assert query.evidence_span is query.evidence_spans[0]
    assert query.evidence_spans[0].char_start == CHART.index(FIRST)
    assert query.evidence_spans[0].char_end == CHART.index(FIRST) + len(FIRST)
    assert query.evidence_spans[1].char_start == CHART.index(SECOND)
    assert query.evidence_spans[1].char_end == CHART.index(SECOND) + len(SECOND)
    assert query.evidence_spans[1].documented_at == "2026-08-12T10:00:00Z"


def test_concatenated_non_contiguous_evidence_is_rejected() -> None:
    query = _query(EvidenceSpan(document_id="note", quote=f"{FIRST} {SECOND}"))

    errors, _ = anchor_query_evidence_spans(query, CHART)

    assert errors == [
        "evidence_spans[0] is not a verbatim contiguous chart span"
    ]


def test_one_unsupported_span_rejects_the_whole_evidence_set() -> None:
    query = _query(
        EvidenceSpan(document_id="note", quote=FIRST),
        EvidenceSpan(document_id="note", quote="Pathology confirmed malignancy."),
    )

    errors, _ = anchor_query_evidence_spans(query, CHART)

    assert errors == [
        "evidence_spans[1] is not a verbatim contiguous chart span"
    ]


def test_orchestrator_withholds_invalid_evidence_and_queues_rewrite() -> None:
    def runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
        assert stage == "query_generation"
        return {
            "queries": [
                {
                    "query_id": "q_invalid",
                    "gap_id": "gap_conflict",
                    "topic": "diagnostic conflict",
                    "reason": "conflicting diagnoses",
                    "query_text": "Please clarify the final diagnosis.",
                    "evidence_spans": [
                        {"document_id": "note", "quote": f"{FIRST} {SECOND}"}
                    ],
                    "response_options": [
                        "A. Biliary",
                        "B. Idiopathic",
                        "C. Other",
                        "D. Unable to determine",
                    ],
                }
            ],
            "run_id": "run_query",
            "trace_id": "trace_query",
        }

    case = CDICase(case_id="case_invalid", chart_excerpt=CHART)
    CDIOrchestrator(runner=runner)._stage_query_generation(case)

    assert case.proposed_provider_queries == []
    assert len(case.query_rewrite_queue) == 1
    queued = case.query_rewrite_queue[0]
    assert queued["query_id"] == "q_invalid"
    assert queued["status"] == "NEEDS_EVIDENCE_REWRITE"
    assert queued["gate_reasons"] == [
        "evidence_spans[0] is not a verbatim contiguous chart span"
    ]


def test_orchestrator_accepts_two_independent_evidence_spans() -> None:
    def runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
        assert stage == "query_generation"
        return {
            "queries": [
                {
                    "query_id": "q_valid",
                    "gap_id": "gap_conflict",
                    "topic": "diagnostic conflict",
                    "reason": "conflicting diagnoses",
                    "query_text": "Please clarify the final diagnosis.",
                    "evidence_spans": [
                        {"document_id": "note", "quote": FIRST},
                        {"document_id": "note", "quote": SECOND},
                    ],
                    "response_options": [
                        "A. Biliary",
                        "B. Idiopathic",
                        "C. Other",
                        "D. Unable to determine",
                    ],
                }
            ],
        }

    case = CDICase(case_id="case_valid", chart_excerpt=CHART)
    CDIOrchestrator(runner=runner)._stage_query_generation(case)

    assert case.query_rewrite_queue == []
    assert len(case.proposed_provider_queries) == 1
    query = case.proposed_provider_queries[0]
    assert [span.quote for span in query.evidence_spans] == [FIRST, SECOND]
    assert query.evidence_span.quote == FIRST


def test_query_generation_records_every_uncovered_gap_without_fabricating_query() -> None:
    def runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
        assert stage == "query_generation"
        return {"queries": []}

    case = CDICase(
        case_id="case_missing_draft",
        chart_excerpt=CHART,
        documentation_gaps=[
            DocumentationGap(
                gap_id="gap_severity",
                description="Severity is not documented",
                why_it_matters="Requires CDI review",
                evidence_span=EvidenceSpan(document_id="note", quote=FIRST),
            ),
            DocumentationGap(
                gap_id="gap_etiology",
                description="Etiology is not documented",
                why_it_matters="Requires CDI review",
                evidence_span=EvidenceSpan(document_id="note", quote=SECOND),
            ),
        ],
    )

    CDIOrchestrator(runner=runner)._stage_query_generation(case)

    assert case.proposed_provider_queries == []
    assert case.stage_run_ids["query_generation::coverage_missing"] == "2"
    assert [item["gap_id"] for item in case.query_rewrite_queue] == [
        "gap_severity",
        "gap_etiology",
    ]
    assert all(
        item["status"] == "NEEDS_QUERY_DRAFT"
        and item["query_text"] == ""
        and item["gate_reasons"]
        for item in case.query_rewrite_queue
    )
