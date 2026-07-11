"""Phase 5 Track D P0.5 Gate 1 — Data consistency unit tests.

Covers:
  - _localize_child_ids rewrites placeholder IDs to case-scoped
  - persist_case drops orphan queries (gap_id not in case gaps)
  - assert_case_consistent detects all known pathologies
  - derive_case_state returns correct state per gap/query counts
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
)
from app.models.cdi_case import (
    CDICaseModel,
    DocumentationGapModel,
    ProviderQueryModel,
)
from app.services.cdi_persistence import (
    _localize_child_ids,
    assert_case_consistent,
    derive_case_state,
    persist_case,
)


def _mk_evidence() -> EvidenceSpan:
    return EvidenceSpan(
        document_id="DOC-1",
        quote="咳嗽咳痰伴发热3天",
        char_start=0,
        char_end=10,
        documented_at="2024-01-01",
    )


def test_localize_placeholder_ids():
    """LLM placeholder IDs GAP-001 / Q-001 must be case-scoped."""
    case = CDICase(
        case_id="CASE-test-001",
        chart_excerpt="患者男性,58岁...",
        documentation_gaps=[
            DocumentationGap(
                gap_id="GAP-001",
                description="肺炎类型未明确",
                why_it_matters="影响编码",
                evidence_span=_mk_evidence(),
            ),
            DocumentationGap(
                gap_id="GAP-002",
                description="严重程度未明确",
                why_it_matters="影响DRG",
                evidence_span=_mk_evidence(),
            ),
        ],
        proposed_provider_queries=[
            ProviderQuery(
                query_id="Q-001",
                gap_id="GAP-001",
                topic="类型",
                reason="影响编码",
                evidence_span=_mk_evidence(),
                query_text="请明确肺炎的具体类型",
            ),
            ProviderQuery(
                query_id="Q-002",
                gap_id="GAP-002",
                topic="严重程度",
                reason="影响编码",
                evidence_span=_mk_evidence(),
                query_text="请明确严重程度",
            ),
        ],
    )

    out = _localize_child_ids(case)
    assert out.documentation_gaps[0].gap_id == "CASE-test-001/GAP-001"
    assert out.documentation_gaps[1].gap_id == "CASE-test-001/GAP-002"
    assert out.proposed_provider_queries[0].query_id == "CASE-test-001/Q-001"
    assert out.proposed_provider_queries[0].gap_id == "CASE-test-001/GAP-001"
    assert out.proposed_provider_queries[1].query_id == "CASE-test-001/Q-002"
    assert out.proposed_provider_queries[1].gap_id == "CASE-test-001/GAP-002"


def test_localize_drops_orphan_queries():
    """Queries whose gap_id is not in the case gaps must be dropped."""
    case = CDICase(
        case_id="CASE-test-002",
        chart_excerpt="x",
        documentation_gaps=[
            DocumentationGap(
                gap_id="GAP-001",
                description="ok",
                why_it_matters="ok",
                evidence_span=_mk_evidence(),
            ),
        ],
        proposed_provider_queries=[
            ProviderQuery(
                query_id="Q-001",
                gap_id="GAP-001",  # valid
                topic="t",
                reason="r",
                evidence_span=_mk_evidence(),
                query_text="q",
            ),
            ProviderQuery(
                query_id="Q-002",
                gap_id="GAP-099",  # orphan — must be dropped
                topic="t",
                reason="r",
                evidence_span=_mk_evidence(),
                query_text="q",
            ),
        ],
    )

    out = _localize_child_ids(case)
    assert len(out.proposed_provider_queries) == 1
    assert out.proposed_provider_queries[0].query_id == "CASE-test-002/Q-001"


def test_localize_preserves_already_scoped_ids():
    """If IDs already start with the case_id, leave them alone."""
    case = CDICase(
        case_id="CASE-test-003",
        chart_excerpt="x",
        documentation_gaps=[
            DocumentationGap(
                gap_id="CASE-test-003/GAP-001",
                description="ok",
                why_it_matters="ok",
                evidence_span=_mk_evidence(),
            ),
        ],
        proposed_provider_queries=[
            ProviderQuery(
                query_id="CASE-test-003/Q-001",
                gap_id="CASE-test-003/GAP-001",
                topic="t",
                reason="r",
                evidence_span=_mk_evidence(),
                query_text="q",
            ),
        ],
    )

    out = _localize_child_ids(case)
    assert out.documentation_gaps[0].gap_id == "CASE-test-003/GAP-001"
    assert out.proposed_provider_queries[0].query_id == "CASE-test-003/Q-001"


def test_assert_case_consistent_detects_zero_gap_n_query():
    """Mock case model with 0 gaps + 4 queries must be flagged."""
    @dataclass
    class _Gap:
        id: str
    @dataclass
    class _Query:
        id: str
        gap_id: str
        lifecycle_state: str = "DRAFT"
    @dataclass
    class _Case:
        id: str
        gaps_: list = None
        queries_: list = None
        def __post_init__(self):
            self.gaps_ = self.gaps_ or []
            self.queries_ = self.queries_ or []

    bad = _Case(id="CASE-bad", gaps_=[], queries_=[
        _Query(id="CASE-bad/Q-001", gap_id="GAP-001"),
        _Query(id="CASE-bad/Q-002", gap_id="GAP-002"),
    ])
    issues = assert_case_consistent(bad)
    # Two issues: orphan refs + 0-gap-N-query pathology
    assert any("0 Gap + N Query" in i for i in issues)
    assert any("references gap_id=GAP-001" in i for i in issues)


def test_derive_case_state_auto_pass():
    """0 gaps + 0 queries → AUTO_PASS."""
    @dataclass
    class _Case:
        id: str
        gaps_: list
        queries_: list
    out = derive_case_state(_Case(id="CASE-x", gaps_=[], queries_=[]))
    assert out == "AUTO_PASS"


def test_derive_case_state_inconsistent():
    """0 gaps + N queries → INCONSISTENT."""
    @dataclass
    class _Query:
        lifecycle_state: str
    @dataclass
    class _Case:
        id: str
        gaps_: list
        queries_: list
    out = derive_case_state(_Case(id="CASE-x", gaps_=[], queries_=[_Query("DRAFT")]))
    assert out == "INCONSISTENT"


def test_derive_case_state_pending_review():
    """gaps>0 + queries in DRAFT → PENDING_CDI_REVIEW."""
    @dataclass
    class _Query:
        lifecycle_state: str
    @dataclass
    class _Case:
        id: str
        gaps_: list
        queries_: list
    out = derive_case_state(_Case(
        id="CASE-x",
        gaps_=[object()],
        queries_=[_Query("DRAFT"), _Query("PENDING_CDI_REVIEW")],
    ))
    assert out == "PENDING_CDI_REVIEW"


@pytest.mark.asyncio
async def test_persist_case_localizes_ids_real_db(tmp_path):
    """End-to-end: persist a case with placeholder IDs and read back
    to confirm IDs are case-scoped and referential integrity holds."""
    case = CDICase(
        case_id="CASE-pytest-localize",
        chart_excerpt="患者咳嗽",
        documentation_gaps=[
            DocumentationGap(
                gap_id="GAP-001",
                description="d",
                why_it_matters="w",
                evidence_span=_mk_evidence(),
            ),
        ],
        proposed_provider_queries=[
            ProviderQuery(
                query_id="Q-001",
                gap_id="GAP-001",
                topic="t",
                reason="r",
                evidence_span=_mk_evidence(),
                query_text="q",
            ),
        ],
    )

    async with AsyncSessionLocal() as db:
        try:
            case_model = await persist_case(
                db, case,
                organization_id="test-org",
                created_by_user_id="test-user",
            )
            # Confirm IDs were localized
            gaps_q = await db.execute(select(DocumentationGapModel).where(
                DocumentationGapModel.case_id == case.case_id
            ))
            gaps = gaps_q.scalars().all()
            assert len(gaps) == 1
            assert gaps[0].id == "CASE-pytest-localize/GAP-001"

            queries_q = await db.execute(select(ProviderQueryModel).where(
                ProviderQueryModel.case_id == case.case_id
            ))
            queries = queries_q.scalars().all()
            assert len(queries) == 1
            assert queries[0].id == "CASE-pytest-localize/Q-001"
            assert queries[0].gap_id == "CASE-pytest-localize/GAP-001"

            # Consistency assertion must pass
            from app.services.cdi_persistence import load_case
            loaded = await load_case(db, case.case_id)
            issues = assert_case_consistent(loaded)
            assert issues == [], f"unexpected issues: {issues}"
        finally:
            # Cleanup
            from sqlalchemy import delete
            await db.execute(delete(ProviderQueryModel).where(
                ProviderQueryModel.case_id == case.case_id))
            await db.execute(delete(DocumentationGapModel).where(
                DocumentationGapModel.case_id == case.case_id))
            await db.execute(delete(CDICaseModel).where(
                CDICaseModel.id == case.case_id))
            await db.commit()
