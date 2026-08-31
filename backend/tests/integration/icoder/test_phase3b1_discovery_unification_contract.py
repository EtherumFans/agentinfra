"""Phase 3-B1 Section C — Discovery source unification contract tests.

Verifies that the 4 agent entry points have clear, non-overlapping
responsibilities per the Phase 3-B1 prompt §C:

1. ``GET /api/icoder/agents/hub`` — pack-mastered, no auth, read-only,
   product browsing. Source: ``official_agents/**/agent_pack.json``.
2. ``GET /api/icoder/agents`` — A2A discovery, pack-mastered via card
   factories. Source: ``agent_card.py`` factories (Phase 4 will plug in
   DB). No auth.
3. ``GET /api/rest/v1/agent_definitions`` — DB-mastered, auth-gated,
   CRUD for user-created + seed.py prebuilt agents. Source: ``Agent``
   DB model.
4. ``GET /api/rest/v1/agent_definitions/templates`` — DB-mastered,
   no auth, hardcoded ``AGENT_TEMPLATES`` list for "new agent" wizard.

Plus:
5. Medical Coding Agent appears in Hub (Section B done) AND A2A
   discovery (Section D will add the card factory; this test documents
   the requirement).
6. every Hub-visible pack is runnable and appears in A2A discovery.
7. deprecated/internal metadata-only and expert-stub packs remain hidden.
8. internal_engine not in Hub, but exists as internal dependency
   (registered for orchestrator internal use).
9. seed.py PREBUILT_AGENTS keys vs agent_pack.json agent_refs — no
   silent collision (different namespaces, documented).
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


# --- Entry point 1: Agent Hub (pack-mastered, no auth) ---

def test_hub_is_pack_mastered_and_no_auth(client):
    """Hub reads official_agents/agent_pack.json — no auth required."""
    r = client.get("/api/icoder/agents/hub")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "official_agents/agent_pack.json"
    # 24 visible packs (10 runnable + 14 metadata-only) after Phase A1B-AE
    # added 14 net-new Corti-parity stubs + Phase A1D.5 claim-check stub.
    assert body["total"] == 26


# --- Entry point 2: A2A discovery (pack-mastered via card factories) ---

def test_a2a_discovery_is_pack_mastered(client):
    """A2A discovery returns AgentCards built from card factories.
    Currently only medcoder-coding-review has a factory; Section D
    will add medical-coding-agent.
    """
    r = client.get("/api/icoder/agents")
    assert r.status_code == 200
    body = r.json()
    agent_ids = {a["id"] for a in body["agents"]}
    # medcoder-coding-review is the internal engine — its card is currently
    # the only one with a factory. Section D will add medical-coding-agent.
    assert "medcoder-coding-review" in agent_ids
    # No auth required for discovery
    assert "authorization" not in {k.lower() for k in r.request.headers.keys()}


def test_every_hub_visible_pack_appears_in_a2a_runnable_discovery(client):
    """The current launch-candidate baseline has no visible Coming Soon pack."""
    hub = client.get("/api/icoder/agents/hub").json()
    a2a = client.get("/api/icoder/agents").json()
    hub_ids = {
        card["agent_ref"].rsplit("/", 1)[-1].split("@", 1)[0]
        for card in hub["agents"]
    }
    agent_ids = {card["id"] for card in a2a["agents"]}

    assert len(hub_ids) == 26
    assert hub_ids <= agent_ids
    for upgraded in {
        "denial-appeals",
        "diagnosis-extractor",
        "drg-analyzer",
        "evidence-ranker",
        "procedure-extractor",
    }:
        assert upgraded in agent_ids

    # Deprecated aliases remain hidden rather than masquerading as runnable.
    assert {"cdi-review", "documentation-gap"}.isdisjoint(agent_ids)


def test_visible_evidence_extractor_is_runnable_but_internal_stubs_are_hidden(client):
    """The promoted evidence Agent is public; three internal stubs stay hidden."""
    r = client.get("/api/icoder/agents")
    body = r.json()
    agent_ids = {a["id"] for a in body["agents"]}
    assert "evidence-extractor" in agent_ids
    for stub_id in ["index-navigator", "code-reconciler", "tabular-validator"]:
        assert stub_id not in agent_ids, (
            f"expert-stub {stub_id} must not appear in user-level A2A discovery"
        )


# --- Entry point 3: agent_definitions (DB-mastered, auth-gated in prod) ---

def test_agent_definitions_is_db_mastered(client):
    """/api/rest/v1/agent_definitions is DB-backed.

    In production: requires auth (401 without token). In test env
    (ICODER_DISABLE_AUTH_FOR_TESTS=1): auth is bypassed, returns 200
    with DB rows.

    Either way, the response must be DB-shaped (rows with ``is_prebuilt``
    field), NOT pack-shaped (cards with ``agent_ref`` field). This is
    what makes agent_definitions distinct from Hub — Hub returns
    pack cards, agent_definitions returns DB rows.
    """
    r = client.get("/api/rest/v1/agent_definitions")
    # Test env bypasses auth (200); prod would 401. Both are honest states.
    assert r.status_code in (200, 401), (
        f"agent_definitions returned {r.status_code}; expected 200 (test env) or 401 (prod)"
    )
    if r.status_code == 200:
        body = r.json()
        # DB rows have is_prebuilt field; pack cards don't
        if body.get("agents"):
            for row in body["agents"]:
                assert "is_prebuilt" in row, (
                    f"agent_definitions row must have 'is_prebuilt' (DB-shaped); "
                    f"got keys: {list(row.keys())}"
                )
                assert "agent_ref" not in row, (
                    f"agent_definitions row must NOT have 'agent_ref' "
                    f"(that's Hub/A2A pack-shaped); got agent_ref={row.get('agent_ref')}"
                )


# --- Entry point 4: templates (Pack-mastered + generic blanks, no auth) ---

def test_templates_endpoint_no_auth(client):
    """The New Agent wizard mirrors Hub launch candidates without drift.

    No auth is required to browse templates. Governed creation is performed
    by the authenticated Hub clone endpoint; only generic blank templates use
    the generic Agent create path.
    """
    r = client.get("/api/rest/v1/agent_definitions/templates")
    assert r.status_code == 200
    body = r.json()
    assert "templates" in body
    assert isinstance(body["templates"], list)
    governed = [
        item for item in body["templates"]
        if item.get("template_kind") == "governed_prebuilt"
    ]
    generic = [
        item for item in body["templates"]
        if item.get("template_kind") == "generic_blank"
    ]
    hub = client.get("/api/icoder/agents/hub").json()
    assert {item["id"] for item in governed} == {
        item["agent_id"] for item in hub["agents"]
    }
    assert len(governed) == 26
    assert {item["id"] for item in generic} == {
        "translator-blank",
        "summarizer-blank",
    }
    assert len(body["templates"]) == 28

    stale_aliases = {
        "cdi",
        "clinical-edu",
        "code-validation",
        "compliance-guardrail",
        "medical-coding",
        "note-completeness",
    }
    assert not stale_aliases & {item["id"] for item in body["templates"]}
    for item in governed:
        assert item["clone_transport"] == "agent_hub"
        assert item["clone_url"] == (
            f"/api/icoder/agents/{item['runtime_agent_id']}/clone"
        )
        assert item["source_agent_ref"].startswith("icoder/")


def test_templates_are_not_runnable_agents(client):
    """Templates are starting points for new agents — not runnable themselves.
    Each template should have an id, title, system_prompt, but NO run_endpoint.
    """
    r = client.get("/api/rest/v1/agent_definitions/templates")
    for t in r.json()["templates"]:
        assert "id" in t, "template must have id"
        assert "title" in t or "name" in t, f"template {t.get('id')} must have title or name"
        assert "run_endpoint" not in t, (
            f"template {t.get('id')} must not have run_endpoint "
            f"(templates are not runnable)"
        )


def test_governed_template_download_is_the_canonical_pack(client):
    response = client.get(
        "/api/rest/v1/agent_definitions/templates/clinical-guidelines/download"
    )
    assert response.status_code == 200
    downloaded = response.json()
    assert downloaded["agent_ref"] == "icoder/clinical-guidelines@1.1.0"
    assert downloaded["backend_provider"] == (
        "icoder.governed-clinical-guidelines.v1"
    )
    assert downloaded["manifest"]["maturity"] == "runnable"
    assert downloaded["manifest"]["production_ready"] is False
    assert not any(str(key).startswith("_") for key in downloaded)


def test_legacy_clone_path_fails_closed_for_governed_template(client):
    response = client.post(
        "/api/rest/v1/agent_definitions/clinical-guidelines/clone",
        json={},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "governed_template_clone_endpoint_required"
    assert detail["clone_url"] == (
        "/api/icoder/agents/clinical-guidelines/clone"
    )


# --- Cross-entry-point consistency ---

def test_hub_and_a2a_discovery_are_both_pack_mastered(client):
    """Both Hub and A2A discovery read from agent_pack.json (Hub) or
    card factories derived from packs (A2A). Neither reads from DB.
    """
    hub = client.get("/api/icoder/agents/hub").json()
    a2a = client.get("/api/icoder/agents").json()

    # All 26 Hub-visible packs are runnable launch candidates.
    assert hub["total"] == 26
    assert len(a2a["agents"]) >= 26

    # Hub cards have agent_ref (file-system canonical ref)
    for card in hub["agents"]:
        assert card["agent_ref"].startswith("icoder/"), (
            f"Hub card must have file-system agent_ref starting with 'icoder/'; "
            f"got {card['agent_ref']}"
        )


def test_medical_coding_agent_appears_in_hub(client):
    """Medical Coding Agent must appear in Hub (Section B done)."""
    r = client.get("/api/icoder/agents/hub")
    refs = {c["agent_ref"] for c in r.json()["agents"]}
    assert "icoder/medical-coding-agent@2.0.0" in refs, (
        "Medical Coding Agent must appear in Hub"
    )


def test_medical_coding_agent_appears_in_a2a_after_section_d(client):
    """Medical Coding Agent must also appear in A2A discovery.

    This is a GATE test: it FAILS until Section D adds the card factory
    for medical-coding-agent. The failure is intentional — it surfaces
    the Section D scope. After Section D completes, this test passes.

    If Section D is complete and this still fails, the card factory
    was not wired into _phase1_agent_provider in main.py.
    """
    r = client.get("/api/icoder/agents")
    body = r.json()
    agent_ids = {a["id"] for a in body["agents"]}
    # After Section D, "medical-coding-agent" should be in agent_ids
    assert "medical-coding-agent" in agent_ids, (
        "Medical Coding Agent must appear in A2A discovery (Section D will add the "
        "card factory). If this test fails, Section D has not yet completed the migration."
    )


# --- seed.py vs agent_pack.json naming collision check ---

def test_seed_prebuilt_agents_no_silent_collision_with_packs(client):
    """seed.py PREBUILT_AGENTS (16 DB rows) and agent_pack.json (16 file packs)
    overlap on 6 keys: code-validation, compliance-guardrail, denial-appeals,
    diagnosis-extractor, note-completeness, procedure-extractor.

    These are in DIFFERENT namespaces:
    - seed.py: DB rows with is_prebuilt=True, key=adata["key"] (kebab-case)
    - agent_pack.json: file packs, agent_ref="icoder/{slug}@{version}"

    The Hub and A2A discovery use agent_pack.json (file-system canonical).
    agent_definitions list shows BOTH (DB rows from seed.py + user-created),
    but the pack-backed agents are clearly distinguished by agent_ref
    starting with "icoder/".

    This test verifies no silent collision: the 6 overlapping names
    appear in BOTH seed.py (as DB rows) and agent_pack.json (as file packs),
    but the Hub only shows the file packs (the canonical Corti-aligned versions).
    """
    # Hub shows pack-backed agents (file-system canonical)
    r = client.get("/api/icoder/agents/hub")
    pack_refs = {c["agent_ref"] for c in r.json()["agents"]}
    # The 6 overlapping packs should appear in Hub with their pack-backed agent_ref.
    # Phase 3-D1 Task 5 (2026-07-06): 3 of these upgraded from metadata-only
    # to runnable, so their agent_ref gained the -agent suffix (matching
    # the medical-coding-agent convention).
    expected_pack_refs = [
        "icoder/code-validation-agent@2.0.0",
        "icoder/compliance-guardrail-agent@1.0.0",
        "icoder/denial-appeals@1.1.0",
        "icoder/diagnosis-extractor@1.2.0",
        "icoder/note-completeness-agent@1.0.0",
        "icoder/procedure-extractor@1.1.0",
    ]
    for ref in expected_pack_refs:
        assert ref in pack_refs, (
            f"Pack-backed {ref} should appear in Hub (canonical Corti-aligned version). "
            f"If missing, the seed.py DB row may have shadowed it."
        )


# --- Well-known agent.json (A2A standard discovery) ---

def test_well_known_agent_json_returns_200(client):
    """.well-known/agent.json is the A2A v0.3 standard discovery endpoint.
    Must return 200 with agents list.
    """
    r = client.get("/.well-known/agent.json")
    assert r.status_code == 200
    body = r.json()
    assert "agents" in body
    assert isinstance(body["agents"], list)


def test_llms_txt_returns_200(client):
    """llms.txt is the LLM-friendly A2A discovery endpoint."""
    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert "text/markdown" in r.headers.get("content-type", "")
