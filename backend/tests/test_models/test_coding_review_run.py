"""M3-0 Hospital Pilot — CodingReviewRun model tests.

Round-trip tests verifying the SQLAlchemy model persists / reloads the
full M3-0 pipeline state correctly. Tests use the in-memory SQLite
test DB wired by ``tests/conftest.py``.

Coverage:
  * Model import + table registration
  * Insert + reload — all fields round-trip
  * JSON columns (nested dicts / lists) persist as JSON
  * Default values match the M3-0 contract
  * Index existence (organization_id+created_at, case_id, trace_id)
  * Optional fields (drg_route, encounter_text_redacted) are nullable
  * 24-char hex PK length
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select


# ── Schema tests (sync) ─────────────────────────────────────────────────


def test_model_importable_and_registered():
    """CodingReviewRun imports cleanly and is registered on Base.metadata."""
    from app.models.coding_review_run import CodingReviewRun
    from app.database import Base

    assert CodingReviewRun.__tablename__ == "coding_review_runs"
    assert CodingReviewRun.__table__ in Base.metadata.tables.values()


def test_pk_length_is_24_chars():
    """PK column is String(24) to match the API run_id length."""
    from app.models.coding_review_run import CodingReviewRun

    pk_col = CodingReviewRun.__table__.c.id
    assert pk_col.type.length == 24, f"expected 24-char PK, got {pk_col.type.length}"


def test_required_columns_present():
    """Every M3-0 field is on the table."""
    from app.models.coding_review_run import CodingReviewRun

    cols = {c.name for c in CodingReviewRun.__table__.c}
    required = {
        "id", "created_at", "updated_at",
        "organization_id", "created_by_user_id",
        "agent_ref", "agent_category", "prediction_mode",
        "case_id", "trace_id", "input_source",
        "status", "degraded", "business_result_generated",
        "manual_review_required", "reason",
        "primary_diagnosis", "secondary_diagnoses", "procedures",
        "high_risk_coding_points", "evidence_chain",
        "risk_route", "safety_gate", "drg_route",
        "pipeline_stages_observed", "pipeline_stage_meta",
        "human_review_records",
        "encounter_text", "encounter_text_redacted",
        "model_version", "code_dict_version", "rule_version",
        "agent_version", "data_asset_version",
        "started_at", "finished_at",
    }
    missing = required - cols
    assert not missing, f"missing columns: {missing}"


def test_indexes_present():
    """(org, created_at), case_id, trace_id, status indexes exist."""
    from app.models.coding_review_run import CodingReviewRun

    index_names = {idx.name for idx in CodingReviewRun.__table__.indexes}
    assert "ix_coding_review_runs_org_created" in index_names
    assert "ix_coding_review_runs_case_id" in index_names
    assert "ix_coding_review_runs_trace_id" in index_names
    assert "ix_coding_review_runs_status" in index_names


def test_drg_route_is_nullable():
    """drg_route is nullable — pre-Commit-7 rows have no DRG grouping."""
    from app.models.coding_review_run import CodingReviewRun

    drg_col = CodingReviewRun.__table__.c.drg_route
    assert drg_col.nullable is True


def test_encounter_text_redacted_is_nullable():
    """encounter_text_redacted is nullable — pre-Commit-8 rows have no redacted copy."""
    from app.models.coding_review_run import CodingReviewRun

    col = CodingReviewRun.__table__.c.encounter_text_redacted
    assert col.nullable is True


def test_pipeline_stage_meta_is_nullable():
    """pipeline_stage_meta is nullable — pre-Commit-6 rows have no per-stage tool_run_id."""
    from app.models.coding_review_run import CodingReviewRun

    col = CodingReviewRun.__table__.c.pipeline_stage_meta
    assert col.nullable is True


# ── Round-trip tests (async) ────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session():
    """Yield a fresh async session; commits are explicit per test."""
    from app.database import async_session_factory

    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_insert_and_reload_minimal(db_session):
    """Insert with only required fields, reload — defaults match the contract."""
    from app.models.coding_review_run import CodingReviewRun

    run = CodingReviewRun(
        organization_id="org_default1",
        agent_ref="icoder/homepage-coding-review-agent@1.0.0",
        case_id="c-roundtrip-001",
        trace_id="t-roundtrip-001",
    )
    db_session.add(run)
    await db_session.commit()

    # 24-char hex PK auto-populated
    assert run.id is not None
    assert len(run.id) == 24
    assert all(c in "0123456789abcdef" for c in run.id)

    # Defaults
    assert run.agent_category == "official_reference_agent"
    assert run.prediction_mode == "link_validation"
    assert run.input_source == "manual"
    assert run.status == "unavailable"
    assert run.degraded is False
    assert run.business_result_generated is False
    assert run.manual_review_required is False
    assert run.reason == ""
    assert run.secondary_diagnoses == []
    assert run.procedures == []
    assert run.high_risk_coding_points == []
    assert run.evidence_chain == []
    assert run.risk_route == {}
    assert run.safety_gate == {}
    assert run.pipeline_stages_observed == []
    assert run.human_review_records == []
    assert run.primary_diagnosis is None
    assert run.drg_route is None
    assert run.pipeline_stage_meta is None
    assert run.encounter_text is None
    assert run.encounter_text_redacted is None

    # Reload via a fresh query
    stmt = select(CodingReviewRun).where(CodingReviewRun.id == run.id)
    reloaded = (await db_session.execute(stmt)).scalar_one()
    assert reloaded.id == run.id
    assert reloaded.case_id == "c-roundtrip-001"
    assert reloaded.trace_id == "t-roundtrip-001"


@pytest.mark.asyncio
async def test_insert_and_reload_full_payload(db_session):
    """Insert a fully-populated run (all M3-0 fields), reload — JSON round-trips."""
    from app.models.coding_review_run import CodingReviewRun

    primary = {
        "code": "I21.401", "description": "急性ST段抬高型心肌梗死",
        "confidence": 0.92, "category": "principal",
        "evidence": [{"text": "持续胸痛 6 小时", "kind": "auto_bootstrap"}],
        "human_review_required": False, "risk_level": "low",
    }
    secondary = [
        {"code": "I10.x00", "description": "高血压", "confidence": 0.85},
    ]
    procedures = [
        {"code": "00.6600", "description": "冠脉支架植入", "confidence": 0.88},
    ]
    high_risk = [
        {"code": "I66.901", "is_priority": True, "reason": "脑梗死",
         "human_review_required": True, "current_status": "pending"},
    ]
    evidence_chain = [
        {"span_id": "s1", "text": "持续胸痛", "match_method": "auto", "confidence": 0.8,
         "kind": "auto_bootstrap", "target_code": "I21.401"},
    ]
    risk_route = {"level": "high", "reasons": ["I66.901 priority hit"], "high_risk_hits": ["I66.901"]}
    safety_gate = {"rule_count": 2, "block_count": 0, "rules": []}
    drg_route = {
        "status": "ok", "mdc": "MDCE", "adrg": "EC1", "drg": "EC13",
        "drg_name": "经皮冠状动脉支架植入伴 MCC",
        "coverage": True, "cc_level": "MCC",
        "is_medical_or_surgical": "surgical", "reason": "ok",
    }
    pipeline_stages = [
        "document_normalizer", "evidence_fact_extractor", "candidate_generator",
        "high_risk_coding_point_checker", "risk_router", "medical_safety_gate",
    ]
    human_review = [
        {"record_id": "r1", "action": "accept", "target_code": "I21.401",
         "reviewer": "dr.li", "reason_code": "R007", "confirmed_at": "2026-06-11T00:00:00Z"},
    ]

    run = CodingReviewRun(
        organization_id="org_default1",
        agent_ref="icoder/homepage-coding-review-agent@1.0.0",
        case_id="c-full-001",
        trace_id="t-full-001",
        input_source="m2b_sample",
        status="ok",
        degraded=False,
        business_result_generated=True,
        manual_review_required=True,
        reason="HybridCodingAdapter succeeded",
        primary_diagnosis=primary,
        secondary_diagnoses=secondary,
        procedures=procedures,
        high_risk_coding_points=high_risk,
        evidence_chain=evidence_chain,
        risk_route=risk_route,
        safety_gate=safety_gate,
        drg_route=drg_route,
        pipeline_stages_observed=pipeline_stages,
        human_review_records=human_review,
        encounter_text="持续胸痛 6 小时入院, EKG 示 ST 抬高",
        model_version="deepseek-v4-flash (M3-0 interim)",
        code_dict_version="icd10cn_code_catalog 37897 codes (M3-0 baseline)",
        rule_version="medical_coding R001-R010 (M3-0 baseline)",
        created_by_user_id="u-test-001",
    )
    db_session.add(run)
    await db_session.commit()

    # Reload
    stmt = select(CodingReviewRun).where(CodingReviewRun.id == run.id)
    reloaded = (await db_session.execute(stmt)).scalar_one()

    # JSON columns: round-trip preserves structure
    assert reloaded.primary_diagnosis == primary
    assert reloaded.secondary_diagnoses == secondary
    assert reloaded.procedures == procedures
    assert reloaded.high_risk_coding_points == high_risk
    assert reloaded.evidence_chain == evidence_chain
    assert reloaded.risk_route == risk_route
    assert reloaded.safety_gate == safety_gate
    assert reloaded.drg_route == drg_route
    assert reloaded.pipeline_stages_observed == pipeline_stages
    assert reloaded.human_review_records == human_review

    # Scalars
    assert reloaded.status == "ok"
    assert reloaded.degraded is False
    assert reloaded.business_result_generated is True
    assert reloaded.manual_review_required is True
    assert reloaded.organization_id == "org_default1"
    assert reloaded.created_by_user_id == "u-test-001"
    assert reloaded.encounter_text == "持续胸痛 6 小时入院, EKG 示 ST 抬高"


@pytest.mark.asyncio
async def test_query_by_trace_id_returns_one(db_session):
    """trace_id index supports fast lookup of the run that produced a given trace."""
    from app.models.coding_review_run import CodingReviewRun

    target_trace = f"t-trace-{uuid.uuid4().hex[:8]}"
    run = CodingReviewRun(
        organization_id="org_default1",
        agent_ref="icoder/homepage-coding-review-agent@1.0.0",
        trace_id=target_trace,
        case_id="c-trace-001",
    )
    db_session.add(run)
    await db_session.commit()

    stmt = select(CodingReviewRun).where(CodingReviewRun.trace_id == target_trace)
    found = (await db_session.execute(stmt)).scalar_one()
    assert found.id == run.id
    assert found.trace_id == target_trace


@pytest.mark.asyncio
async def test_query_by_organization_id_and_created_at(db_session):
    """(organization_id, created_at) index supports tenant-scoped list queries."""
    from app.models.coding_review_run import CodingReviewRun

    runs = [
        CodingReviewRun(
            agent_ref="icoder/homepage-coding-review-agent@1.0.0",
            organization_id="org_alpha",
            case_id=f"c-alpha-{i}",
        )
        for i in range(3)
    ] + [
        CodingReviewRun(
            agent_ref="icoder/homepage-coding-review-agent@1.0.0",
            organization_id="org_beta",
            case_id=f"c-beta-{i}",
        )
        for i in range(2)
    ]
    for r in runs:
        db_session.add(r)
    await db_session.commit()

    stmt = (
        select(CodingReviewRun)
        .where(CodingReviewRun.organization_id == "org_alpha")
        .order_by(CodingReviewRun.created_at.desc())
    )
    alpha_runs = (await db_session.execute(stmt)).scalars().all()
    assert len(alpha_runs) == 3
    assert all(r.organization_id == "org_alpha" for r in alpha_runs)
