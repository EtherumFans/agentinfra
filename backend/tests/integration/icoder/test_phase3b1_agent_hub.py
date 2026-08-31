"""Phase 3-B1 Section B — Agent Hub endpoint tests.

Verifies the restored ``/api/icoder/agents/hub`` endpoint per the
Phase 3-B1 prompt §B success criteria:

1. Endpoint returns 200.
2. Response structure matches contract (agents[], total, source).
3. hidden_from_hub=true packs do NOT appear.
4. metadata-only or unresolved packs do NOT appear.
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


def test_public_hub_runtime_readiness_requires_authenticated_tenant_context(client):
    body = client.get("/api/icoder/agents/hub").json()
    cards = body["agents"]

    assert body["schema_version"] == "1.3"
    assert len(cards) == 26
    assert all(card["runtime_readiness"]["structural_status"] == "ready" for card in cards)
    assert all(card["runtime_readiness"]["live_health_verified"] is False for card in cards)
    assert all(
        card["runtime_readiness"]["semantic_validation_status"] == "not_verified"
        for card in cards
    )
    assert all(
        card["runtime_readiness"]["production_approval_status"] == "not_approved"
        for card in cards
    )

    assert all(
        card["runtime_readiness"]["configuration_status"] == "not_checked"
        for card in cards
    )
    assert all(card["runtime_readiness"]["run_action_enabled"] is False for card in cards)
    assert all(
        card["runtime_readiness"]["reason"]
        == "tenant_runtime_readiness_requires_authentication"
        for card in cards
    )


def test_hub_openapi_exposes_versioned_runtime_readiness_schema(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/icoder/agents/hub"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/AgentHubListResponse")

    components = schema["components"]["schemas"]
    card = components["AgentHubCardResponse"]["properties"]
    assert card["execution_path"]["type"] == "string"
    assert card["execution_target"]["type"] == "string"
    assert card["runtime_readiness"]["$ref"].endswith("/AgentHubRuntimeReadiness")

    readiness = components["AgentHubRuntimeReadiness"]
    assert set(readiness["required"]) == {
        "structural_status",
        "configuration_status",
        "run_action_enabled",
        "reason",
        "runtime_dependencies",
        "external_llm_required",
        "live_health_verified",
        "semantic_validation_status",
        "production_approval_status",
    }
    assert readiness["additionalProperties"] is False
    assert set(readiness["properties"]["configuration_status"]["enum"]) == {
        "not_checked",
        "local_ready",
        "configured_not_live_verified",
        "unavailable",
    }

    tenant_operation = schema["paths"]["/api/icoder/agents/hub/readiness"]["get"]
    tenant_response = tenant_operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert tenant_response["$ref"].endswith("/AgentHubTenantReadinessResponse")
    tenant_readiness = components["AgentHubTenantRuntimeReadiness"]
    assert tenant_readiness["additionalProperties"] is False
    assert set(tenant_readiness["required"]) == {
        "structural_status",
        "configuration_status",
        "run_action_enabled",
        "reason",
        "runtime_dependencies",
        "llm_required",
        "live_health_verified",
        "connectivity_status",
        "semantic_validation_status",
        "production_approval_status",
    }


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

    Phase 4-F (2026-07-09): evidence-extractor was upgraded from expert-stub
    to certified (it's now one of the 8 iCoDer built agents) — removed from
    this exclusion list. The remaining 3 expert-stub packs (index-navigator /
    code-reconciler / tabular-validator) are MedCodER pipeline stages, not
    user-facing Agents.
    """
    r = client.get("/api/icoder/agents/hub")
    agent_refs = {c["agent_ref"] for c in r.json()["agents"]}
    for stub_ref in [
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


# --- former metadata-only packs are real launch candidates ---

def test_former_metadata_only_packs_are_runnable_launch_candidates(client):
    """Former placeholders remain visible only after runnable migration.

    Phase 3-D1 Task 5 (2026-07-06): code-validation / compliance-guardrail /
    note-completeness upgraded from metadata-only to runnable — removed
    from this list. Their runnability is verified in
    ``test_phase3d1_three_simple_agents_visible_and_runnable`` below.

    Phase 4-F (2026-07-09): drg-analyzer / procedure-extractor upgraded from
    metadata-only to mvp (now iCoDer built agents) — removed from this list.
    Their runnability is verified by the v1.3 spec schema test.

    Phase 5 Track D Gate 3 (2026-07-11): cdi-review + documentation-gap
    deprecated (folded into clinical-documentation-improvement-agent as
    CORE_ENTRY_AGENT). Removed from this list — both are now hidden_from_hub.

    Representative migrated Packs are asserted here; a regression to
    metadata-only or an unresolvable Provider would now remove the card and
    fail the authoritative runtime matrix.
    """
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}

    metadata_only_refs = [
        # Original Phase 4-F survivors (cdi-review + documentation-gap
        # removed in Phase 5 Track D — both deprecated + hidden).
            "icoder/evidence-ranker@1.1.0",
        # Phase A1D.5 claim-check stub (metadata-only tag).
        # Phase A1B-AE net-new metadata-only Corti-parity stubs (sample).
        "icoder/discharge-edu@1.1.0",
    ]
    for ref in metadata_only_refs:
        assert ref in cards_by_ref, (
            f"migrated launch candidate {ref} must appear in Hub"
        )
        card = cards_by_ref[ref]
        assert card["runnable"] is True, (
            f"migrated pack {ref} must have runnable=true"
        )
        assert card["run_endpoint"] is not None, (
            f"migrated pack {ref} must have run_endpoint"
        )
        assert card["pack_status"] == "executable"
        assert card["launch_candidate_ready"] is True


def test_phase3d1_three_simple_agents_visible_and_runnable(client):
    """Phase 3-D1 Task 5 — the 3 simple runnable agents must appear in Hub
    with runnable=true, an a2a_endpoint, and maturity='runnable'.

    These were metadata-only before Task 5; now they're real, deterministic
    agents wired through _SimpleAgentDispatchHandler in app/main.py.
    """
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}

    runnable_refs = [
        "icoder/code-validation-agent@2.0.0",
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
        assert card["maturity"] in ("mvp", "runnable"), (
            f"agent {ref} maturity must be 'mvp' or 'runnable'; got {card['maturity']!r}"
        )
        assert card["production_ready"] is False, (
            f"agent {ref} must declare production_ready=false"
        )
        assert "Launch candidate" in card["badge"], (
            f"agent {ref} badge must identify launch-candidate status; got {card['badge']!r}"
        )


def test_rule_explainer_is_wired_to_unified_runtime(client):
    """The former metadata-only pack is executable and uses the live facade."""
    cards = {
        c["agent_id"]: c
        for c in client.get("/api/icoder/agents/hub").json()["agents"]
    }
    card = cards["rule-explainer"]
    assert card["agent_ref"] == "icoder/rule-explainer@1.2.0"
    assert card["pack_status"] == "executable"
    assert card["runnable"] is True
    assert card["launch_candidate_ready"] is True
    assert card["launch_candidate_blockers"] == []
    assert card["run_endpoint"] == "/api/v1/agents/rule-explainer/run"
    assert card["run_url"] == card["run_endpoint"]


def test_diagnosis_extractor_is_wired_to_unified_runtime(client):
    cards = {
        c["agent_id"]: c
        for c in client.get("/api/icoder/agents/hub").json()["agents"]
    }
    card = cards["diagnosis-extractor"]
    assert card["agent_ref"] == "icoder/diagnosis-extractor@1.2.0"
    assert card["pack_status"] == "executable"
    assert card["runnable"] is True
    assert card["launch_candidate_ready"] is True
    assert card["run_endpoint"] == "/api/v1/agents/diagnosis-extractor/run"


def test_revenue_cycle_agents_are_wired_to_unified_runtime(client):
    cards = {
        c["agent_id"]: c
        for c in client.get("/api/icoder/agents/hub").json()["agents"]
    }
    for agent_id in ("claim-check", "denial-appeals", "prior-auth"):
        card = cards[agent_id]
        assert card["pack_status"] == "executable"
        assert card["runnable"] is True
        assert card["launch_candidate_ready"] is True
        assert card["run_endpoint"] == f"/api/v1/agents/{agent_id}/run"


# --- Medical Coding Agent visible + runnable ---

def test_medical_coding_agent_visible_and_runnable(client):
    """Medical Coding Agent (icoder/medical-coding-agent@2.0.0) must appear
    in Hub as a runnable engineering launch candidate with human review required.
    """
    r = client.get("/api/icoder/agents/hub")
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}
    ref = "icoder/medical-coding-agent@2.0.0"
    assert ref in cards_by_ref, "Medical Coding Agent must appear in Hub"
    card = cards_by_ref[ref]
    assert card["runnable"] is True, "Medical Coding Agent must be runnable"
    assert card["run_endpoint"] is not None, "Medical Coding Agent must have run_endpoint"
    assert card["maturity"] == "runnable", (
        "Medical Coding Agent maturity must reflect its executable runtime"
    )
    assert card["production_ready"] is False, (
        "Medical Coding Agent must declare production_ready=false"
    )
    assert "Launch candidate" in card["badge"], (
        f"Medical Coding Agent badge must identify launch-candidate status; got {card['badge']!r}"
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
    """Hub lists all visible launch candidates after Corti catalog closure.

    Breakdown of the 30 packs discovered by BuiltinAgentPackProvider:
    - 10 certified runnable (MVP) - visible
      * medical-coding-agent@2.0.0
      * evidence-extractor / drg-analyzer / procedure-extractor (Phase 4-F)
      * note-completeness-agent / compliance-guardrail-agent (Phase 3-D1)
      * principal-diagnosis-review / discharge-summary-structuring (Phase 4-F)
      * code-validation-agent@2.0.0 (Phase 4-C v2 migration)
      * clinical-documentation-improvement-agent (Phase 5 Track D Gate 3 - CDI entry agent)
    - former metadata-only certified Packs are now executable launch candidates
      * 3 Phase 4-F survivors: denial-appeals / diagnosis-extractor / evidence-ranker
        (cdi-review + documentation-gap deprecated + hidden in Phase 5 Track D Gate 3)
      * 1 Phase A1D.5 claim-check stub
      * 10 Phase A1B-AE net-new Corti-parity stubs (discharge-edu /
        nursing-handoff / referral-gen / icd10-navigator / rule-explainer /
        prior-auth / icu-summary / triage / med-reconciliation /
        surgical-registry)
    - 6 hidden - NOT visible
      * 1 internal_engine (medcoder-coding-review)
      * 3 expert-stub (index-navigator / code-reconciler / tabular-validator)
      * 2 deprecated (cdi-review / documentation-gap - hidden_from_hub=true)

    So Hub shows 24 visible cards (10 runnable + 14 metadata-only).
    """
    r = client.get("/api/icoder/agents/hub")
    body = r.json()
    assert body["total"] == 26, (
        f"Hub must list 26 visible runnable launch candidates; got {body['total']}. "
        f"Cards: {[c['agent_ref'] for c in body['agents']]}"
    )


def test_live_corti_catalog_closure_agents_are_runnable(client):
    """The two Agents found missing in the 2026-08-09 Corti live audit run."""
    cards = {
        c["agent_id"]: c
        for c in client.get("/api/icoder/agents/hub").json()["agents"]
    }
    for agent_id in ("clinical-education", "clinical-guidelines"):
        card = cards[agent_id]
        assert card["pack_status"] == "executable"
        assert card["runnable"] is True
        assert card["launch_candidate_ready"] is True
        assert card["production_ready"] is False
        assert card["run_endpoint"] == f"/api/v1/agents/{agent_id}/run"


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
            assert card["run_endpoint"] == (
                f"/api/v1/agents/{card['agent_id']}/run"
            ), f"unexpected unified run endpoint: {card['run_endpoint']!r}"
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
    from app.icoder.agent_runtime.a2a_facade import medical_coding_schema_ref
    assert oc["schema_ref"] == medical_coding_schema_ref()
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
    assert oc["field_relations"] == [{
        "id": "failed_rules_require_human_review",
        "when": [{
            "path": "validation_summary.passed",
            "operator": "equals",
            "value": False,
        }],
        "must": [{
            "path": "human_review.review_required",
            "operator": "equals",
            "value": True,
        }],
    }]
