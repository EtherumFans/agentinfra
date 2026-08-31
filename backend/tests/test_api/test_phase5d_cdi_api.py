"""Phase 5 Track D Gate 9 — CDI REST API integration tests.

Tests:
    - POST /api/v1/cdi/runs                (orchestrator run)
    - POST /api/v1/cdi/queries/{id}/transition (RBAC + NLQ gate)
    - GET  /api/v1/cdi/audit/dashboard     (RBAC: only auditor/admin)
    - POST /api/v1/cdi/subscriptions       (event validation)
    - GET  /api/v1/cdi/health              (health check)
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
# Force the stub CDI runner in tests. The real runner needs DeepSeek to produce
# ≥1 final query; in mock-LLM mode CEA blocks most candidates, leaving 0 queries
# and breaking every transition test. Stub runner always emits 1+ query.
os.environ.setdefault("ICODER_CDI_FORCE_STUB_FOR_TESTS", "1")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _override_role(client: TestClient, role: str):
    """Override the get_current_user dependency to return the given role.

    The conftest.py module-wide bypass defaults to "admin". For RBAC
    tests we swap the role per-call.
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
            # Default conftest bypass restores on next session,
            # but to be safe we re-install the admin bypass.
            app.dependency_overrides[get_current_user] = lambda: _make_mock_user("admin")

    return _restore


def test_query_audit_queue_projection_is_role_scoped() -> None:
    from app.api.cdi import _project_query_audit_queue
    from tests.conftest import _make_mock_user

    queue = [{"query_id": "q-blocked", "status": "NEEDS_CDI_REWRITE"}]

    assert _project_query_audit_queue(queue, _make_mock_user("admin")) == queue
    assert _project_query_audit_queue(queue, _make_mock_user("qc")) == queue
    assert _project_query_audit_queue(queue, _make_mock_user("insurance")) == queue
    assert _project_query_audit_queue(queue, _make_mock_user("clinician")) == []

    unknown = _make_mock_user("clinician")
    unknown.role = "unknown_role"
    assert _project_query_audit_queue(queue, unknown) == []


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_cdi_health(client: TestClient) -> None:
    r = client.get("/api/v1/cdi/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"healthy", "degraded"}
    assert body["router"] == "cdi"
    assert "POST /runs" in body["endpoints"]
    assert "no_medical_coding_calls" in body["boundaries_enforced"]
    assert body["capabilities"]["subscription_persistence"] == "ready"


# ---------------------------------------------------------------------------
# POST /runs — orchestrator
# ---------------------------------------------------------------------------


def test_post_cdi_runs_returns_case(client: TestClient) -> None:
    """The orchestrator run endpoint returns a CDI case with gaps + queries."""

    r = client.post(
        "/api/v1/cdi/runs",
        json={
            "chart_excerpt": "患者男性,58岁,因'咳嗽咳痰伴发热 3 天'入院。"
                             "查体:T 38.5℃。痰培养:肺炎链球菌。入院诊断:肺炎。",
            "patient_ref": "MRN-001",
            "encounter_ref": "ENC-001",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case_id"].startswith("CASE-")
    assert body["completion_state"] in (
        "AUTO_PASS", "REVIEW_RECOMMENDED", "REVIEW_REQUIRED", "BLOCKED",
    )
    assert "chart_excerpt_preview" in body
    # Stub runner may produce 0+ gaps/queries — just check structure
    assert isinstance(body["documentation_gaps"], list)
    assert isinstance(body["proposed_provider_queries"], list)


def test_post_cdi_runs_with_explicit_case_id(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/runs",
        json={
            "chart_excerpt": "test chart",
            "case_id": "CASE-FIXED-001",
        },
    )
    assert r.status_code == 200
    assert r.json()["case_id"] == "CASE-FIXED-001"


def test_post_cdi_runs_rejects_empty_input(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/runs",
        json={"chart_excerpt": ""},
    )
    assert r.status_code == 422  # min_length=1


def test_post_cdi_runs_rejects_too_long_input(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/runs",
        json={"chart_excerpt": "x" * 32001},
    )
    assert r.status_code == 422  # max_length=32000


# ---------------------------------------------------------------------------
# GET /runs/{case_id} — Gate 3 real read (404 for unknown)
# ---------------------------------------------------------------------------


def test_get_cdi_unknown_case_returns_404(client: TestClient) -> None:
    """Gate 3: GET /runs/{unknown_id} now reads from DB. Unknown → 404
    (no longer 501 not_implemented; that was the Gate 9 stub)."""

    r = client.get("/api/v1/cdi/runs/CASE-DOES-NOT-EXIST-123")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "case_not_found"


def test_get_cdi_case_round_trips_after_post(client: TestClient) -> None:
    """Gate 3 closed loop: POST /runs persists, GET /runs/{id} reads it back."""

    # 1. POST to create + persist the case
    post_resp = client.post(
        "/api/v1/cdi/runs",
        json={
            "chart_excerpt": "患者男性,58岁,因咳嗽咳痰伴发热3天入院。诊断:肺炎。",
            "case_id": "CASE-ROUNDTRIP-001",
            "patient_ref": "MRN-001",
            "encounter_ref": "ENC-001",
        },
    )
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert post_data["case_id"] == "CASE-ROUNDTRIP-001"

    # 2. GET to read back
    get_resp = client.get("/api/v1/cdi/runs/CASE-ROUNDTRIP-001")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["case_id"] == "CASE-ROUNDTRIP-001"
    assert get_data["patient_ref"].startswith("PSEUDO-PATIENT-")
    assert get_data["encounter_ref"].startswith("PSEUDO-ENCOUNTER-")
    assert get_data["patient_ref"] != "MRN-001"
    assert get_data["encounter_ref"] != "ENC-001"
    # Gaps + queries count must match what POST returned
    assert len(get_data["documentation_gaps"]) == len(post_data["documentation_gaps"])
    assert len(get_data["proposed_provider_queries"]) == len(
        post_data["proposed_provider_queries"]
    )


def test_get_cdi_case_post_is_idempotent(client: TestClient) -> None:
    """Re-POSTing the same case_id does not duplicate rows."""

    # First POST creates
    r1 = client.post(
        "/api/v1/cdi/runs",
        json={
            "chart_excerpt": "Idempotency test chart.",
            "case_id": "CASE-IDEM-001",
        },
    )
    assert r1.status_code == 200

    # Second POST with same case_id returns same case (idempotent)
    r2 = client.post(
        "/api/v1/cdi/runs",
        json={
            "chart_excerpt": "Idempotency test chart.",
            "case_id": "CASE-IDEM-001",
        },
    )
    assert r2.status_code == 200
    assert r1.json()["case_id"] == r2.json()["case_id"]


# ---------------------------------------------------------------------------
# POST /queries/{id}/transition — RBAC + NLQ gate
# ---------------------------------------------------------------------------


def _seed_case_with_query(
    client: TestClient,
    *,
    chart: str = "test chart",
    lifecycle_state: str = "DRAFT",
) -> str:
    """Insert a CDI case + 1 query directly into the test DB at the given state.

    Phase 5 Track D P0.5 Gate 7: transition endpoint now fetches real
    from_state from the DB, so we must seed a persisted query before
    driving any transition.

    Going via the API (POST /runs) is unreliable here because the stub
    runner emits 0 queries, and the real runner with mock LLM also
    produces 0 (CEA blocks everything). Direct DB insert is deterministic
    and exercises exactly the persistence path the endpoint reads.
    """
    import asyncio
    import uuid

    from app.database import async_session_factory
    from app.models.cdi_case import CDICaseModel, DocumentationGapModel, ProviderQueryModel

    case_id = f"CASE-SEED-{uuid.uuid4().hex[:8]}"
    gap_id = f"GAP-SEED-{uuid.uuid4().hex[:8]}"
    query_id = f"Q-SEED-{uuid.uuid4().hex[:8]}"

    async def _seed() -> None:
        async with async_session_factory() as s:
            s.add(CDICaseModel(
                id=case_id,
                organization_id="org_default1",
                patient_ref="DEID",
                encounter_ref="DEID",
                chart_excerpt_hash="seed-hash",
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
                case_id=case_id,
                gap_type="UNSPECIFIED_CLINICAL_DETAIL",
                description="seed gap for transition test",
                evidence_document_id="doc-1",
                evidence_quote="seed quote",
                evidence_char_start=0,
                evidence_char_end=10,
                priority="routine",
                status="OPEN",
            ))
            s.add(ProviderQueryModel(
                id=query_id,
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


def test_transition_unknown_query_returns_404(client: TestClient) -> None:
    """Gate 7: unknown query_id → 404 query_not_found (was 200 stub before)."""

    r = client.post(
        "/api/v1/cdi/queries/q-does-not-exist/transition",
        json={"to_state": "APPROVED"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "query_not_found"


def test_transition_to_pending_review_requires_nlq_inputs(client: TestClient) -> None:
    """DRAFT → PENDING_CDI_REVIEW needs query_text + response_options +
    evidence_quote + topic for NLQ gate evaluation."""

    qid = _seed_case_with_query(client)
    r = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "PENDING_CDI_REVIEW"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "nlq_gate_input_required"


def test_transition_to_approved_returns_sla(client: TestClient) -> None:
    """APPROVED transition computes SLA due_at and persists it.

    Must seed at PENDING_CDI_REVIEW — that's the only state from which
    APPROVED is reachable (per _ALLOWED_TRANSITIONS).
    """

    qid = _seed_case_with_query(client, lifecycle_state="PENDING_CDI_REVIEW")
    r = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "APPROVED", "priority": "urgent"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["to_state"] == "APPROVED"
    assert body["sla_due_at"] is not None


def test_transition_to_approved_routine_priority(client: TestClient) -> None:
    qid = _seed_case_with_query(client, lifecycle_state="PENDING_CDI_REVIEW")
    r = client.post(
        f"/api/v1/cdi/queries/{qid}/transition",
        json={"to_state": "APPROVED", "priority": "routine"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sla_due_at"] is not None


# ---------------------------------------------------------------------------
# GET /audit/dashboard — RBAC
# ---------------------------------------------------------------------------


def test_audit_dashboard_for_admin(client: TestClient) -> None:
    """Admin can access audit dashboard."""

    r = client.get("/api/v1/cdi/audit/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_cases"] >= 0
    assert body["total_queries"] >= 0
    assert "Tenant-scoped" in body["note"]


def test_audit_dashboard_aggregates_persisted_workflow_rows(client: TestClient) -> None:
    """The dashboard is a real tenant aggregate, not a fixed empty shell."""

    _seed_case_with_query(client, lifecycle_state="ESCALATED")
    response = client.get("/api/v1/cdi/audit/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_cases"] >= 1
    assert body["total_queries"] >= 1
    assert body["queries_by_state"]["ESCALATED"] >= 1
    assert body["queries_by_priority"]["routine"] >= 1
    assert any(
        gap_type == "UNSPECIFIED_CLINICAL_DETAIL" and count >= 1
        for gap_type, count in body["top_gap_types"]
    )
    assert body["escalation_rate"] > 0
    assert "chart_excerpt" not in body
    assert "query_text" not in body


def test_cdi_case_query_and_dashboard_are_tenant_scoped(client: TestClient) -> None:
    """A different organization cannot observe or mutate persisted CDI data."""

    import asyncio

    from sqlalchemy import select

    from app.database import async_session_factory
    from app.main import app
    from app.middleware.auth import get_current_organization, get_current_user
    from app.models.cdi_case import ProviderQueryModel
    from tests.conftest import _make_mock_user

    query_id = _seed_case_with_query(client, lifecycle_state="PENDING_CDI_REVIEW")

    async def _case_id() -> str:
        async with async_session_factory() as session:
            return str(
                (
                    await session.execute(
                        select(ProviderQueryModel.case_id).where(
                            ProviderQueryModel.id == query_id,
                        )
                    )
                ).scalar_one()
            )

    case_id = asyncio.run(_case_id())
    original_user = app.dependency_overrides.get(get_current_user)
    original_org = app.dependency_overrides.get(get_current_organization)

    def _other_tenant_user():
        return _make_mock_user("admin")

    class _OtherTenantOrg:
        id = "org-other001"

    app.dependency_overrides[get_current_user] = _other_tenant_user
    app.dependency_overrides[get_current_organization] = lambda: _OtherTenantOrg()
    try:
        get_response = client.get(f"/api/v1/cdi/runs/{case_id}")
        assert get_response.status_code == 404

        transition_response = client.post(
            f"/api/v1/cdi/queries/{query_id}/transition",
            json={"to_state": "APPROVED"},
        )
        assert transition_response.status_code == 404

        dashboard_response = client.get("/api/v1/cdi/audit/dashboard")
        assert dashboard_response.status_code == 200
        assert dashboard_response.json()["total_cases"] == 0
        assert dashboard_response.json()["total_queries"] == 0
    finally:
        if original_user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = original_user
        if original_org is None:
            app.dependency_overrides.pop(get_current_organization, None)
        else:
            app.dependency_overrides[get_current_organization] = original_org


def test_audit_dashboard_for_qc_cdi_specialist_forbidden(client: TestClient) -> None:
    """QC (=cdi_specialist) cannot access audit dashboard (auditor-only)."""

    restore = _override_role(client, "qc")
    try:
        r = client.get("/api/v1/cdi/audit/dashboard")
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "forbidden"
    finally:
        restore()


def test_audit_dashboard_for_clinician_forbidden(client: TestClient) -> None:
    restore = _override_role(client, "clinician")
    try:
        r = client.get("/api/v1/cdi/audit/dashboard")
        assert r.status_code == 403
    finally:
        restore()


def test_audit_dashboard_for_insurance_auditor(client: TestClient) -> None:
    """INSURANCE (=auditor) can access audit dashboard."""

    restore = _override_role(client, "insurance")
    try:
        r = client.get("/api/v1/cdi/audit/dashboard")
        assert r.status_code == 200
    finally:
        restore()


# ---------------------------------------------------------------------------
# POST /subscriptions
# ---------------------------------------------------------------------------


def test_create_subscription_in_app(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/subscriptions",
        json={
            "user_role": "cdi_specialist",
            "events": ["QUERY_RESPONDED", "QUERY_ESCALATED"],
            "channel": "in_app",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subscription_id"].startswith("sub-")
    assert body["channel"] == "in_app"


def test_create_subscription_webhook_requires_url(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/subscriptions",
        json={
            "user_role": "auditor",
            "events": ["SLA_BREACH_CRITICAL"],
            "channel": "webhook",
            "target_url": "",
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "webhook_requires_url"


def test_create_subscription_webhook_with_url(client: TestClient, monkeypatch) -> None:
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    r = client.post(
        "/api/v1/cdi/subscriptions",
        json={
            "user_role": "auditor",
            "events": ["SLA_BREACH_CRITICAL"],
            "channel": "webhook",
            "target_url": "https://emr.example.com/cdi-webhook",
            "secret": "hospital-shared-secret-2026",
        },
    )
    assert r.status_code == 200
    assert "secret" not in r.json()


def test_create_subscription_webhook_fails_closed_without_encryption_key(
    client: TestClient, monkeypatch,
) -> None:
    monkeypatch.delenv("ICODER_PHI_ENCRYPTION_KEY", raising=False)
    r = client.post(
        "/api/v1/cdi/subscriptions",
        json={
            "user_role": "auditor",
            "events": ["SLA_BREACH_CRITICAL"],
            "channel": "webhook",
            "target_url": "https://emr.example.com/cdi-webhook",
            "secret": "hospital-shared-secret-2026",
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "webhook_encryption_unavailable"


def test_create_subscription_rejects_invalid_event(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/subscriptions",
        json={
            "user_role": "cdi_specialist",
            "events": ["NOT_A_REAL_EVENT"],
            "channel": "in_app",
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["error"] == "invalid_events"
    assert "NOT_A_REAL_EVENT" in body["detail"]["invalid"]


# ---------------------------------------------------------------------------
# Boundary enforcement
# ---------------------------------------------------------------------------


def test_cdi_router_does_not_call_medical_coding(client: TestClient) -> None:
    """CDI router must not invoke medical-coding tools.

    We verify by checking that the /runs response shape lacks any ICD
    code fields (those belong to medical-coding, not CDI).
    """

    r = client.post(
        "/api/v1/cdi/runs",
        json={"chart_excerpt": "test chart"},
    )
    body = r.json()
    # None of these medical-coding-only fields should be in CDI response
    assert "diagnosis_codes" not in body
    assert "icd_codes" not in body
    assert "procedure_codes" not in body
    assert "drg_code" not in body
