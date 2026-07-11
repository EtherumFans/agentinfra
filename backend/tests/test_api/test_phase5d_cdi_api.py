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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_cdi_health(client: TestClient) -> None:
    r = client.get("/api/v1/cdi/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["router"] == "cdi"
    assert "POST /runs" in body["endpoints"]
    assert "no_medical_coding_calls" in body["boundaries_enforced"]


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
# GET /runs/{case_id} — stub (returns 501)
# ---------------------------------------------------------------------------


def test_get_cdi_case_stub_returns_501(client: TestClient) -> None:
    """Gate 9 stub: GET /runs/{case_id} not yet implemented."""

    r = client.get("/api/v1/cdi/runs/CASE-123")
    assert r.status_code == 501
    assert r.json()["detail"]["error"] == "not_implemented"


# ---------------------------------------------------------------------------
# POST /queries/{id}/transition — RBAC + NLQ gate
# ---------------------------------------------------------------------------


def test_transition_to_pending_review_requires_nlq_inputs(client: TestClient) -> None:
    """DRAFT → PENDING_CDI_REVIEW needs query_text + response_options +
    evidence_quote + topic for NLQ gate evaluation."""

    r = client.post(
        "/api/v1/cdi/queries/q1/transition",
        json={"to_state": "PENDING_CDI_REVIEW"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "nlq_gate_input_required"


def test_transition_to_approved_returns_sla(client: TestClient) -> None:
    """APPROVED transition computes SLA due_at."""

    r = client.post(
        "/api/v1/cdi/queries/q1/transition",
        json={"to_state": "APPROVED", "priority": "urgent"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["to_state"] == "APPROVED"
    assert body["sla_due_at"] is not None


def test_transition_to_approved_routine_priority(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/queries/q1/transition",
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
    assert body["total_cases"] == 0
    assert body["total_queries"] == 0
    assert "Gate 9 stub" in body["note"]


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


def test_create_subscription_webhook_with_url(client: TestClient) -> None:
    r = client.post(
        "/api/v1/cdi/subscriptions",
        json={
            "user_role": "auditor",
            "events": ["SLA_BREACH_CRITICAL"],
            "channel": "webhook",
            "target_url": "https://emr.example.com/cdi-webhook",
        },
    )
    assert r.status_code == 200


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
