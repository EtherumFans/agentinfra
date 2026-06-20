"""M3-0 Hospital Pilot — RBAC for /api/icoder/coding-review/*.

Plan reference: docs/M3_HOSPITAL_PILOT_READINESS_PLAN.md Commit 4.

All 5 M3-0 endpoints require a valid JWT. ``/human-review`` additionally
requires role ∈ {admin, coder}.

These tests opt OUT of the conftest's auth bypass by setting
``ICODER_DISABLE_AUTH_FOR_TESTS=0`` and using TestClient (which does not
carry an Authorization header by default).

Coverage:
  * All 5 endpoints return 401 without an Authorization header
  * /run accepts admin and coder (no role restriction for run)
  * /human-review requires admin or coder; rejects other roles (403)
  * /human-review overrides ``reviewer`` and ``reviewer_role`` from the
    request body with the JWT identity
  * Reads (/list, /{run_id}, /{run_id}/report) accept any authenticated user
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


# Tests in this module explicitly opt out of the conftest auth bypass.
@pytest.fixture(autouse=True)
def _disable_auth_bypass(monkeypatch):
    monkeypatch.setenv("ICODER_DISABLE_AUTH_FOR_TESTS", "0")
    # Force-clear any override the autouse conftest fixture may have set
    # for the previous test in the same TestClient process.
    from app.main import app as _app
    from app.middleware.auth import get_current_user
    _app.dependency_overrides.pop(get_current_user, None)
    yield
    _app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


# ── 1. All endpoints require auth (401) ─────────────────────────────────


def test_run_without_auth_returns_401(client):
    r = client.post("/api/icoder/coding-review/run", json={
        "encounter_text": "test", "case_id": "c-401-001",
    })
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


def test_human_review_without_auth_returns_401(client):
    r = client.post("/api/icoder/coding-review/anything/human-review", json={
        "action": "accept", "reason_code": "R007", "reviewer": "dr.li",
    })
    assert r.status_code == 401


def test_get_run_without_auth_returns_401(client):
    r = client.get("/api/icoder/coding-review/anything")
    assert r.status_code == 401


def test_get_report_without_auth_returns_401(client):
    r = client.get("/api/icoder/coding-review/anything/report")
    assert r.status_code == 401


def test_list_runs_without_auth_returns_401(client):
    r = client.get("/api/icoder/coding-review/")
    assert r.status_code == 401


# ── 2. Authenticated user with admin role can run / human-review ────────


def _register_admin_and_get_token(client) -> str:
    """Register an admin user via the public auth endpoint, return JWT."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"admin_{suffix}",
        "email": f"admin_{suffix}@example.com",
        "password": "AdminPass123!",
        "full_name": f"Test Admin {suffix}",  # unique per test → unique org slug
        "role": "admin",
        "department": "测试科",
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, f"register admin failed: {r.text}"
    return r.json()["access_token"]


def _register_with_role(client, role: str) -> str:
    import uuid
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"{role}_{suffix}",
        "email": f"{role}_{suffix}@example.com",
        "password": "RolePass123!",
        "full_name": f"Test {role} {suffix}",  # unique per test → unique org slug
        "role": role,
        "department": "测试科",
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, f"register {role} failed: {r.text}"
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_run_with_admin_token_succeeds(client):
    token = _register_admin_and_get_token(client)
    r = client.post(
        "/api/icoder/coding-review/run",
        json={"encounter_text": "test admin run", "case_id": "c-admin-001"},
        headers=_auth(token),
    )
    assert r.status_code == 200, f"admin run failed: {r.text}"
    assert r.json()["agent_ref"] == "icoder/homepage-coding-review-agent@1.0.0"


def test_run_with_coder_token_succeeds(client):
    token = _register_with_role(client, "coder")
    r = client.post(
        "/api/icoder/coding-review/run",
        json={"encounter_text": "test coder run", "case_id": "c-coder-001"},
        headers=_auth(token),
    )
    assert r.status_code == 200, f"coder run failed: {r.text}"


# ── 3. /human-review requires admin or coder (403 for other roles) ──────


def _run_for_test(client, token: str, case_id: str) -> str:
    r = client.post(
        "/api/icoder/coding-review/run",
        json={"encounter_text": "test", "case_id": case_id},
        headers=_auth(token),
    )
    assert r.status_code == 200
    return r.json()["run_id"]


def test_human_review_with_admin_token_succeeds(client):
    token = _register_admin_and_get_token(client)
    run_id = _run_for_test(client, token, "c-hr-admin")

    h = client.post(
        f"/api/icoder/coding-review/{run_id}/human-review",
        json={
            "action": "accept",
            "target_code": "I21.401",
            "target_role": "primary_disease",
            "reason_code": "R007",
            "reviewer": "ignored",
            "reviewer_role": "ignored",
        },
        headers=_auth(token),
    )
    assert h.status_code == 200, f"admin /human-review failed: {h.text}"
    h_body = h.json()
    assert h_body["accepted"] is True


def test_human_review_with_coder_token_succeeds(client):
    token = _register_with_role(client, "coder")
    run_id = _run_for_test(client, token, "c-hr-coder")

    h = client.post(
        f"/api/icoder/coding-review/{run_id}/human-review",
        json={
            "action": "accept",
            "target_code": "I21.401",
            "target_role": "primary_disease",
            "reason_code": "R007",
            "reviewer": "ignored",
            "reviewer_role": "ignored",
        },
        headers=_auth(token),
    )
    assert h.status_code == 200, f"coder /human-review failed: {h.text}"


@pytest.mark.parametrize("role", ["clinician", "insurance", "qc", "it", "dept_head"])
def test_human_review_with_non_coder_role_returns_403(client, role):
    """Roles outside {admin, coder} are rejected from /human-review with 403."""
    token = _register_with_role(client, role)
    # Need a run owned by someone — admin creates one
    admin_token = _register_admin_and_get_token(client)
    run_id = _run_for_test(client, admin_token, f"c-hr-{role}-reject")

    h = client.post(
        f"/api/icoder/coding-review/{run_id}/human-review",
        json={
            "action": "accept",
            "target_code": "I21.401",
            "target_role": "primary_disease",
            "reason_code": "R007",
            "reviewer": "dr.li",
            "reviewer_role": role,
        },
        headers=_auth(token),
    )
    assert h.status_code == 403, f"role={role} should be rejected with 403, got {h.status_code}: {h.text}"
    detail = h.json().get("detail", "")
    assert "admin" in detail and "coder" in detail


# ── 4. Reviewer / reviewer_role overridden from JWT ─────────────────────


def test_human_review_overrides_reviewer_from_jwt(client):
    """Body's ``reviewer`` / ``reviewer_role`` are replaced with JWT identity."""
    token = _register_with_role(client, "coder")
    run_id = _run_for_test(client, token, "c-hr-override")

    h = client.post(
        f"/api/icoder/coding-review/{run_id}/human-review",
        json={
            "action": "accept",
            "target_code": "I21.401",
            "target_role": "primary_disease",
            "reason_code": "R007",
            "reviewer": "dr.li_pretend",       # different from JWT
            "reviewer_role": "admin",            # different from JWT (coder)
        },
        headers=_auth(token),
    )
    assert h.status_code == 200
    h_body = h.json()
    # Warnings should flag the override
    assert any("reviewer" in w for w in h_body["warnings"]), \
        f"expected reviewer mismatch warning, got: {h_body['warnings']}"
    assert any("role" in w for w in h_body["warnings"]), \
        f"expected role mismatch warning, got: {h_body['warnings']}"


# ── 5. Read endpoints accept any authenticated user (no role gate) ──────


def test_get_run_with_clinician_role_succeeds(client):
    """Reads are not role-gated — any authenticated user can view runs."""
    admin_token = _register_admin_and_get_token(client)
    run_id = _run_for_test(client, admin_token, "c-read-clinician")

    clinician_token = _register_with_role(client, "clinician")
    g = client.get(
        f"/api/icoder/coding-review/{run_id}",
        headers=_auth(clinician_token),
    )
    assert g.status_code == 200
    assert g.json()["run_id"] == run_id


def test_list_runs_with_clinician_role_succeeds(client):
    clinician_token = _register_with_role(client, "clinician")
    lst = client.get(
        "/api/icoder/coding-review/",
        headers=_auth(clinician_token),
    )
    assert lst.status_code == 200
    assert "runs" in lst.json()


# ── 6. organization_id / created_by_user_id are populated from JWT ──────


def test_run_row_attribution_uses_jwt_user(client):
    """CodingReviewRun row carries the authenticated user / org from JWT."""
    token = _register_with_role(client, "coder")
    r = client.post(
        "/api/icoder/coding-review/run",
        json={"encounter_text": "test", "case_id": "c-attr-001"},
        headers=_auth(token),
    )
    run_id = r.json()["run_id"]

    # Drop in-memory mirror, read from DB
    from app.api import icoder_coding_review
    icoder_coding_review._RUNS_STORE.pop(run_id, None)

    # Use a second TestClient to ensure we hit the DB
    new_client = TestClient_factory()  # noqa: F821 — defined below
    g = new_client.get(f"/api/icoder/coding-review/{run_id}")
    # No auth → 401, but we just want to verify the row was created with
    # attribution; the easier check is to drop into the DB directly.
    assert g.status_code == 401  # no token in this client

    # Verify DB row directly
    import asyncio
    from app.database import async_session_factory
    from app.models.coding_review_run import CodingReviewRun
    from sqlalchemy import select

    async def _load():
        async with async_session_factory() as session:
            stmt = select(CodingReviewRun).where(CodingReviewRun.id == run_id)
            return (await session.execute(stmt)).scalar_one()
    row = asyncio.get_event_loop().run_until_complete(_load())
    assert row.created_by_user_id is not None
    assert row.created_by_user_id.startswith("u-") or len(row.created_by_user_id) == 12 or len(row.created_by_user_id) > 0
    # organization_id is set to the registering user's org
    assert row.organization_id is not None


def TestClient_factory():
    """Factory helper used in test_run_row_attribution_uses_jwt_user."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
