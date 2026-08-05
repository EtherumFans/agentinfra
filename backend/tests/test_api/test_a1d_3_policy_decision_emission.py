"""A1D.3 — A1C-B-010 + A1C-B-011 policy_decision + purpose_of_use emission.

Predecessor state (Phase A1C.6 §1 row 12): ``details.decision`` + 4 sibling
fields (decision_reason / rbac_role / abac_purpose_match / tenant_match)
were DESIGN — only DENY-side decisions were logged via HTTPException
handlers. Allow-side decisions (200/2xx responses) were not consistently
logged, so an auditor could see every denial but not every grant.

Predecessor state (Phase A1C.6 §1 row 5): ``details.purpose_of_use`` was
DESIGN — RBAC honored; ABAC ``request.state.purpose_of_use`` propagation
to ``audit_log.details`` deferred.

A1D.3 closes both by:
  - Adding a ``policy_decision`` parameter to ``log_action``. When set,
    the dict is merged into ``details``. The expected shape is::

        {
            "decision": "allow" | "deny",
            "decision_reason": str,
            "rbac_role": str,           # UserRole.value or "system"
            "abac_purpose_match": str,   # "match" | "mismatch" | "n/a"
            "tenant_match": str,         # "match" | "mismatch"
        }

  - Adding a ``purpose_of_use`` parameter to ``log_action``. When set,
    ``details.purpose_of_use`` is populated.

The signature additions are KEYWORD-only with default ``None``, so the
40+ existing call sites do not need to change. Pilot env wiring (Phase
after A1D) will opt-in per route.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class _FakeDB:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)


@pytest.fixture
def unpaused_audit_env(monkeypatch):
    monkeypatch.delenv("ICODER_AUDIT_WRITE_PAUSED", raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────
# §1 policy_decision — structured dict lands in audit_log.details
# ─────────────────────────────────────────────────────────────────────


def test_log_action_accepts_policy_decision_allow(
    unpaused_audit_env, monkeypatch,
):
    """Allow-side policy_decision populates details.decision + siblings."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="patient_context.create",
        resource_type="patient_context",
        resource_id="pc-1",
        organization_id="org-test",
        policy_decision={
            "decision": "allow",
            "decision_reason": "rbac role admin permitted",
            "rbac_role": "admin",
            "abac_purpose_match": "match",
            "tenant_match": "match",
        },
    ))

    assert len(db.added) == 1
    details = db.added[0].details
    assert details["decision"] == "allow"
    assert details["rbac_role"] == "admin"
    assert details["abac_purpose_match"] == "match"
    assert details["tenant_match"] == "match"
    assert details["decision_reason"] == "rbac role admin permitted"


def test_log_action_accepts_policy_decision_deny(
    unpaused_audit_env,
):
    """Deny-side policy_decision also lands in details (defense-in-depth)."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="patient_context.create",
        resource_type="patient_context",
        resource_id="pc-1",
        organization_id="org-test",
        policy_decision={
            "decision": "deny",
            "decision_reason": "rbac role coder lacks permission",
            "rbac_role": "coder",
            "abac_purpose_match": "n/a",
            "tenant_match": "match",
        },
    ))

    details = db.added[0].details
    assert details["decision"] == "deny"
    assert details["rbac_role"] == "coder"


def test_log_action_preserves_existing_details_when_policy_decision_set(
    unpaused_audit_env,
):
    """policy_decision merges into details; caller-supplied details preserved."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="agent_run.start",
        resource_type="agent_run",
        resource_id="run-1",
        organization_id="org-test",
        details={"agent_id": "agent-1", "trace_id": "t-1"},
        policy_decision={
            "decision": "allow",
            "rbac_role": "clinician",
        },
    ))

    details = db.added[0].details
    # Caller details preserved
    assert details["agent_id"] == "agent-1"
    assert details["trace_id"] == "t-1"
    # policy_decision merged in
    assert details["decision"] == "allow"
    assert details["rbac_role"] == "clinician"


def test_log_action_without_policy_decision_unchanged(unpaused_audit_env):
    """Regression: callers that don't pass policy_decision still work."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="user.login",
        resource_type="user",
        resource_id="u-1",
        organization_id="org-test",
    ))

    details = db.added[0].details
    # details may be None or empty dict (depending on redactor), but must NOT
    # contain decision/rbac_role keys
    if details:
        assert "decision" not in details
        assert "rbac_role" not in details


# ─────────────────────────────────────────────────────────────────────
# §2 purpose_of_use — ABAC dimension lands in details
# ─────────────────────────────────────────────────────────────────────


def test_log_action_accepts_purpose_of_use(unpaused_audit_env):
    """purpose_of_use parameter populates details.purpose_of_use."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="patient_context.create",
        resource_type="patient_context",
        resource_id="pc-1",
        organization_id="org-test",
        purpose_of_use="treatment",
    ))

    details = db.added[0].details
    assert details["purpose_of_use"] == "treatment"


def test_log_action_without_purpose_of_use_unchanged(unpaused_audit_env):
    """Regression: callers that don't pass purpose_of_use still work."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="user.login",
        resource_type="user",
        resource_id="u-1",
        organization_id="org-test",
    ))

    details = db.added[0].details
    if details:
        assert "purpose_of_use" not in details


# ─────────────────────────────────────────────────────────────────────
# §3 policy_decision + purpose_of_use — combined
# ─────────────────────────────────────────────────────────────────────


def test_log_action_accepts_policy_decision_and_purpose_of_use_together(
    unpaused_audit_env,
):
    """Both new parameters can be set in the same call (full ABAC+RBAC row)."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="documents.submit",
        resource_type="document",
        resource_id="doc-1",
        organization_id="org-test",
        policy_decision={
            "decision": "allow",
            "rbac_role": "clinician",
            "abac_purpose_match": "match",
            "tenant_match": "match",
        },
        purpose_of_use="treatment",
    ))

    details = db.added[0].details
    assert details["decision"] == "allow"
    assert details["rbac_role"] == "clinician"
    assert details["purpose_of_use"] == "treatment"
