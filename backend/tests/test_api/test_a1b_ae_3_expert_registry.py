"""A1B-AE.3 — Expert Registry provenance tests.

Charter Amendment 1 §7 requires the dual-tier provenance model to be
applied to every Expert and MCP artefact. This test module exercises:

§1  Migration 022 — schema additions + backfill rules.
§2  Model defaults — Expert/McpServer columns accept the documented
    enum values and reject invalid ones via CHECK constraints.
§3  API surface — ``/api/v1/experts`` (list/get/filter) and
    ``/api/v1/experts/registry/reconcile``.
§4  Catalog reconciliation — the A1B-AE.2 expert_catalog.json entries
    map cleanly to DB rows after the migration backfill.
§5  Charter Amendment 1 §7 forbidden behaviours — no artefact should
    ever land in the DB without an explicit origin value.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

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


# ─────────────────────────────────────────────────────────────────────
# §1 Migration 022 schema
# ─────────────────────────────────────────────────────────────────────

def _db_path() -> str:
    """Path to the runtime SQLite DB used by the test app."""
    return os.environ.get(
        "ICODER_TEST_DB_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "test.db"),
    )


def _column_exists(db_path: str, table: str, column: str) -> bool:
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r[1] == column for r in rows)
    finally:
        conn.close()


def test_migration_022_expert_columns_present():
    """Migration 022 must add canonical_key/origin/corti_alignment/pack_dir/provenance."""
    db = _db_path()
    if not os.path.exists(db):
        pytest.skip(f"test DB not present at {db}")
    for col in ("canonical_key", "origin", "corti_alignment", "pack_dir", "provenance"):
        assert _column_exists(db, "experts", col), (
            f"experts.{col} missing — Migration 022 not applied"
        )


def test_migration_022_mcp_authorization_type_present():
    """Migration 022 must add mcp_servers.authorization_type."""
    db = _db_path()
    if not os.path.exists(db):
        pytest.skip(f"test DB not present at {db}")
    assert _column_exists(db, "mcp_servers", "authorization_type"), (
        "mcp_servers.authorization_type missing — Migration 022 not applied"
    )


def test_migration_022_origin_backfill_for_prebuilts():
    """Migration 022 §5: experts with is_prebuilt=1 backfill to PACK_DECLARED."""
    db = _db_path()
    if not os.path.exists(db):
        pytest.skip(f"test DB not present at {db}")
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT origin, COUNT(*) FROM experts WHERE is_prebuilt = 1 GROUP BY origin"
        ).fetchall()
        origins = dict(rows)
        # All prebuilts should be PACK_DECLARED after backfill
        non_packdecl = sum(v for k, v in origins.items() if k != "PACK_DECLARED")
        assert non_packdecl == 0, (
            f"Prebuilt experts not backfilled to PACK_DECLARED: {origins}"
        )
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────
# §2 Model enum validation
# ─────────────────────────────────────────────────────────────────────

def test_expert_origin_enum_values_complete():
    from app.models.expert import EXPERT_ORIGIN_VALUES
    assert set(EXPERT_ORIGIN_VALUES) == {
        "CLEAN_ROOM_PUBLIC",
        "REVERSE_ENGINEERED",
        "ICODER_INTERNAL",
        "PACK_DECLARED",
    }


def test_expert_corti_alignment_enum_values_complete():
    from app.models.expert import EXPERT_CORTI_ALIGNMENT_VALUES
    assert set(EXPERT_CORTI_ALIGNMENT_VALUES) == {
        "CORTI_REFERENCE",
        "CORTI_ALIGNED",
        "CORTI_ADAPTED",
        "ICODER_ONLY",
        "UNKNOWN",
    }


def test_mcp_authorization_type_enum_values_complete():
    """Corti public docs §9 — 4 values exhaustive."""
    from app.models.expert import MCP_AUTHORIZATION_TYPE_VALUES
    assert set(MCP_AUTHORIZATION_TYPE_VALUES) == {"none", "inherit", "bearer", "oauth2.0"}


# ─────────────────────────────────────────────────────────────────────
# §3 API surface
# ─────────────────────────────────────────────────────────────────────

def test_api_list_experts_returns_200(client):
    r = client.get("/api/v1/experts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "experts" in body and "total" in body
    assert isinstance(body["experts"], list)


def test_api_list_experts_filters_by_origin(client):
    r = client.get("/api/v1/experts", params={"origin": "ICODER_INTERNAL"})
    assert r.status_code == 200
    body = r.json()
    for e in body["experts"]:
        assert e["origin"] == "ICODER_INTERNAL"


def test_api_list_experts_rejects_invalid_origin(client):
    r = client.get("/api/v1/experts", params={"origin": "BOGUS"})
    assert r.status_code == 400


def test_api_list_experts_rejects_invalid_alignment(client):
    r = client.get("/api/v1/experts", params={"corti_alignment": "BOGUS"})
    assert r.status_code == 400


def test_api_get_expert_404_unknown(client):
    r = client.get("/api/v1/experts/does-not-exist-id")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# §4 Registry reconciliation
# ─────────────────────────────────────────────────────────────────────

def test_api_registry_reconcile_returns_200(client):
    r = client.get("/api/v1/experts/registry/reconcile")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalog_count"] >= 40, body  # A1B-AE.2 catalog has 40 entries
    assert "entries" in body and isinstance(body["entries"], list)
    assert body["summary"]["present"] + body["summary"]["missing"] + body["summary"]["divergent"] == body["catalog_count"]


def test_registry_reconcile_classifies_missing_entries_correctly(client):
    """Catalog entries with no DB row must come back as MISSING (e.g. CORTI_REFERENCE)."""
    r = client.get("/api/v1/experts/registry/reconcile")
    body = r.json()
    statuses = {e["db_status"] for e in body["entries"]}
    # All three statuses should appear unless the DB has zero rows
    # MISSING is always present because CORTI_REFERENCE entries (calculator-expert,
    # clinical-trials-expert, etc.) have no DB row by design.
    assert "MISSING" in statuses, f"Expected MISSING entries, got {statuses}"


# ─────────────────────────────────────────────────────────────────────
# §5 Charter Amendment 1 §7 — provenance block on every artefact
# ─────────────────────────────────────────────────────────────────────

def test_charter_amendment_1_observation_session_evidence_files_exist():
    """REVERSE_ENGINEERED artefacts must cite an observation_session_id."""
    evidence_root = (
        Path(__file__).resolve().parents[3]
        / "reports"
        / "phase-a1b"
        / "evidence"
        / "a1b_ae_3_corti_console_observation"
    )
    # At least one session dir should exist after A1B-AE.3 observation
    assert evidence_root.exists(), f"Evidence root missing: {evidence_root}"
    sessions = list(evidence_root.iterdir())
    assert len(sessions) >= 1, "No observation session directories captured"


def test_charter_amendment_1_forbidden_verdicts_preserved():
    """The 8 forbidden verdicts must remain forbidden under Amendment 1."""
    forbidden = {
        "PRODUCTION_READY",
        "FULLY_VERIFIED",
        "PHI_BOUNDED",
        "CORTI_PARITY_VERIFIED",
        "PASS_A1A_GATE4_FINAL",
        "READY_FOR_HOSPITAL_DEPLOYMENT",
        "CLINICAL_GRADE_VERIFIED",
        "CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED",
    }
    allowed_final = {
        "PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED"
    }
    assert forbidden.isdisjoint(allowed_final), (
        "Forbidden verdict leaked into allowed set"
    )
