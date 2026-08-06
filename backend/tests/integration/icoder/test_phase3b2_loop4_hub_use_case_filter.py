"""Phase 3-B2 Loop 4 — Hub `?use_case=` filter contract tests.

Verifies the Corti-style use_case filter on the Hub endpoint
(`GET /api/icoder/agents/hub?use_case=<key>`):

- No filter → all visible packs returned (11 visible: 10 metadata-only + 1 MVP).
- `?use_case=coding_revenue_cycle` → all 16 packs have this key (set en masse
  by the Loop 4 batch script), so all 11 visible packs are returned.
- `?use_case=clinical_evidence_research` → 0 packs (none declared yet).
- `?use_case=invalid_key` → 0 packs (unknown key returns empty, not 400).
- Each Hub card now includes a top-level `use_case` field (Loop 4 §1).
- Schema version bumped to "1.1" (Loop 4).
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-p11")


@pytest.fixture
def client():
    """Use context manager to trigger lifespan so PlatformRuntime + seed
    agents initialize before the test runs."""
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _get(client: TestClient, path: str):
    return client.get(path)


def test_hub_no_use_case_filter_returns_all_visible(client: TestClient):
    """No ?use_case= → all visible packs returned.

    After Phase A1B-AE added 14 net-new Corti-parity stubs + Phase A1D.5
    added claim-check stub + Phase 5 Track D added CDI entry agent,
    visible pack count is 24 (10 runnable + 14 metadata-only). 6 packs
    remain hidden (1 internal_engine + 3 expert-stub + 2 deprecated).
    Multiple use_case keys are now represented (coding_revenue_cycle,
    care_coordination, clinical_evidence, point_of_care).
    """
    response = _get(client, "/api/icoder/agents/hub")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.1"
    assert body["total"] == 24, f"Expected 24 visible packs, got {body['total']}"
    use_cases = {c.get("use_case") for c in body["agents"]}
    # coding_revenue_cycle is the dominant use_case and must be present;
    # other use_cases may also appear (care_coordination, etc.).
    assert "coding_revenue_cycle" in use_cases, use_cases


def test_hub_filter_coding_revenue_cycle_returns_all_11(client: TestClient):
    """?use_case=coding_revenue_cycle → all 17 packs that declare this key.

    Phase 3-D1 Task 5 (2026-07-06): 3 packs upgraded from metadata-only to
    runnable (code-validation / compliance-guardrail / note-completeness).

    Phase 4-F (2026-07-09): drg-analyzer / procedure-extractor / evidence-
    extractor upgraded to runnable. principal-diagnosis-review /
    discharge-summary-structuring added as runnable.

    Phase 5 Track D Gate 3 (2026-07-11): clinical-documentation-improvement-
    agent added as CORE_ENTRY_AGENT (CDI).

    After all upgrades: 10 runnable + 7 metadata-only = 17 packs under
    coding_revenue_cycle.
    """
    response = _get(client, "/api/icoder/agents/hub?use_case=coding_revenue_cycle")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 17, f"Expected 17 packs for coding_revenue_cycle, got {body['total']}"
    # All returned cards should declare this use_case at top level.
    for card in body["agents"]:
        assert card["use_case"] == "coding_revenue_cycle"
    # The original Phase 3-D1 4 runnable agents must be a SUBSET of the
    # runnable cards. Phase 4-F + Phase 5 Track D added more runnable
    # agents under this use_case (10 total now).
    runnable_cards = [c for c in body["agents"] if c["runnable"]]
    runnable_ids = sorted(c["agent_id"] for c in runnable_cards)
    must_include = {
        "code-validation-agent",
        "compliance-guardrail-agent",
        "medical-coding-agent",
        "note-completeness-agent",
    }
    assert must_include.issubset(set(runnable_ids)), (
        f"Expected at least {sorted(must_include)}; got {runnable_ids}"
    )


def test_hub_filter_clinical_evidence_research_returns_empty(client: TestClient):
    """?use_case=clinical_evidence_research → 0 packs (no pack declares
    this use_case yet; Loop 4 only set coding_revenue_cycle on all 16)."""
    response = _get(client, "/api/icoder/agents/hub?use_case=clinical_evidence_research")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0, f"Expected 0 packs, got {body['total']}"
    assert body["agents"] == []


def test_hub_filter_unknown_key_returns_empty_not_400(client: TestClient):
    """Unknown use_case key → empty result, NOT a 400 error. Backend
    treats unknown keys as a non-matching filter (silent empty)."""
    response = _get(client, "/api/icoder/agents/hub?use_case=invalid_garbage_key")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["agents"] == []


def test_hub_cards_include_use_case_top_level_field(client: TestClient):
    """Loop 4 §1: each Hub card must include `use_case` as a top-level
    field (not just inside manifest). Used by the frontend dropdown."""
    response = _get(client, "/api/icoder/agents/hub")
    assert response.status_code == 200
    body = response.json()
    for card in body["agents"]:
        assert "use_case" in card, f"Card missing use_case: {card.get('agent_ref')}"
        assert card["use_case"], f"use_case is empty for {card.get('agent_ref')}"


def test_hub_filter_case_sensitive(client: TestClient):
    """use_case filter is case-sensitive (Corti enum is lowercase
    snake_case). 'Coding_Revenue_Cycle' should return 0, not 11."""
    response = _get(client, "/api/icoder/agents/hub?use_case=Coding_Revenue_Cycle")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0, "Filter should be case-sensitive"
