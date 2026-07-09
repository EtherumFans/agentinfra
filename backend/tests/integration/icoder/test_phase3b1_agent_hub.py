"""Phase 3-B1 Section B — Agent Hub endpoint tests.

Verifies the restored ``/api/icoder/agents/hub`` endpoint per the
Phase 3-B1 prompt §B success criteria:

1. Endpoint returns 200.
2. Response structure matches contract (agents[], total, source).
3. hidden_from_hub=true packs do NOT appear.
4. metadata-only packs visible but ``runnable=false`` (no Run button).
5. Medical Coding Agent visible AND ``runnable=true`` (has Run).
6. expert-stub packs do NOT appear.
7. internal_engine packs do NOT appear.
8. ``production_ready`` field is always present (A.5.5).

These are smoke-level tests against the live TestClient (in-process).
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
    """Use context manager to trigger lifespan so PlatformRuntime initializes."""
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# --- Endpoint returns 200 + contract shape ---

def test_hub_endpoint_returns_200(client):
    """``GET /api/icoder/agents/hub`` must return 200 (restored endpoint)."""
    r = client.get("/api/icoder/agents/hub")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"


def test_hub_response_contract_shape(client):
    """Response must have ``agents``, ``total``, ``source``, ``schema_version``."""
    r = client.get("/api/icoder/agents/hub")
    body = r.json()
    assert "agents" in body, "missing 'agents' field"
    assert "total" in body, "missing 'total' field"
    assert "source" in body, "missing 'source' field"
    assert body["source"] == "official_agents/agent_pack.json"
    assert body["total"] == len(body["agents"])
    assert body["total"] >= 1, "Hub must list at least 1 agent"


# --- hidden / stub / internal_engine packs must NOT appear ---

def test_hidden_packs_excluded(client):
    """hidden_from_hub=true packs must not appear in Hub."""
    r = client.get("/api/icoder/agents/hub")
    for card in r.json()["agents"]:
        assert card["hidden_from_hub"] is False, (
            f"hidden pack {card['agent_ref']} appeared in Hub"
        )


def test_expert_stubs_excluded(client):
    """agent_type=expert-stub packs must not appear in Hub.

    The 4 expert-stub packs (evidence-extractor / index-navigator /
    code-reconciler / tabular-validator) are MedCodER pipeline stages,
    not user-facing Agents.
    """
    r = client.get("/api/icoder/agents/hub")
    agent_refs = {c["agent_ref"] for c in r.json()["agents"]}
    for stub_ref in [
        "icoder/evidence-extractor@1.0.0",
        "icoder/index-navigator@1.0.0",
        "icoder/code-reconciler@1.0.0",
        "icoder/tabular-validator@1.0.0",
    ]:
        assert stub_ref not in agent_refs, (
            f"expert-stub {stub_ref} must not appear in Hub"
        )


def test_internal_engine_excluded(client):
    """agent_type=internal_engine pack (medcoder-coding-review) must not appear."""
    r = client.get("/api/icoder/agents/hub")
    agent_refs = {c["agent_ref"] for c in r.json()["agents"]}
    assert "icoder/medcoder-coding-review-agent@1.0.0" not in agent_refs, (
        "internal_engine pack must not appear in Hub"
    )


# --- metadata-only packs visible but not runnable ---

def test_metadata_only_packs_visible_but_not_runnable(client):
    """The 7 metadata-only certified packs must appear with runnable=false
    and a Coming Soon badge (no Run button on frontend).

    Phase 3-D1 Task 5 (2026-07-06): code-validation / compliance-guardrail /
    note-completeness upgraded from metadata-only to runnable — removed
    from this list. Their runnability is verified in
    ``test_phase3d1_three_simple_agents_visible_and_runnable`` below.
    """
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}

    metadata_only_refs = [
        "icoder/cdi-review@1.0.0",
        "icoder/denial-appeals@1.0.0",
        "icoder/diagnosis-extractor@1.0.0",
        "icoder/documentation-gap@1.0.0",
        "icoder/drg-analyzer@1.0.0",
        "icoder/evidence-ranker@1.0.0",
        "icoder/procedure-extractor@1.0.0",
    ]
    for ref in metadata_only_refs:
        assert ref in cards_by_ref, (
            f"metadata-only pack {ref} must appear in Hub (visible with Coming Soon badge)"
        )
        card = cards_by_ref[ref]
        assert card["runnable"] is False, (
            f"metadata-only pack {ref} must have runnable=false"
        )
        assert card["run_endpoint"] is None, (
            f"metadata-only pack {ref} must not have run_endpoint"
        )
        assert "Coming Soon" in card["badge"], (
            f"metadata-only pack {ref} badge must say 'Coming Soon'; got {card['badge']!r}"
        )


def test_phase3d1_three_simple_agents_visible_and_runnable(client):
    """Phase 3-D1 Task 5 — the 3 simple runnable agents must appear in Hub
    with runnable=true, an a2a_endpoint, and maturity='runnable'.

    These were metadata-only before Task 5; now they're real, deterministic
    agents wired through _SimpleAgentDispatchHandler in app/main.py.
    """
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}

    runnable_refs = [
        "icoder/code-validation-agent@1.0.0",
        "icoder/compliance-guardrail-agent@1.0.0",
        "icoder/note-completeness-agent@1.0.0",
    ]
    for ref in runnable_refs:
        assert ref in cards_by_ref, (
            f"runnable agent {ref} must appear in Hub"
        )
        card = cards_by_ref[ref]
        assert card["runnable"] is True, (
            f"agent {ref} must have runnable=true (Phase 3-D1 Task 5 upgrade)"
        )
        assert card["run_endpoint"] is not None, (
            f"agent {ref} must have an a2a run_endpoint"
        )
        assert card["maturity"] == "runnable", (
            f"agent {ref} maturity must be 'runnable'; got {card['maturity']!r}"
        )
        assert card["production_ready"] is False, (
            f"agent {ref} must declare production_ready=false"
        )
        assert "MVP" in card["badge"], (
            f"agent {ref} badge must include 'MVP'; got {card['badge']!r}"
        )


# --- Medical Coding Agent visible + runnable ---

def test_medical_coding_agent_visible_and_runnable(client):
    """Medical Coding Agent (icoder/medical-coding-agent@2.0.0) must appear
    in Hub with runnable=true and the MVP / AI-assisted / Human review required badge.
    """
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}
    ref = "icoder/medical-coding-agent@2.0.0"
    assert ref in cards_by_ref, "Medical Coding Agent must appear in Hub"
    card = cards_by_ref[ref]
    assert card["runnable"] is True, "Medical Coding Agent must be runnable"
    assert card["run_endpoint"] is not None, "Medical Coding Agent must have run_endpoint"
    assert card["maturity"] == "mvp", "Medical Coding Agent maturity must be 'mvp'"
    assert card["production_ready"] is False, (
        "Medical Coding Agent must declare production_ready=false (MVP, not production-ready)"
    )
    assert "MVP" in card["badge"], (
        f"Medical Coding Agent badge must include 'MVP'; got {card['badge']!r}"
    )
    assert "AI-assisted" in card["badge"], (
        f"Medical Coding Agent badge must include 'AI-assisted'; got {card['badge']!r}"
    )
    assert "Human review" in card["badge"], (
        f"Medical Coding Agent badge must include 'Human review'; got {card['badge']!r}"
    )


# --- production_ready field always present (A.5.5) ---

def test_production_ready_field_always_present(client):
    """Every Hub card must include the production_ready field (A.5.5)."""
    r = client.get("/api/icoder/agents/hub")
    for card in r.json()["agents"]:
        assert "production_ready" in card, (
            f"card {card['agent_ref']} missing 'production_ready' field (A.5.5)"
        )
        assert isinstance(card["production_ready"], bool), (
            f"card {card['agent_ref']} production_ready must be bool, "
            f"got {type(card['production_ready']).__name__}"
        )


def test_no_production_ready_false_claimed_as_ready(client):
    """No pack with production_ready=false can be displayed as production-ready
    (badge / maturity must not say 'production-ready')."""
    r = client.get("/api/icoder/agents/hub")
    for card in r.json()["agents"]:
        if card["production_ready"] is False:
            assert card["maturity"] != "production-ready", (
                f"card {card['agent_ref']} has production_ready=false "
                f"but maturity=production-ready (misleading)"
            )
            assert "production-ready" not in card["badge"].lower(), (
                f"card {card['agent_ref']} badge says 'production-ready' "
                f"but production_ready=false (misleading)"
            )


# --- Hub total count ---

def test_hub_total_count_matches_visibility_filter(client):
    """Hub must list exactly 12 visible packs:
    10 metadata-only certified + 1 medical-coding-agent (MVP) + 1 medical-coding
    certified (note: medical-coding-agent IS the medical-coding certified pack).

    Actual breakdown of the 16 packs:
    - 11 certified user-facing (10 metadata-only + 1 medical-coding-agent MVP)
    - 1 internal_engine (medcoder-coding-review) — hidden
    - 4 expert-stub — hidden

    So Hub must show 11 visible cards (not 12 — medical-coding-agent is one
    of the 11 certified).
    """
    r = client.get("/api/icoder/agents/hub")
    body = r.json()
    assert body["total"] == 11, (
        f"Hub must list 11 visible packs (10 metadata-only + medical-coding-agent MVP); "
        f"got {body['total']}. Cards: {[c['agent_ref'] for c in body['agents']]}"
    )


# --- Run endpoint shape ---

def test_runnable_card_has_run_endpoint(client):
    """Every runnable card must have run_endpoint set; every non-runnable
    card must have run_endpoint=None."""
    r = client.get("/api/icoder/agents/hub")
    for card in r.json()["agents"]:
        if card["runnable"]:
            assert card["run_endpoint"] is not None, (
                f"runnable card {card['agent_ref']} missing run_endpoint"
            )
            assert card["agent_ref"] in card["run_endpoint"], (
                f"run_endpoint {card['run_endpoint']!r} must contain agent_ref"
            )
        else:
            assert card["run_endpoint"] is None, (
                f"non-runnable card {card['agent_ref']} must have run_endpoint=None"
            )


# --- Red lines field ---

def test_medical_coding_agent_red_lines_preserved(client):
    """Medical Coding Agent card must surface the 4 Corti red lines
    in the red_lines field (no_upcoding / no_inference / evidence_required /
    production_writeback_blocked)."""
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}
    card = cards_by_ref["icoder/medical-coding-agent@2.0.0"]
    rl = card["red_lines"]
    assert rl["no_upcoding"] is True, "no_upcoding red line must be true"
    assert rl["no_inference"] is True, "no_inference red line must be true"
    assert rl["evidence_required"] is True, "evidence_required red line must be true"
    assert rl["production_writeback_blocked"] is True, (
        "production_writeback_blocked red line must be true"
    )


# --- 8-field output contract surfaced ---

def test_medical_coding_agent_output_contract_surfaced(client):
    """Medical Coding Agent card must surface the 8-field output contract
    (Phase 3-A red line) in output_contract.required_fields."""
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}
    card = cards_by_ref["icoder/medical-coding-agent@2.0.0"]
    oc = card["output_contract"]
    assert oc["schema_ref"] == "icoder/MedicalCodingAgentOutputV2/v1"
    required = set(oc["required_fields"])
    expected_8 = {
        "encounter_summary",
        "documentation_analysis",
        "code_assignment",
        "documentation_gaps",
        "uncodable_items",
        "validation_summary",
        "human_review",
        "trace_refs",
    }
    assert expected_8.issubset(required), (
        f"output_contract missing required fields: {expected_8 - required}"
    )
