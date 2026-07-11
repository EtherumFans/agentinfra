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
        "prior-auth",
        "referral-gen",
    }
    missing = expected_new - agent_ids
    assert not missing, f"Missing GAP-13-02 agents in hub: {missing}"


@pytest.mark.asyncio
async def test_hub_has_at_least_24_agents(client):
    """Post GAP-13-02 fix, hub total ≥ 24 (9 runnable + 15 metadata-only)."""
    resp = await client.get("/api/icoder/agents/hub")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 24, (
        f"Hub total {body['total']} < 24; GAP-13-02 packs not loaded"
    )


@pytest.mark.asyncio
async def test_gap_13_02_agents_are_metadata_only(client):
    """The 10 GAP-13-02 agents must be runnable=false (metadata-only)."""
    resp = await client.get("/api/icoder/agents/hub")
    body = resp.json()
    by_id = {a["agent_id"]: a for a in body.get("agents", [])}

    expected_new = [
        "icd10-navigator",
        "rule-explainer",
        "surgical-registry",
        "icu-summary",
        "triage",
        "med-reconciliation",
        "discharge-edu",
        "nursing-handoff",
        "prior-auth",
        "referral-gen",
    ]
    for aid in expected_new:
        assert aid in by_id, f"{aid} missing from hub"
        assert by_id[aid]["runnable"] is False, (
            f"{aid} should be metadata-only (runnable=false)"
        )
        assert by_id[aid]["maturity"] == "metadata-only", (
            f"{aid} maturity should be 'metadata-only'"
        )
