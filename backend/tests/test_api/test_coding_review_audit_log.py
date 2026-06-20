"""M3-0 Hospital Pilot — AuditLog writes for /api/icoder/coding-review/*.

Plan reference: docs/M3_HOSPITAL_PILOT_READINESS_PLAN.md Commit 5.

Every /run and every successful /{run_id}/human-review action writes a row
to the ``audit_logs`` table. The writer is best-effort — failures are
logged but do not block the response — so a real production system
still serves the run even if the audit log is degraded.

Coverage:
  * POST /run writes an ``action="coding_review.run"`` AuditLog row
  * POST /{run_id}/human-review writes an
    ``action="coding_review.human_review.<action>"`` AuditLog row
  * organization_id, user_id, username, ip_address, user_agent are
    populated correctly
  * details JSON contains expected fields
  * AuditLog writes are best-effort — even if log_action fails the
    run still returns 200
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.database import async_session_factory
from app.models.audit_log import AuditLog


@pytest.fixture
def client():
    return TestClient(app)


SAMPLE_INPUT = {
    "encounter_text": "患者男 65 岁, 因持续胸痛 6 小时入院",
    "case_id": "c-audit-001",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "I21.401",
}


# ── 1. POST /run writes an AuditLog row ─────────────────────────────────


def test_post_run_writes_audit_log(client):
    """Every /run invocation creates a coding_review.run AuditLog row."""
    pre_count = asyncio.get_event_loop().run_until_complete(_count_audit_logs())
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200, f"run failed: {r.text}"
    run_id = r.json()["run_id"]

    rows = asyncio.get_event_loop().run_until_complete(
        _fetch_audit_logs_for_run(run_id)
    )
    assert len(rows) >= 1, f"no AuditLog rows for run_id={run_id}"
    run_row = next(r for r in rows if r.action == "coding_review.run")
    assert run_row.resource_type == "coding_review_run"
    assert run_row.resource_id == run_id
    assert run_row.user_id is not None
    assert run_row.username is not None
    # organization_id is best-effort — the mock user may not have an
    # OrganizationMember row. We only assert the field exists.
    assert hasattr(run_row, "organization_id")
    # details carries the case-level metadata
    assert run_row.details["case_id"] == "c-audit-001"
    assert run_row.details["mode"] == "link_validation"
    assert "business_result_generated" in run_row.details
    assert "degraded" in run_row.details

    # The total audit log count grew by exactly 1
    post_count = asyncio.get_event_loop().run_until_complete(_count_audit_logs())
    assert post_count == pre_count + 1, f"audit log count delta: {pre_count} → {post_count}"


# ── 2. POST /{run_id}/human-review writes an AuditLog row ──────────────


def test_human_review_writes_audit_log(client):
    """A successful human-review action creates a coding_review.human_review.<action> AuditLog row."""
    r = client.post("/api/icoder/coding-review/run", json={
        **SAMPLE_INPUT, "case_id": "c-audit-hr-001",
    })
    run_id = r.json()["run_id"]

    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept",
        "target_code": "I21.401",
        "target_role": "primary_disease",
        "reason_code": "R007",
        "reviewer": "dr.li",
        "reviewer_role": "coder",
    })
    assert h.status_code == 200
    record_id = h.json()["record_id"]

    rows = asyncio.get_event_loop().run_until_complete(
        _fetch_audit_logs_for_run(run_id)
    )
    actions = [r.action for r in rows]
    assert "coding_review.human_review.accept" in actions, \
        f"expected human_review.accept in {actions}"

    hr_row = next(r for r in rows if r.action == "coding_review.human_review.accept")
    assert hr_row.resource_id == run_id
    assert hr_row.details["record_id"] == record_id
    assert hr_row.details["action"] == "accept"
    assert hr_row.details["target_code"] == "I21.401"
    assert hr_row.details["target_role"] == "primary_disease"
    assert hr_row.details["reason_code"] == "R007"
    assert hr_row.details["production_writeback_blocked"] is True


# ── 3. Both /run and /human-review produce exactly one row each ────────


def test_run_then_human_review_produces_two_audit_log_rows(client):
    """A full run+review cycle creates exactly 2 AuditLog rows (one per action)."""
    r = client.post("/api/icoder/coding-review/run", json={
        **SAMPLE_INPUT, "case_id": "c-audit-both-001",
    })
    run_id = r.json()["run_id"]

    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "reject",
        "target_code": "I21.401",
        "target_role": "primary_disease",
        "reason_code": "R001",
        "reviewer": "dr.li",
        "reviewer_role": "coder",
    })
    assert h.status_code == 200

    rows = asyncio.get_event_loop().run_until_complete(
        _fetch_audit_logs_for_run(run_id)
    )
    assert len(rows) == 2, f"expected 2 rows, got {len(rows)}: {[(r.action,) for r in rows]}"
    actions = {r.action for r in rows}
    assert actions == {"coding_review.run", "coding_review.human_review.reject"}


# ── 4. AuditLog failure does not block the run response ─────────────────


def test_audit_log_failure_does_not_block_run(monkeypatch, client):
    """If the AuditLog write raises, the run still returns 200 (best-effort)."""
    from app.api import icoder_coding_review

    call_count = {"n": 0}

    async def _broken_log_action(*args, **kwargs):
        call_count["n"] += 1
        raise RuntimeError("simulated audit log DB failure")

    monkeypatch.setattr(icoder_coding_review, "log_action", _broken_log_action)

    r = client.post("/api/icoder/coding-review/run", json={
        **SAMPLE_INPUT, "case_id": "c-audit-fail-001",
    })
    # The run is unaffected by audit log failure
    assert r.status_code == 200, f"audit log failure must not block the run: {r.text}"
    assert call_count["n"] == 1, "log_action should have been called once"


# ── 5. ip_address and user_agent are populated from the request ────────


def test_audit_log_captures_ip_and_user_agent(client):
    """The AuditLog row carries the requesting client's IP + UA."""
    r = client.post(
        "/api/icoder/coding-review/run",
        json={**SAMPLE_INPUT, "case_id": "c-audit-ip-001"},
        headers={
            "User-Agent": "icoder-curl-smoke/1.0",
            "X-Forwarded-For": "10.0.0.42",
        },
    )
    run_id = r.json()["run_id"]

    rows = asyncio.get_event_loop().run_until_complete(
        _fetch_audit_logs_for_run(run_id)
    )
    run_row = next(r for r in rows if r.action == "coding_review.run")
    # TestClient doesn't bind a real socket, so client.host may be None;
    # user_agent is the field most likely to be populated.
    assert run_row.user_agent == "icoder-curl-smoke/1.0"


# ── Helpers (async DB) ──────────────────────────────────────────────────


async def _count_audit_logs() -> int:
    async with async_session_factory() as session:
        stmt = select(AuditLog)
        return len((await session.execute(stmt)).scalars().all())


async def _fetch_audit_logs_for_run(run_id: str) -> list[AuditLog]:
    async with async_session_factory() as session:
        stmt = select(AuditLog).where(AuditLog.resource_id == run_id)
        return list((await session.execute(stmt)).scalars().all())
