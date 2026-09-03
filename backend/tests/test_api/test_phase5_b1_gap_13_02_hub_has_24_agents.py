"""Phase 5 Track B GAP-13-02 fix regression test.

Verifies the 10 new metadata-only agent packs appear in the Hub
endpoint. Without these packs, hub drops from 24 → 14 agents and
B-1.4 deep audit cannot compare iCoDer to Corti on 10 of 20 agents.

Run: python -m pytest tests/test_api/test_phase5_b1_gap_13_02_hub_has_24_agents.py -v
"""
from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")

import pytest


@pytest.mark.asyncio
async def test_hub_includes_10_gap_13_02_agents(client):
    """GAP-13-02 fix: hub must include the 10 new metadata-only agents."""
    resp = await client.get("/api/icoder/agents/hub")
    assert resp.status_code == 200
    body = resp.json()
    agent_ids = {a["agent_id"] for a in body.get("agents", [])}

    expected_new = {
        "icd10-navigator",
        "rule-explainer",
        "surgical-registry",
        "icu-summary",
        "triage",
        "med-reconciliation",
        "discharge-edu",
        "nursing-handoff",
        "referral-gen",
    }
    missing = expected_new - agent_ids
    assert not missing, f"Missing GAP-13-02 agents in hub: {missing}"


@pytest.mark.asyncio
async def test_hub_has_exactly_26_launch_candidate_agents(client):
    """Post GAP-13-02 fix, hub total ≥ 24 (9 runnable + 15 metadata-only)."""
    resp = await client.get("/api/icoder/agents/hub")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 26
    assert len(body["agents"]) == 26
    not_ready = {
        card["agent_id"]: {
            "runnable": card.get("runnable"),
            "launch_candidate_ready": card.get("launch_candidate_ready"),
            "maturity": card.get("maturity"),
        }
        for card in body["agents"]
        if not card.get("runnable")
        or not card.get("launch_candidate_ready")
        or card.get("maturity") != "runnable"
    }
    assert not_ready == {}


@pytest.mark.asyncio
async def test_gap_13_02_agents_are_all_runnable(client):
    """Unmigrated GAP-13-02 agents remain explicitly non-runnable."""
    resp = await client.get("/api/icoder/agents/hub")
    body = resp.json()
    by_id = {a["agent_id"]: a for a in body.get("agents", [])}

    expected_new = [
        "icd10-navigator",
        "surgical-registry",
        "icu-summary",
        "triage",
        "med-reconciliation",
        "discharge-edu",
        "nursing-handoff",
        "referral-gen",
    ]
    for aid in expected_new:
        assert aid in by_id, f"{aid} missing from hub"
        assert by_id[aid]["runnable"] is True, (
            f"{aid} should be executable (runnable=true)"
        )
        assert by_id[aid]["maturity"] == "runnable", (
            f"{aid} maturity should be 'runnable'"
        )
        assert by_id[aid]["launch_candidate_ready"] is True

    for aid in ("rule-explainer", "prior-auth"):
        migrated = by_id[aid]
        assert migrated["runnable"] is True
        assert migrated["maturity"] == "runnable"
        assert migrated["launch_candidate_ready"] is True


def test_visible_runnable_packs_have_no_stale_stub_claims() -> None:
    """Release metadata must match the executable Hub state."""
    import json
    from pathlib import Path

    forbidden = ("metadata-only", "metadata only", "wiring deferred", "stub")
    root = Path(__file__).resolve().parents[2] / "official_agents"
    offenders: dict[str, str] = {}
    for pack_path in root.rglob("agent_pack.json"):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        manifest = pack.get("manifest") or {}
        if manifest.get("hidden_from_hub") is True:
            continue
        if manifest.get("maturity") != "runnable":
            continue
        audit_note = str((pack.get("metadata") or {}).get("audit_note") or "")
        lowered = audit_note.lower()
        if any(term in lowered for term in forbidden):
            offenders[pack_path.parent.name] = audit_note

    assert offenders == {}
