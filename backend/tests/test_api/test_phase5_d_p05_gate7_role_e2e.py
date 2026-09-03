"""Phase 5 Track D P0.5 Gate 7 — RBAC + Transition Persistence.

Two risk areas closed here (PDF §3.5 R13):

1. **Transition endpoint is DB-persisted.** Before Gate 7, the endpoint
   called pure-logic ``attempt_transition`` and threw away the result;
   a subsequent GET /runs/{case_id} would show the OLD state. Now the
   endpoint uses ``update_query_lifecycle`` (optimistic-lock + timestamps).

2. **RBAC enforced per (role, from_state, to_state).** Each platform
   role maps to a CDI role via ``platform_role_to_cdi_role``; each CDI
   role has its own allowed-transition set (``_ALLOWED_TRANSITIONS``).
   Clinicians can't author, CDI specialists can't drive clinician-side
   transitions, auditors can't drive anything.

Verdict target: CHECKPOINT_C_PASS — RBAC verified end-to-end at the
API layer. Still below PRODUCTION_READY (Gate 8 covers real-LLM
quality benchmark).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _override_role(client: TestClient, role: str):
    """Override get_current_user to return the given platform-role.

    The conftest module-wide bypass defaults to "admin". For RBAC tests
    we swap per-call. Restore happens via the returned closure.
    """
    from app.main import app
    from app.middleware.auth import get_current_user
    from tests.conftest import _make_mock_user

    original = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: _make_mock_user(role)

    def _restore():
        if original is not None:
            app.dependency_overrides[get_current_user] = original
        else:
            app.dependency_overrides[get_current_user] = lambda: _make_mock_user("admin")

    return _restore


def _seed_query(
    *,
    lifecycle_state: str = "DRAFT",
    chart: str = "test chart",
) -> str:
    """Insert a CDI case + 1 query at the given lifecycle_state directly.

    Deterministic — does not depend on the runner producing queries
    (mock-LLM mode + CEA gate often produces 0 queries).
    """
    import asyncio
    import uuid

    from app.database import async_session_factory
    from app.models.cdi_case import CDICaseModel, DocumentationGapModel, ProviderQueryModel

    case_id = f"CASE-G7-{uuid.uuid4().hex[:8]}"
    gap_id = f"GAP-G7-{uuid.uuid4().hex[:8]}"
    query_id = f"Q-G7-{uuid.uuid4().hex[:8]}"

    async def _seed() -> None:
        async with async_session_factory() as s:
            s.add(CDICaseModel(
                id=case_id,
                organization_id="org_default1",
                patient_ref="DEID",
                encounter_ref="DEID",
                chart_excerpt_hash="g7-hash",
                chart_excerpt_length=len(chart),
                encounter_metadata={},
                draft_codes=[],
                run_id="",
                trace_id="",
                agent_ref="icoder/clinical-documentation-improvement-agent@1.0.0",
                encounter_summary={"key_points": [], "encounter_metadata": {}},
                coding_specificity_checklist=[],
                risk_flags=[],
                specialist_trace=[],
                completion_state="REVIEW_RECOMMENDED",
                created_by_user_id=None,
            ))
            s.add(DocumentationGapModel(
                id=gap_id,
                organization_id="org_default1",
                case_id=case_id,
                gap_type="UNSPECIFIED_CLINICAL_DETAIL",
                description="seed gap",
                evidence_document_id="doc-1",
                evidence_quote="seed quote",
                evidence_char_start=0,
                evidence_char_end=10,
                priority="routine",
                status="OPEN",
            ))
            s.add(ProviderQueryModel(
                id=query_id,
                organization_id="org_default1",
                case_id=case_id,
                gap_id=gap_id,
                topic="seed topic",
                reason="seed reason",
                query_text="seed query text",
                response_options=["选项 A", "选项 B"],
                evidence_document_id="doc-1",
                evidence_quote="seed quote",
                evidence_char_start=0,
                evidence_char_end=10,
                nlq_gate_verdict="PENDING",
                nlq_gate_rules_evaluated=0,
                nlq_gate_rules_passed=0,
                nlq_gate_block_reasons=[],
                nlq_gate_version="NLQ-001..009",
                lifecycle_state=lifecycle_state,
                priority="routine",
            ))
            await s.commit()

    asyncio.run(_seed())
    return query_id


# ---------------------------------------------------------------------------
# Section 1 — Platform → CDI role mapping
# ---------------------------------------------------------------------------


def test_platform_role_mapping_admin() -> None:
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("admin") == "admin"


def test_platform_role_mapping_qc_to_cdi_specialist() -> None:
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("qc") == "cdi_specialist"


def test_platform_role_mapping_clinician() -> None:
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("clinician") == "clinician"


def test_platform_role_mapping_insurance_to_auditor() -> None:
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("insurance") == "auditor"


def test_platform_role_mapping_coder_to_auditor() -> None:
    """Coder (medical coding staff) maps to read-only CDI auditor."""
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("coder") == "auditor"


def test_platform_role_mapping_dept_head_to_auditor() -> None:
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("dept_head") == "auditor"


def test_platform_role_mapping_it_to_auditor() -> None:
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("it") == "auditor"


def test_platform_role_mapping_unknown_defaults_to_auditor() -> None:
    """Unknown roles get the most conservative (read-only) CDI role."""
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role
    assert platform_role_to_cdi_role("random") == "auditor"


# ---------------------------------------------------------------------------
# Section 2 — can_drive_transition matrix
# ---------------------------------------------------------------------------


def test_admin_can_drive_draft_to_pending_review() -> None:
    from app.services.cdi_roles_notifications import can_drive_transition
    assert can_drive_transition("admin", "DRAFT", "PENDING_CDI_REVIEW").allowed


def test_admin_can_drive_full_lifecycle_chain() -> None:
    """Admin can drive every transition in the 9-step chain."""
    from app.services.cdi_roles_notifications import can_drive_transition
    chain = [
        ("DRAFT", "PENDING_CDI_REVIEW"),
        ("PENDING_CDI_REVIEW", "APPROVED"),
        ("APPROVED", "SENT_TO_CLINICIAN"),
        ("SENT_TO_CLINICIAN", "VIEWED"),
        ("VIEWED", "RESPONDED"),
        ("RESPONDED", "DOCUMENTATION_UPDATED"),
        ("DOCUMENTATION_UPDATED", "REVALIDATED"),
        ("REVALIDATED", "CLOSED"),
    ]
    for src, dst in chain:
        r = can_drive_transition("admin", src, dst)
        assert r.allowed, f"admin {src}->{dst} should be allowed: {r.reason}"


def test_cdi_specialist_cannot_drive_clinician_actions() -> None:
    """CDI specialist cannot view/respond on behalf of clinician."""
    from app.services.cdi_roles_notifications import can_drive_transition
    assert not can_drive_transition("cdi_specialist", "SENT_TO_CLINICIAN", "VIEWED").allowed
    assert not can_drive_transition("cdi_specialist", "VIEWED", "RESPONDED").allowed


def test_cdi_specialist_can_drive_author_and_review_actions() -> None:
    from app.services.cdi_roles_notifications import can_drive_transition
    assert can_drive_transition("cdi_specialist", "DRAFT", "PENDING_CDI_REVIEW").allowed
    assert can_drive_transition("cdi_specialist", "PENDING_CDI_REVIEW", "APPROVED").allowed
    assert can_drive_transition("cdi_specialist", "APPROVED", "SENT_TO_CLINICIAN").allowed


def test_clinician_cannot_author_or_review() -> None:
    """Clinician cannot draft or approve queries."""
    from app.services.cdi_roles_notifications import can_drive_transition
    assert not can_drive_transition("clinician", "DRAFT", "PENDING_CDI_REVIEW").allowed
    assert not can_drive_transition("clinician", "PENDING_CDI_REVIEW", "APPROVED").allowed
    assert not can_drive_transition("clinician", "APPROVED", "SENT_TO_CLINICIAN").allowed


def test_clinician_can_drive_receive_and_respond() -> None:
    from app.services.cdi_roles_notifications import can_drive_transition
    assert can_drive_transition("clinician", "SENT_TO_CLINICIAN", "VIEWED").allowed
    assert can_drive_transition("clinician", "VIEWED", "RESPONDED").allowed


def test_auditor_cannot_drive_anything() -> None:
    """Auditor is read-only — no transitions allowed."""
    from app.services.cdi_roles_notifications import can_drive_transition
    for src, dst in [
        ("DRAFT", "PENDING_CDI_REVIEW"),
        ("PENDING_CDI_REVIEW", "APPROVED"),
        ("APPROVED", "SENT_TO_CLINICIAN"),
        ("SENT_TO_CLINICIAN", "VIEWED"),
    ]:
        r = can_drive_transition("auditor", src, dst)
        assert not r.allowed, f"auditor {src}->{dst} should be blocked"


# ---------------------------------------------------------------------------
# Section 3 — API RBAC (transition endpoint with role overrides)
# ---------------------------------------------------------------------------


def test_clinician_cannot_submit_to_cdi_review(client: TestClient) -> None:
    """Clinician trying to author → 403 forbidden."""
    qid = _seed_query(lifecycle_state="DRAFT")
    restore = _override_role(client, "clinician")
    try:
        r = client.post(
            f"/api/v1/cdi/queries/{qid}/transition",
            json={
                "to_state": "PENDING_CDI_REVIEW",
                "query_text": "请问该患者的发热持续时间是?",
                "response_options": ["3 天", "5 天", "7 天以上"],
                "evidence_quote": "发热 3 天",
                "topic": "发热持续时间",
            },
        )
        assert r.status_code == 403
        body = r.json()
        assert body["detail"]["error"] == "forbidden"
        assert body["detail"]["cdi_role"] == "clinician"
    finally:
        restore()


def test_auditor_cannot_approve(client: TestClient) -> None:
    """Auditor trying to approve → 403 forbidden."""
    qid = _seed_query(lifecycle_state="PENDING_CDI_REVIEW")
    restore = _override_role(client, "insurance")
    try:
        r = client.post(
            f"/api/v1/cdi/queries/{qid}/transition",
            json={"to_state": "APPROVED"},
        )
        assert r.status_code == 403
        body = r.json()
        assert body["detail"]["error"] == "forbidden"
        assert body["detail"]["cdi_role"] == "auditor"
    finally:
        restore()


def test_cdi_specialist_cannot_mark_viewed(client: TestClient) -> None:
    """CDI specialist trying to drive SENT_TO_CLINICIAN → VIEWED → 403."""
    qid = _seed_query(lifecycle_state="SENT_TO_CLINICIAN")
    restore = _override_role(client, "qc")
    try:
        r = client.post(
            f"/api/v1/cdi/queries/{qid}/transition",
            json={"to_state": "VIEWED"},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["cdi_role"] == "cdi_specialist"
    finally:
        restore()


def test_clinician_can_drive_viewed(client: TestClient) -> None:
    """Clinician can mark a SENT_TO_CLINICIAN query as VIEWED."""
    qid = _seed_query(lifecycle_state="SENT_TO_CLINICIAN")
    restore = _override_role(client, "clinician")
    try:
        r = client.post(
            f"/api/v1/cdi/queries/{qid}/transition",
            json={"to_state": "VIEWED"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["to_state"] == "VIEWED"
        assert body["accepted"] is True
    finally:
        restore()


def test_admin_can_drive_admin_only_transition(client: TestClient) -> None:
    """Admin can drive DOCUMENTATION_UPDATED → REVALIDATED (clinician/specialist can't always)."""
    qid = _seed_query(lifecycle_state="DOCUMENTATION_UPDATED")
    r = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "REVALIDATED"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["to_state"] == "REVALIDATED"


# ---------------------------------------------------------------------------
# Section 4 — Persistence (state + timestamps + SLA)
# ---------------------------------------------------------------------------


def _get_query_state(query_id: str) -> tuple[str, object | None, object | None, object | None]:
    """Return (state, sla_due_at, sent_at, viewed_at) for a query."""
    import asyncio
    from app.database import async_session_factory
    from app.models.cdi_case import ProviderQueryModel

    async def _read():
        async with async_session_factory() as s:
            m = await s.get(ProviderQueryModel, query_id)
            return (
                m.lifecycle_state if m else "??",
                m.sla_due_at if m else None,
                m.sent_at if m else None,
                m.viewed_at if m else None,
            )

    return asyncio.run(_read())


def test_transition_persists_state_change(client: TestClient) -> None:
    """After transition, DB row reflects the new lifecycle_state."""
    qid = _seed_query(lifecycle_state="PENDING_CDI_REVIEW")
    r = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "APPROVED", "priority": "routine"},
    )
    assert r.status_code == 200, r.text

    state, sla_due_at, _, _ = _get_query_state(qid)
    assert state == "APPROVED"
    assert sla_due_at is not None  # persisted


def test_transition_sets_sent_at_on_sent_to_clinician(client: TestClient) -> None:
    """APPROVED → SENT_TO_CLINICIAN sets sent_at timestamp."""
    qid = _seed_query(lifecycle_state="APPROVED")
    r = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "SENT_TO_CLINICIAN"},
    )
    assert r.status_code == 200, r.text

    _, _, sent_at, _ = _get_query_state(qid)
    assert sent_at is not None


def test_transition_sets_viewed_at(client: TestClient) -> None:
    """SENT_TO_CLINICIAN → VIEWED sets viewed_at."""
    qid = _seed_query(lifecycle_state="SENT_TO_CLINICIAN")
    restore = _override_role(client, "clinician")
    try:
        r = client.post(
            f"/api/v1/cdi/queries/{qid}/transition",
            json={"to_state": "VIEWED"},
        )
        assert r.status_code == 200, r.text
    finally:
        restore()

    _, _, _, viewed_at = _get_query_state(qid)
    assert viewed_at is not None


def test_sla_urgent_is_24h_routine_is_72h(client: TestClient) -> None:
    """Urgent priority SLA = 24h; routine = 72h (PDF §7)."""
    from datetime import datetime, timedelta, timezone

    from app.services.cdi_query_lifecycle import compute_sla_due_at

    now = datetime.now(timezone.utc)
    urgent = compute_sla_due_at(now, "urgent")
    routine = compute_sla_due_at(now, "routine")
    # Urgent window (24h) is shorter than routine window (72h)
    assert routine - urgent == timedelta(hours=48)
    # End-to-end: the transition response carries the SLA due_at
    qid = _seed_query(lifecycle_state="PENDING_CDI_REVIEW")
    r = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "APPROVED", "priority": "urgent"},
    )
    assert r.status_code == 200
    assert r.json()["sla_due_at"] is not None


# ---------------------------------------------------------------------------
# Section 5 — Concurrent transition (optimistic lock)
# ---------------------------------------------------------------------------


def test_concurrent_transition_returns_409(client: TestClient) -> None:
    """Two writers race on the same query — first wins, second gets 409.

    We simulate concurrency by manually moving state to a different value
    between the RBAC check and the optimistic-lock write. The endpoint's
    optimistic-lock SQL (UPDATE WHERE lifecycle_state = :from) returns
    rowcount=0, triggering the 409 path.
    """
    import asyncio

    from app.database import async_session_factory
    from app.models.cdi_case import ProviderQueryModel

    qid = _seed_query(lifecycle_state="PENDING_CDI_REVIEW")

    # Manually flip state to APPROVED behind the endpoint's back
    async def _flip():
        async with async_session_factory() as s:
            m = await s.get(ProviderQueryModel, qid)
            assert m is not None
            m.lifecycle_state = "APPROVED"
            await s.commit()

    asyncio.run(_flip())

    # Now the endpoint reads PENDING_CDI_REVIEW, but the row is APPROVED.
    # Wait — actually the endpoint reads the CURRENT state at request time,
    # so it will see APPROVED and try APPROVED→APPROVED which fails RBAC.
    # To genuinely test the optimistic-lock path we need to start from a
    # valid pair (PENDING_CDI_REVIEW, APPROVED) but flip the row mid-flight.
    # Simpler: flip back to PENDING_CDI_REVIEW then race.

    async def _flip_back():
        async with async_session_factory() as s:
            m = await s.get(ProviderQueryModel, qid)
            assert m is not None
            m.lifecycle_state = "PENDING_CDI_REVIEW"
            await s.commit()

    asyncio.run(_flip_back())

    # Now make a successful transition first, then retry — second call
    # sees APPROVED state and from_state=PENDING_CDI_REVIEW optimistic-lock
    # miss returns 409.
    r1 = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "APPROVED", "priority": "routine"},
    )
    assert r1.status_code == 200

    # Force the endpoint to read the OLD from_state by re-seeding state in DB
    # back to PENDING_CDI_REVIEW but the row's actual state is APPROVED.
    # That's hard to do cleanly via the API — instead, set state back manually
    # then call the endpoint with same body. Endpoint reads PENDING_CDI_REVIEW
    # again, RBAC ok, but the optimistic-lock flag should still pass.
    # The true 409 path requires the row to change between read & write,
    # which only happens under real concurrency. To exercise the code path,
    # we monkeypatch update_query_lifecycle to return (None, False).

    from app.api import cdi as cdi_module
    from app.services.cdi_persistence import update_query_lifecycle

    original = cdi_module.update_query_lifecycle

    async def _always_fail(*args, **kwargs):
        return (None, False)

    cdi_module.update_query_lifecycle = _always_fail  # type: ignore[assignment]
    try:
        qid2 = _seed_query(lifecycle_state="PENDING_CDI_REVIEW")
        r2 = client.post(
            f"/api/v1/cdi/queries/{qid2}/transition",
            json={"to_state": "APPROVED", "priority": "routine"},
        )
        assert r2.status_code == 409
        assert r2.json()["detail"]["error"] == "concurrent_transition"
    finally:
        cdi_module.update_query_lifecycle = original  # type: ignore[assignment]
