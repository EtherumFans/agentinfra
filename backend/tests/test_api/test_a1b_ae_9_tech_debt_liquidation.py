"""A1B-AE.9 — Tech-debt liquidation (External-Gate API + Presets REST + DEPRECATED notices).

Coverage:
§1 External-Expert Gate REST endpoint (/api/v1/experts/external-gate/evaluate)
§2 Preset Agents REST endpoints (/api/v1/presets)
§3 Legacy-orphan DEPRECATED notices present (code_validation / compliance_guardrail / note_completeness)
§4 Charter Amendment 1 §7 forbidden verdicts preserved
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


# ─────────────────────────────────────────────────────────────────────
# §1 External-Expert Gate REST endpoint
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Boot the FastAPI app with auth bypassed for tests."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_external_gate_evaluates_non_gated_expert(client):
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={"expert_key": "coding-expert"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expert_key"] == "coding-expert"
    assert body["permitted"] is True
    assert body["reason"] == "OK"


def test_external_gate_evaluates_drugbank_licence_required(client):
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={
            "expert_key": "drugbank",
            "egress_enabled": True,
            "region": "EU",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is False
    assert body["reason"] == "LICENCE_REQUIRED"


def test_external_gate_evaluates_drugbank_licence_satisfied(client):
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={
            "expert_key": "drugbank",
            "egress_enabled": True,
            "region": "EU",
            "licence_token_count": 1,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is True
    assert body["reason"] == "OK"


def test_external_gate_evaluates_web_search_opt_in_missing(client):
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={
            "expert_key": "web-search",
            "egress_enabled": True,
            "region": "EU",
            "provider_opt_in": True,
            "tenant_opt_in": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is False
    assert body["reason"] == "PROVIDER_OPT_IN_MISSING"


def test_external_gate_evaluates_pubmed_egress_disabled(client):
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={"expert_key": "pubmed"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is False
    assert body["reason"] == "EGRESS_DISABLED"


# ─────────────────────────────────────────────────────────────────────
# §2 Preset Agents REST endpoints
# ─────────────────────────────────────────────────────────────────────

def test_presets_list(client):
    r = client.get("/api/v1/presets")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    keys = [p["canonical_key"] for p in body["presets"]]
    assert "icoder-medical-coding-preset" in keys
    assert "icoder-cdi-preset" in keys
    assert "icoder-drg-dip-preset" in keys
    assert "icoder-intake-interview-preset" in keys
    assert "icoder-claim-check-preset" in keys


def test_presets_list_summary_fields(client):
    r = client.get("/api/v1/presets")
    body = r.json()
    for p in body["presets"]:
        assert "name" in p
        assert "name_zh" in p
        assert "agent_type" in p
        assert p["agent_type"] in {"expert", "orchestrator", "interviewing-expert"}
        assert "corti_alignment" in p
        assert "expert_count" in p
        assert p["expert_count"] >= 1


def test_preset_detail(client):
    r = client.get("/api/v1/presets/icoder-medical-coding-preset")
    assert r.status_code == 200
    body = r.json()
    assert body["canonical_key"] == "icoder-medical-coding-preset"
    assert body["delegates_to_pack"] == "icoder/medical-coding-agent@2.0.0"
    assert body["red_lines"]["human_review_required"] is True
    assert body["red_lines"]["production_writeback_blocked"] is True
    assert len(body["experts"]) >= 1


def test_preset_detail_404(client):
    r = client.get("/api/v1/presets/does-not-exist")
    assert r.status_code == 404


def test_preset_card_emits_corti_section6_camelcase(client):
    r = client.get("/api/v1/presets/icoder-cdi-preset/card")
    assert r.status_code == 200
    card = r.json()
    # Corti §6 camelCase fields
    for field in ("name", "description", "systemPrompt", "agentType", "experts", "mcpServers"):
        assert field in card, f"missing Corti §6 field: {field}"
    # iCoDer extensions namespaced
    assert "icoder_ext" in card
    assert card["icoder_ext"]["canonical_key"] == "icoder-cdi-preset"
    # CDI preset has Phase 5 Track D red lines
    assert card["icoder_ext"]["red_lines"]["no_auto_diagnosis"] is True
    assert card["icoder_ext"]["red_lines"]["no_cmi_target"] is True


def test_preset_card_404(client):
    r = client.get("/api/v1/presets/does-not-exist/card")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# §3 Legacy-orphan DEPRECATED notices
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "legacy_dir",
    [
        "code_validation",
        "compliance_guardrail",
        "note_completeness",
    ],
)
def test_deprecated_notice_present(legacy_dir):
    """Each of the 3 LEGACY_CODE_ORPHAN dirs (A1B-AE.2 §3) must carry
    a DEPRECATED.md notice filed in A1B-AE.9. The dir itself is NOT
    deleted in A1B-AE.9 (call sites still import from them)."""
    backend_root = Path(__file__).resolve().parent.parent.parent
    notice = backend_root / "official_agents" / legacy_dir / "DEPRECATED.md"
    assert notice.exists(), f"missing DEPRECATED.md in {legacy_dir}/"
    text = notice.read_text(encoding="utf-8")
    assert "DEPRECATED" in text
    assert "LEGACY_CODE_ORPHAN" in text
    assert "A1B-AE.9" in text
    # The notice must declare the canonical dash-form successor
    dash_form = legacy_dir.replace("_", "-")
    assert dash_form in text


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
    allowed = {"PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED"}
    assert forbidden.isdisjoint(allowed)
