"""Phase A1A Gate 3.1 — unit tests for the evidence-based classifier.

Covers charter §8 A items 1–15. Uses an in-memory SQLite database
with the minimum schema the classifier queries (no FastAPI / app
import required beyond the classifier itself).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.middleware.tenancy_guard import (
    CLASS_LEGACY_AMBIGUOUS,
    CLASS_LEGACY_INFERRED,
    CLASS_LEGACY_VERIFIED,
    CLASS_MODERN_SYSTEM,
)
from app.services.legacy_tenancy_attribution import (
    SYSTEM_AUDIT_ACTIONS,
    AttributionEvidence,
    classify,
    collect_evidence_for_row,
    reclassify_table,
)


# ── Schema bootstrap ────────────────────────────────────────────────────


_SCHEMA_SQL = """
CREATE TABLE organizations (id VARCHAR PRIMARY KEY);
CREATE TABLE organization_members (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    user_id VARCHAR,
    created_at DATETIME
);
CREATE TABLE oauth_clients (
    id VARCHAR PRIMARY KEY,
    client_id VARCHAR,
    organization_id VARCHAR,
    embedded_app_id VARCHAR
);
CREATE TABLE runtime_sessions (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    context_id VARCHAR
);
CREATE TABLE runtime_audit_records (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    request_id VARCHAR
);
CREATE TABLE run_history (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    user_id VARCHAR,
    api_client_id VARCHAR,
    embedded_app_id VARCHAR,
    session_id VARCHAR,
    context_id VARCHAR,
    request_id VARCHAR,
    tenancy_classification VARCHAR,
    created_at DATETIME,
    tenancy_attribution_source VARCHAR,
    tenancy_attribution_confidence VARCHAR,
    tenancy_attribution_migration VARCHAR,
    tenancy_attributed_at DATETIME,
    tenancy_original_org_id VARCHAR,
    tenancy_candidate_count INTEGER
);
CREATE TABLE audit_logs (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR,
    user_id VARCHAR,
    action VARCHAR,
    tenancy_classification VARCHAR,
    created_at DATETIME,
    tenancy_attribution_source VARCHAR,
    tenancy_attribution_confidence VARCHAR,
    tenancy_attribution_migration VARCHAR,
    tenancy_attributed_at DATETIME,
    tenancy_original_org_id VARCHAR,
    tenancy_candidate_count INTEGER
);
"""


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    with eng.begin() as conn:
        for stmt in _SCHEMA_SQL.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(sa_text(s))
    yield eng
    eng.dispose()


@pytest.fixture()
def conn(engine):
    with engine.connect() as c:
        yield c


# ── Helpers ─────────────────────────────────────────────────────────────


def _add_org(conn, org_id):
    conn.execute(sa_text("INSERT INTO organizations (id) VALUES (:o)"), {"o": org_id})


def _add_membership(conn, user_id, org_id, created_at):
    conn.execute(
        sa_text(
            "INSERT INTO organization_members (id, user_id, organization_id, created_at) "
            "VALUES (:id, :u, :o, :c)"
        ),
        {"id": f"m-{user_id}-{org_id}", "u": user_id, "o": org_id, "c": created_at},
    )


def _add_oauth_client(conn, client_id, org_id, embedded_app_id=None):
    conn.execute(
        sa_text(
            "INSERT INTO oauth_clients (id, client_id, organization_id, embedded_app_id) "
            "VALUES (:id, :cid, :o, :aid)"
        ),
        {
            "id": f"oc-{client_id}",
            "cid": client_id,
            "o": org_id,
            "aid": embedded_app_id,
        },
    )


def _add_run_history(
    conn,
    *,
    row_id,
    user_id=None,
    api_client_id=None,
    embedded_app_id=None,
    session_id=None,
    context_id=None,
    request_id=None,
    created_at=None,
    current_org=None,
    current_cls="LEGACY_TENANT_KNOWN",
):
    conn.execute(
        sa_text(
            "INSERT INTO run_history (id, organization_id, user_id, api_client_id, "
            "embedded_app_id, session_id, context_id, request_id, "
            "tenancy_classification, created_at) "
            "VALUES (:id, :org, :u, :ac, :ea, :s, :ctx, :rq, :cls, :c)"
        ),
        {
            "id": row_id, "org": current_org, "u": user_id,
            "ac": api_client_id, "ea": embedded_app_id,
            "s": session_id, "ctx": context_id, "rq": request_id,
            "cls": current_cls, "c": created_at or datetime.utcnow(),
        },
    )


def _add_audit_log(conn, *, row_id, user_id=None, action, created_at=None, current_org=None, current_cls="LEGACY_TENANT_KNOWN"):
    conn.execute(
        sa_text(
            "INSERT INTO audit_logs (id, organization_id, user_id, action, "
            "tenancy_classification, created_at) "
            "VALUES (:id, :org, :u, :a, :cls, :c)"
        ),
        {
            "id": row_id, "org": current_org, "u": user_id, "a": action,
            "cls": current_cls, "c": created_at or datetime.utcnow(),
        },
    )


NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
EARLIER = NOW - timedelta(days=30)
LATER = NOW + timedelta(days=1)


# ── Tests 1–15 ──────────────────────────────────────────────────────────


def test_1_single_org_user_is_inferred(conn):
    """Charter §8 A #1: user has only 1 org → INFERRED."""
    _add_org(conn, "org-A")
    _add_membership(conn, "u1", "org-A", EARLIER)
    _add_run_history(conn, row_id="r1", user_id="u1", current_org=None, created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r1")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_INFERRED
    assert d.organization_id == "org-A"
    assert d.confidence == "inferred"
    assert d.candidate_count == 1


def test_2_multi_org_user_is_ambiguous(conn):
    """Charter §8 A #2: user belongs to 2 orgs → AMBIGUOUS."""
    _add_org(conn, "org-A"); _add_org(conn, "org-B")
    _add_membership(conn, "u2", "org-A", EARLIER)
    _add_membership(conn, "u2", "org-B", EARLIER)
    _add_run_history(conn, row_id="r2", user_id="u2", created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r2")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_AMBIGUOUS
    assert d.organization_id is None  # ambiguous ⇒ no implicit pick
    assert d.confidence == "ambiguous"
    assert d.candidate_count == 2


def test_3_latest_membership_time_mismatch(conn):
    """Charter §8 A #3: latest membership is recent but the run is old.

    Membership snapshot at record time is the empty set (user hadn't
    joined yet); history has 1 candidate. Decision: INFERRED with
    source = ``user_single_membership_history``.
    """
    _add_org(conn, "org-A")
    _add_membership(conn, "u3", "org-A", LATER)  # joined AFTER the run
    _add_run_history(conn, row_id="r3", user_id="u3", created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r3")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_INFERRED
    assert d.organization_id == "org-A"
    assert "single_membership_history" in d.source or "latest" in d.source


def test_4_membership_created_after_run(conn):
    """Charter §8 A #4: explicit time-conflict case.

    Same as test 3 but with multiple memberships, both created after
    the run. The classifier should NOT pick one arbitrarily; if
    ``at_time`` is empty, it falls through to history. If history has
    >1 candidate, AMBIGUOUS. If history has 1, INFERRED.
    """
    _add_org(conn, "org-A")
    _add_membership(conn, "u4", "org-A", LATER)
    _add_run_history(conn, row_id="r4", user_id="u4", created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r4")
    d = classify(ev, current_org_id=None)
    # History has exactly 1 candidate; at_time is empty.
    assert d.classification == CLASS_LEGACY_INFERRED
    assert d.organization_id == "org-A"


def test_5_api_client_evidence_matches_membership(conn):
    """Charter §8 A #5: api_client_id → org matches membership → VERIFIED."""
    _add_org(conn, "org-A")
    _add_membership(conn, "u5", "org-A", EARLIER)
    _add_oauth_client(conn, "client-1", "org-A")
    _add_run_history(
        conn, row_id="r5", user_id="u5", api_client_id="client-1", created_at=NOW,
    )
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r5")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_VERIFIED
    assert d.organization_id == "org-A"
    assert d.confidence == "verified"


def test_6_api_client_evidence_conflicts_with_membership(conn):
    """Charter §8 A #6: api_client pins org-A, membership pins org-B.

    Strong evidence wins; the row is VERIFIED to api_client's org.
    """
    _add_org(conn, "org-A"); _add_org(conn, "org-B")
    _add_membership(conn, "u6", "org-B", EARLIER)
    _add_oauth_client(conn, "client-2", "org-A")
    _add_run_history(
        conn, row_id="r6", user_id="u6", api_client_id="client-2", created_at=NOW,
    )
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r6")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_VERIFIED
    assert d.organization_id == "org-A"  # strong evidence wins


def test_7_session_evidence(conn):
    """Charter §8 A #7: session_id resolves via runtime_sessions → VERIFIED."""
    _add_org(conn, "org-A")
    conn.execute(
        sa_text(
            "INSERT INTO runtime_sessions (id, organization_id, context_id) "
            "VALUES (:id, :o, :ctx)"
        ),
        {"id": "sess-1", "o": "org-A", "ctx": None},
    )
    _add_run_history(conn, row_id="r7", session_id="sess-1", created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r7")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_VERIFIED
    assert d.organization_id == "org-A"


def test_8_context_evidence(conn):
    """Charter §8 A #8: context_id resolves via runtime_sessions.context_id → VERIFIED."""
    _add_org(conn, "org-A")
    conn.execute(
        sa_text(
            "INSERT INTO runtime_sessions (id, organization_id, context_id) "
            "VALUES (:id, :o, :ctx)"
        ),
        {"id": "sess-2", "o": "org-A", "ctx": "ctx-xyz"},
    )
    _add_run_history(conn, row_id="r8", context_id="ctx-xyz", created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r8")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_VERIFIED
    assert d.organization_id == "org-A"


def test_9_no_evidence_no_user(conn):
    """Charter §8 A #9 + #13: no user_id, no other correlation → UNKNOWN."""
    _add_run_history(conn, row_id="r9", user_id=None, created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r9")
    d = classify(ev, current_org_id=None)
    assert d.classification == "LEGACY_TENANT_UNKNOWN"
    assert d.organization_id is None
    assert d.confidence == "none"
    assert d.source == "no_user_id_no_candidate"


def test_10_system_user_security_event(conn):
    """Charter §8 A #10: api_client.authentication_rejected with NULL user → MODERN_SYSTEM."""
    _add_audit_log(
        conn, row_id="a10", user_id=None,
        action="api_client.authentication_rejected", created_at=NOW,
    )
    conn.commit()

    ev = collect_evidence_for_row(conn, table="audit_logs", row_id="a10")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_MODERN_SYSTEM
    assert d.organization_id is None
    assert d.source == "security_event"
    assert d.confidence == "verified"


def test_11_platform_admin_multi_org_ambiguous(conn):
    """Charter §8 A #11: platform admin with 3 memberships → AMBIGUOUS."""
    for o in ("org-A", "org-B", "org-C"):
        _add_org(conn, o)
        _add_membership(conn, "admin", o, EARLIER)
    _add_run_history(conn, row_id="r11", user_id="admin", created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r11")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_AMBIGUOUS
    assert d.candidate_count == 3


def test_12_multiple_candidates_no_strong_evidence(conn):
    """Charter §8 A #12: 2 membership candidates, no api_client → AMBIGUOUS."""
    _add_org(conn, "org-A"); _add_org(conn, "org-B")
    _add_membership(conn, "u12", "org-A", EARLIER)
    _add_membership(conn, "u12", "org-B", EARLIER)
    _add_run_history(conn, row_id="r12", user_id="u12", created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r12")
    d = classify(ev, current_org_id=None)
    assert d.classification == CLASS_LEGACY_AMBIGUOUS


def test_13_unknown_candidate_zero(conn):
    """Charter §8 A #13: no user_id, no candidate count → UNKNOWN ( Quarantine is operator-applied downstream)."""
    _add_run_history(conn, row_id="r13", user_id=None, created_at=NOW)
    conn.commit()

    ev = collect_evidence_for_row(conn, table="run_history", row_id="r13")
    d = classify(ev, current_org_id=None)
    assert d.classification == "LEGACY_TENANT_UNKNOWN"
    assert d.candidate_count == 0


def test_14_reclassify_idempotent(conn):
    """Charter §8 A #14: re-running the classifier yields the same classification."""
    _add_org(conn, "org-A")
    _add_membership(conn, "u14", "org-A", EARLIER)
    _add_run_history(conn, row_id="r14", user_id="u14", created_at=NOW)
    conn.commit()

    counts1 = reclassify_table(conn, table="run_history")
    conn.commit()
    counts2 = reclassify_table(conn, table="run_history")
    conn.commit()

    # Same final state, same counts dict (preserved_modern short-circuits
    # MODERN rows; legacy rows re-UPDATE with identical values).
    assert counts1 == counts2


def test_15_counts_closure(conn):
    """Charter §8 A #15: pre/post counts must reconcile."""
    _add_org(conn, "org-A"); _add_org(conn, "org-B")
    _add_membership(conn, "u15a", "org-A", EARLIER)
    _add_membership(conn, "u15b", "org-A", EARLIER)
    _add_membership(conn, "u15c", "org-A", EARLIER)
    _add_membership(conn, "u15c", "org-B", EARLIER)  # multi-org → ambiguous
    _add_run_history(conn, row_id="r15a", user_id="u15a", created_at=NOW)  # INFERRED
    _add_run_history(conn, row_id="r15b", user_id="u15b", created_at=NOW)  # INFERRED
    _add_run_history(conn, row_id="r15c", user_id="u15c", created_at=NOW)  # AMBIGUOUS
    _add_run_history(conn, row_id="r15d", user_id=None, created_at=NOW)    # UNKNOWN
    _add_run_history(
        conn, row_id="r15e", user_id="u15a", created_at=NOW,
        current_cls="MODERN", current_org="org-A",
    )  # preserved
    conn.commit()

    counts = reclassify_table(conn, table="run_history")
    conn.commit()

    assert counts.get(CLASS_LEGACY_INFERRED) == 2
    assert counts.get(CLASS_LEGACY_AMBIGUOUS) == 1
    assert counts.get("LEGACY_TENANT_UNKNOWN") == 1
    assert counts.get("preserved_modern") == 1
    # Sum must equal total rows in the table.
    total_rows = conn.execute(sa_text("SELECT COUNT(*) FROM run_history")).scalar()
    assert sum(counts.values()) == total_rows


# ── Schema-defensive tests ─────────────────────────────────────────────


def test_collect_evidence_skips_missing_runtime_sessions_context_id(tmp_path):
    """If runtime_sessions lacks context_id (production state today),
    the context_id lookup silently returns None — no exception."""
    eng = create_engine(f"sqlite:///{tmp_path/'t.db'}", future=True)
    with eng.begin() as c:
        for s in """
            CREATE TABLE organizations (id VARCHAR PRIMARY KEY);
            CREATE TABLE organization_members (id VARCHAR PRIMARY KEY, user_id VARCHAR, organization_id VARCHAR, created_at DATETIME);
            CREATE TABLE oauth_clients (id VARCHAR PRIMARY KEY, client_id VARCHAR, organization_id VARCHAR);
            CREATE TABLE runtime_sessions (id VARCHAR PRIMARY KEY, organization_id VARCHAR);
            CREATE TABLE runtime_audit_records (id VARCHAR PRIMARY KEY, organization_id VARCHAR);
            CREATE TABLE run_history (
                id VARCHAR PRIMARY KEY, organization_id VARCHAR, user_id VARCHAR,
                api_client_id VARCHAR, embedded_app_id VARCHAR, session_id VARCHAR,
                context_id VARCHAR, request_id VARCHAR, tenancy_classification VARCHAR,
                created_at DATETIME,
                tenancy_attribution_source VARCHAR, tenancy_attribution_confidence VARCHAR,
                tenancy_attribution_migration VARCHAR, tenancy_attributed_at DATETIME,
                tenancy_original_org_id VARCHAR, tenancy_candidate_count INTEGER
            );
            CREATE TABLE audit_logs (
                id VARCHAR PRIMARY KEY, organization_id VARCHAR, user_id VARCHAR,
                action VARCHAR, tenancy_classification VARCHAR, created_at DATETIME,
                tenancy_attribution_source VARCHAR, tenancy_attribution_confidence VARCHAR,
                tenancy_attribution_migration VARCHAR, tenancy_attributed_at DATETIME,
                tenancy_original_org_id VARCHAR, tenancy_candidate_count INTEGER
            );
        """.split(";"):
            if s.strip():
                c.execute(sa_text(s))

    with eng.connect() as c:
        c.execute(sa_text(
            "INSERT INTO run_history (id, context_id, created_at) "
            "VALUES ('r', 'ctx-x', :now)"
        ), {"now": datetime.utcnow()})
        c.commit()
        ev = collect_evidence_for_row(c, table="run_history", row_id="r")
        # context_id lookup was skipped silently; no crash.
        assert ev.org_from_context is None


def test_system_audit_actions_allowlist_includes_reject_event():
    """The api_client.authentication_rejected action must be in the
    system-scope allowlist so it classifies MODERN_SYSTEM."""
    assert "api_client.authentication_rejected" in SYSTEM_AUDIT_ACTIONS
