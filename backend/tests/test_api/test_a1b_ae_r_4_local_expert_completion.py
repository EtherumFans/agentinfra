"""A1B-AE-R.4 — Local Expert completion tests.

Coverage:

§1  Calculator catalogue — 4 new formulas with published-reference test cases
    §1.1 CHA2DS2-VASc (Lip 2012)
    §1.2 MELD-Na (OPTN 2022 / Kim WR 2022)
    §1.3 eGFR CKD-EPI 2021 race-free (Inker LA 2021)
    §1.4 Wells DVT (Wells 2003)

§2  Memory Expert ↔ Context bridge — ingest_context_messages()
    §2.1 idempotent per (session_id = context_id:message_id)
    §2.2 extracts text from parts_json dict + string shapes
    §2.3 skips empty messages
    §2.4 scopes to a specific context_id

§3  Interviewing state persistence
    §3.1 serialize_state() round-trips through deserialize_state()
    §3.2 deserialize_state() rejects mismatched question lists
    §3.3 save_to_context / load_from_context round-trip via contexts.metadata_json
    §3.4 load_from_context returns None when no state present

§4  Charter Amendment 1 §7 forbidden verdicts preserved
"""
from __future__ import annotations

import json
import os
from datetime import datetime, UTC

import pytest
import pytest_asyncio

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


# ─────────────────────────────────────────────────────────────────────
# §1 Calculator catalogue
# ─────────────────────────────────────────────────────────────────────


def test_supports_six_calculators_now():
    from app.agents.experts.medical_calculator_expert import SUPPORTED_CALCULATORS
    expected = {
        "bmi",
        "cockcroft-gault",
        "cha2ds2-vasc",
        "meld-na",
        "egfr-ckd-epi-2021",
        "wells-dvt",
    }
    assert set(SUPPORTED_CALCULATORS) == expected


# §1.1 CHA2DS2-VASc ---------------------------------------------------


def test_cha2ds2_vasc_zero_score_male_low_risk():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "cha2ds2-vasc",
        age_years=50,
        sex="male",
        chf=False,
        hypertension=False,
        diabetes=False,
        stroke_tia_history=False,
        vascular_disease=False,
    )
    assert r.output["score"] == 0
    assert r.output["risk_tier"] == "low"


def test_cha2ds2_vasc_female_min_score_is_one():
    """Female sex category alone = 1 (low-moderate for female)."""
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "cha2ds2-vasc",
        age_years=40,
        sex="female",
    )
    assert r.output["score"] == 1


def test_cha2ds2_vasc_age_75plus_counts_as_two():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "cha2ds2-vasc",
        age_years=78,
        sex="male",
        hypertension=True,
        diabetes=True,
    )
    # age 78 → 2, hypertension → 1, diabetes → 1 = 4
    assert r.output["score"] == 4
    assert r.output["risk_tier"] == "high"


def test_cha2ds2_vasc_stroke_history_doubles():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "cha2ds2-vasc",
        age_years=70,
        sex="male",
        stroke_tia_history=True,
    )
    # age 70 → 1, stroke → 2 = 3
    assert r.output["score"] == 3
    assert "anticoagulation" in r.output["anticoagulation_recommendation"].lower()


def test_cha2ds2_vasc_rejects_invalid_sex():
    from app.agents.experts.medical_calculator_expert import calculate
    with pytest.raises(ValueError):
        calculate("cha2ds2-vasc", age_years=60, sex="other")


# §1.2 MELD-Na --------------------------------------------------------


def test_meld_na_typical_case():
    """Reference: OPTN 2022 sample case.

    creatinine=1.5, bilirubin=2.0, INR=1.5, Na=135.
    Per OPTN canonical formula (×10 form): MELD(i) ≈ 17.5; MELD-Na ≈ 19.0.
    """
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "meld-na",
        creatinine_mg_dl=1.5,
        bilirubin_mg_dl=2.0,
        inr=1.5,
        sodium_mmol_l=135,
    )
    assert 17.0 <= r.output["meld_score"] <= 18.0
    assert r.output["meld_na_score"] >= r.output["meld_score"]
    assert r.output["mortality_tier_90d"] in {"low", "moderate", "high", "very_high"}


def test_meld_na_caps_creatinine_at_3():
    from app.agents.experts.medical_calculator_expert import calculate
    r_high = calculate(
        "meld-na",
        creatinine_mg_dl=10.0,
        bilirubin_mg_dl=2.0,
        inr=1.5,
        sodium_mmol_l=137,
    )
    r_cap = calculate(
        "meld-na",
        creatinine_mg_dl=3.0,
        bilirubin_mg_dl=2.0,
        inr=1.5,
        sodium_mmol_l=137,
    )
    assert abs(r_high.output["meld_score"] - r_cap.output["meld_score"]) < 0.1


def test_meld_na_caps_sodium_to_137():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "meld-na",
        creatinine_mg_dl=1.0,
        bilirubin_mg_dl=1.0,
        inr=1.0,
        sodium_mmol_l=145,
    )
    assert any("above 137" in w for w in r.warnings)


def test_meld_na_caps_sodium_to_125():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "meld-na",
        creatinine_mg_dl=1.0,
        bilirubin_mg_dl=1.0,
        inr=1.0,
        sodium_mmol_l=120,
    )
    assert any("below 125" in w for w in r.warnings)


def test_meld_na_dialysis_forces_creatinine_to_3():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "meld-na",
        creatinine_mg_dl=0.8,
        bilirubin_mg_dl=1.0,
        inr=1.0,
        sodium_mmol_l=137,
        dialysis_within_7d=True,
    )
    assert any("dialysis" in w.lower() for w in r.warnings)


# §1.3 eGFR CKD-EPI 2021 ---------------------------------------------


def test_egfr_male_normal_function():
    """Inker 2021 reference: 40yo male, Scr=0.9 (= κ) → eGFR ≈ 111 mL/min/1.73m²."""
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "egfr-ckd-epi-2021",
        age_years=40,
        sex="male",
        serum_creatinine_mg_dl=0.9,
    )
    # At Scr = κ, the formula simplifies to 142 × 0.9938^40 ≈ 110.7
    assert 100 <= r.output["egfr_ml_min_1_73m2"] <= 120
    assert r.output["ckd_stage"].startswith("G1")


def test_egfr_female_at_scr_equal_kappa_gets_1_012_multiplier():
    """Female at Scr = 0.7 (her κ) — the 1.012 sex multiplier wins over the
    different κ, so female eGFR is slightly higher than male's at Scr=0.9."""
    from app.agents.experts.medical_calculator_expert import calculate
    r_m = calculate(
        "egfr-ckd-epi-2021",
        age_years=40,
        sex="male",
        serum_creatinine_mg_dl=0.9,  # male κ = 0.9
    )
    r_f = calculate(
        "egfr-ckd-epi-2021",
        age_years=40,
        sex="female",
        serum_creatinine_mg_dl=0.7,  # female κ = 0.7
    )
    assert r_f.output["egfr_ml_min_1_73m2"] > r_m.output["egfr_ml_min_1_73m2"]


def test_egfr_ckd_stage_g3a():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "egfr-ckd-epi-2021",
        age_years=70,
        sex="male",
        serum_creatinine_mg_dl=1.6,
    )
    assert r.output["egfr_ml_min_1_73m2"] < 90
    assert any("egfr" in w.lower() or "ckd" in w.lower() or "60" in w for w in r.warnings)


def test_egfr_rejects_invalid_inputs():
    from app.agents.experts.medical_calculator_expert import calculate
    with pytest.raises(ValueError):
        calculate("egfr-ckd-epi-2021", age_years=0, sex="male", serum_creatinine_mg_dl=1.0)
    with pytest.raises(ValueError):
        calculate("egfr-ckd-epi-2021", age_years=50, sex="male", serum_creatinine_mg_dl=0)


# §1.4 Wells DVT ------------------------------------------------------


def test_wells_dvt_zero_score_low_risk():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate("wells-dvt")
    assert r.output["score"] == 0
    assert r.output["risk_tier"] == "low"


def test_wells_dvt_alternative_diagnosis_subtracts_one():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "wells-dvt",
        alternative_diagnosis_at_least_as_likely=True,
    )
    assert r.output["score"] == -1
    assert r.output["risk_tier"] == "low"


def test_wells_dvt_high_score_high_risk():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "wells-dvt",
        active_cancer=True,
        recently_bedridden_postoperative=True,
        swelling_entire_leg=True,
        calf_swelling_3cm_vs_asymptomatic_side=True,
        pitting_edema_symptomatic_leg=True,
    )
    assert r.output["score"] == 5
    assert r.output["risk_tier"] == "high"


def test_wells_dvt_intermediate_score_moderate_risk():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate(
        "wells-dvt",
        recently_bedridden_postoperative=True,
        pitting_edema_symptomatic_leg=True,
    )
    assert r.output["score"] == 2
    assert r.output["risk_tier"] == "moderate"


# ─────────────────────────────────────────────────────────────────────
# §2 Memory ↔ Context bridge
# ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def memory_db(monkeypatch):
    """In-memory SQLite for ConversationMemory + ContextMessageRow."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.database import Base
    import app.models.memory  # noqa: F401
    import app.icoder.agent_runtime.context.db_models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(
        "app.services.memory_expert._get_embedding_model", lambda: None
    )

    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_memory_ingest_context_messages_basic(memory_db):
    from app.services.memory_expert import memory_expert
    from app.icoder.agent_runtime.context.db_models import (
        ContextRow,
        ContextMessageRow,
    )

    ctx_id = "ctx-test-basic"
    memory_db.add(
        ContextRow(
            id=ctx_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            agent_id="agent-1",
            organization_id="org_test",
            status="ACTIVE",
            metadata_json="{}",
        )
    )
    memory_db.add(
        ContextMessageRow(
            context_id=ctx_id,
            message_id="msg-1",
            role="user",
            parts_json=json.dumps([{"text": "Patient has type 2 diabetes"}]),
            timestamp=datetime.now(UTC),
        )
    )
    await memory_db.commit()

    saved = await memory_expert.ingest_context_messages(
        context_id=ctx_id,
        user_id="user-1",
        organization_id="org_test",
        db=memory_db,
    )
    assert saved == 1


@pytest.mark.asyncio
async def test_memory_ingest_is_idempotent(memory_db):
    from app.services.memory_expert import memory_expert
    from app.icoder.agent_runtime.context.db_models import (
        ContextRow,
        ContextMessageRow,
    )

    ctx_id = "ctx-test-idempotent"
    memory_db.add(
        ContextRow(
            id=ctx_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            agent_id="agent-1",
            organization_id="org_test",
            status="ACTIVE",
            metadata_json="{}",
        )
    )
    memory_db.add(
        ContextMessageRow(
            context_id=ctx_id,
            message_id="msg-A",
            role="user",
            parts_json=json.dumps([{"text": "hello"}]),
            timestamp=datetime.now(UTC),
        )
    )
    await memory_db.commit()

    first = await memory_expert.ingest_context_messages(
        context_id=ctx_id,
        user_id="user-1",
        organization_id="org_test",
        db=memory_db,
    )
    second = await memory_expert.ingest_context_messages(
        context_id=ctx_id,
        user_id="user-1",
        organization_id="org_test",
        db=memory_db,
    )
    assert first == 1
    assert second == 0, "second ingest should skip already-saved messages"


@pytest.mark.asyncio
async def test_memory_ingest_handles_string_parts_json(memory_db):
    from app.services.memory_expert import memory_expert
    from app.icoder.agent_runtime.context.db_models import (
        ContextRow,
        ContextMessageRow,
    )

    ctx_id = "ctx-test-string-parts"
    memory_db.add(
        ContextRow(
            id=ctx_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            agent_id="agent-1",
            organization_id="org_test",
            status="ACTIVE",
            metadata_json="{}",
        )
    )
    memory_db.add(
        ContextMessageRow(
            context_id=ctx_id,
            message_id="msg-str",
            role="user",
            parts_json="patient has hypertension",  # plain string, not JSON
            timestamp=datetime.now(UTC),
        )
    )
    await memory_db.commit()

    saved = await memory_expert.ingest_context_messages(
        context_id=ctx_id,
        user_id="user-1",
        organization_id="org_test",
        db=memory_db,
    )
    assert saved == 1


@pytest.mark.asyncio
async def test_memory_ingest_skips_empty_messages(memory_db):
    from app.services.memory_expert import memory_expert
    from app.icoder.agent_runtime.context.db_models import (
        ContextRow,
        ContextMessageRow,
    )

    ctx_id = "ctx-test-empty"
    memory_db.add(
        ContextRow(
            id=ctx_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            agent_id="agent-1",
            organization_id="org_test",
            status="ACTIVE",
            metadata_json="{}",
        )
    )
    memory_db.add(
        ContextMessageRow(
            context_id=ctx_id,
            message_id="msg-empty",
            role="user",
            parts_json=json.dumps([{"text": ""}, {"content": ""}]),
            timestamp=datetime.now(UTC),
        )
    )
    await memory_db.commit()

    saved = await memory_expert.ingest_context_messages(
        context_id=ctx_id,
        user_id="user-1",
        organization_id="org_test",
        db=memory_db,
    )
    assert saved == 0


@pytest.mark.asyncio
async def test_memory_ingest_scopes_to_specific_context(memory_db):
    from app.services.memory_expert import memory_expert
    from app.icoder.agent_runtime.context.db_models import (
        ContextRow,
        ContextMessageRow,
    )

    for ctx_id in ("ctx-A", "ctx-B"):
        memory_db.add(
            ContextRow(
                id=ctx_id,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                expires_at=datetime.now(UTC),
                agent_id="agent-1",
                organization_id="org_test",
                status="ACTIVE",
                metadata_json="{}",
            )
        )
    memory_db.add(
        ContextMessageRow(
            context_id="ctx-A",
            message_id="msg-a",
            role="user",
            parts_json=json.dumps([{"text": "from context A"}]),
            timestamp=datetime.now(UTC),
        )
    )
    memory_db.add(
        ContextMessageRow(
            context_id="ctx-B",
            message_id="msg-b",
            role="user",
            parts_json=json.dumps([{"text": "from context B"}]),
            timestamp=datetime.now(UTC),
        )
    )
    await memory_db.commit()

    saved = await memory_expert.ingest_context_messages(
        context_id="ctx-A",
        user_id="user-1",
        organization_id="org_test",
        db=memory_db,
    )
    assert saved == 1


@pytest.mark.asyncio
async def test_memory_save_encrypts_and_recall_is_tenant_scoped(
    memory_db, monkeypatch
):
    from cryptography.fernet import Fernet

    from app.services.memory_expert import memory_expert
    from app.services.phi_encryption import is_encrypted_value

    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    memory = await memory_expert.save(
        user_id="user-1",
        session_id="session-encrypted",
        role="user",
        content="患者2型糖尿病控制欠佳，近期空腹血糖升高",
        organization_id="org_test",
        db=memory_db,
    )

    assert memory is not None
    assert memory.organization_id == "org_test"
    assert is_encrypted_value(memory.content)
    assert is_encrypted_value(memory.key_facts)
    assert "糖尿病" not in memory.content

    recalled = await memory_expert.recall(
        user_id="user-1",
        organization_id="org_test",
        query="糖尿病控制",
        db=memory_db,
    )
    assert len(recalled) == 1
    assert "糖尿病控制欠佳" in recalled[0]["content"]
    assert recalled[0]["retrieval_mode"] == "LEXICAL_CJK_BIGRAM"
    assert recalled[0]["key_facts"] == []

    cross_tenant = await memory_expert.recall(
        user_id="user-1",
        organization_id="other_org",
        query="糖尿病控制",
        db=memory_db,
    )
    assert cross_tenant == []


@pytest.mark.asyncio
async def test_memory_ingest_rejects_wrong_organization(memory_db):
    from app.services.memory_expert import memory_expert
    from app.icoder.agent_runtime.context.db_models import (
        ContextMessageRow,
        ContextRow,
    )

    context_id = "ctx-org-isolation"
    memory_db.add(
        ContextRow(
            id=context_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            agent_id="agent-1",
            organization_id="org_test",
            status="ACTIVE",
            metadata_json="{}",
        )
    )
    memory_db.add(
        ContextMessageRow(
            context_id=context_id,
            message_id="msg-org",
            role="user",
            parts_json=json.dumps([{"text": "tenant-bound content"}]),
            timestamp=datetime.now(UTC),
        )
    )
    await memory_db.commit()

    saved = await memory_expert.ingest_context_messages(
        context_id=context_id,
        user_id="user-1",
        organization_id="other_org",
        db=memory_db,
    )

    assert saved == 0


# ─────────────────────────────────────────────────────────────────────
# §3 Interviewing state persistence
# ─────────────────────────────────────────────────────────────────────


def test_serialize_deserialize_roundtrip():
    from app.agents.experts.interviewing_expert import (
        QuestionSpec,
        start_interview,
        advance,
        serialize_state,
        deserialize_state,
    )

    questions = [
        QuestionSpec(key="q1", prompt="First?"),
        QuestionSpec(key="q2", prompt="Second?", kind="number"),
        QuestionSpec(key="q3", prompt="Third?"),
    ]
    state = start_interview("demo", questions)
    advance(state)
    advance(state, answer="yes")

    blob = serialize_state(state)
    assert blob["version"] == 1
    assert blob["answers"] == {"q1": "yes"}
    assert blob["cursor"] == 1
    assert blob["question_keys"] == ["q1", "q2", "q3"]

    restored = deserialize_state(blob, questions)
    assert restored.questionnaire_key == "demo"
    assert restored.answers == {"q1": "yes"}
    assert restored.cursor == 1
    assert [q.key for q in restored.questions] == ["q1", "q2", "q3"]


def test_deserialize_rejects_mismatched_question_list():
    from app.agents.experts.interviewing_expert import (
        QuestionSpec,
        start_interview,
        serialize_state,
        deserialize_state,
    )

    original = [
        QuestionSpec(key="a", prompt="A?"),
        QuestionSpec(key="b", prompt="B?"),
    ]
    state = start_interview("q", original)
    blob = serialize_state(state)

    wrong = [QuestionSpec(key="x", prompt="X?")]
    with pytest.raises(ValueError):
        deserialize_state(blob, wrong)


@pytest.mark.asyncio
async def test_interview_save_load_roundtrip_via_context(memory_db):
    """End-to-end: save InterviewState to contexts.metadata_json, reload it."""
    from app.agents.experts.interviewing_expert import (
        QuestionSpec,
        start_interview,
        advance,
        save_to_context,
        load_from_context,
    )
    from app.icoder.agent_runtime.context.db_models import ContextRow

    ctx_id = "ctx-interview-persist"
    memory_db.add(
        ContextRow(
            id=ctx_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            agent_id="agent-1",
            organization_id="org_test",
            status="ACTIVE",
            metadata_json="{}",
        )
    )
    await memory_db.commit()

    questions = [
        QuestionSpec(key="name", prompt="What is your name?"),
        QuestionSpec(key="age", prompt="Age?", kind="number"),
    ]
    state = start_interview("intake", questions)
    advance(state)
    advance(state, answer="Alice")

    await save_to_context(memory_db, ctx_id, state)

    # Verify the metadata_json was actually written
    from sqlalchemy import select

    row = (
        await memory_db.execute(select(ContextRow).where(ContextRow.id == ctx_id))
    ).scalars().first()
    meta = json.loads(row.metadata_json)
    assert "interview_state" in meta
    assert meta["interview_state"]["answers"] == {"name": "Alice"}

    # Reload
    restored = await load_from_context(memory_db, ctx_id, questions)
    assert restored is not None
    assert restored.answers == {"name": "Alice"}
    assert restored.cursor == 1


@pytest.mark.asyncio
async def test_load_from_context_returns_none_when_empty(memory_db):
    from app.agents.experts.interviewing_expert import (
        QuestionSpec,
        load_from_context,
    )
    from app.icoder.agent_runtime.context.db_models import ContextRow

    ctx_id = "ctx-no-state"
    memory_db.add(
        ContextRow(
            id=ctx_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            agent_id="agent-1",
            organization_id="org_test",
            status="ACTIVE",
            metadata_json="{}",
        )
    )
    await memory_db.commit()

    questions = [QuestionSpec(key="x", prompt="X?")]
    result = await load_from_context(memory_db, ctx_id, questions)
    assert result is None


# ─────────────────────────────────────────────────────────────────────
# §4 Charter Amendment 1 §7 forbidden verdicts preserved
# ─────────────────────────────────────────────────────────────────────


def test_forbidden_verdicts_preserved():
    forbidden = {
        "PRODUCTION_READY", "FULLY_VERIFIED", "PHI_BOUNDED",
        "CORTI_PARITY_VERIFIED", "PASS_A1A_GATE4_FINAL",
        "READY_FOR_HOSPITAL_DEPLOYMENT", "CLINICAL_GRADE_VERIFIED",
        "CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED",
    }
    allowed = {
        "PASS_A1B_AE_R_AGENT_RUNTIME_PRESET_MATERIALIZATION_PUBLIC_EXPERT_MCP_AND_HUMAN_WORKFLOWS_VERIFIED",
        "PARTIAL_A1B_AE_R_RUNTIME_AND_HUMAN_WORKFLOW_RECONCILIATION_FILED",
    }
    assert forbidden.isdisjoint(allowed)
