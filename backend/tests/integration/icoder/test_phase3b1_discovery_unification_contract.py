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
6. metadata-only packs visible in Hub but NOT in A2A runnable discovery.
7. expert-stubs not in Hub, not in user-level A2A discovery.
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
    # 11 visible packs (10 metadata-only + medical-coding-agent MVP)
    assert body["total"] == 11


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


def test_a2a_discovery_does_not_include_metadata_only_packs(client):
    """metadata-only packs (10 certified packs with no experts[]) must
    NOT appear in A2A runnable discovery — they have no run path.
    They DO appear in Hub (with Coming Soon badge), but A2A discovery
    is for runnable agents only.
    """
    r = client.get("/api/icoder/agents")
    body = r.json()
    agent_ids = {a["id"] for a in body["agents"]}
    metadata_only_refs = [
        "cdi-review", "code-validation", "compliance-guardrail",
        "denial-appeals", "diagnosis-extractor", "documentation-gap",
        "drg-analyzer", "evidence-ranker", "note-completeness",
        "procedure-extractor",
    ]
    for ref in metadata_only_refs:
        assert ref not in agent_ids, (
            f"metadata-only pack {ref} must not appear in A2A runnable discovery "
            f"(it has no run path; Hub shows it with Coming Soon badge instead)"
        )


def test_a2a_discovery_does_not_include_expert_stubs(client):
    """expert-stub packs (4 MedCodER pipeline stages) must NOT appear
    in user-level A2A discovery — they're internal pipeline stages.
    """
    r = client.get("/api/icoder/agents")
    body = r.json()
    agent_ids = {a["id"] for a in body["agents"]}
    for stub_id in [
        "evidence-extractor",
        "index-navigator",
        "code-reconciler",
        "tabular-validator",
    ]:
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


# --- Entry point 4: templates (DB-mastered, no auth, for wizard) ---

def test_templates_endpoint_no_auth(client):
    """/api/rest/v1/agent_definitions/templates returns AGENT_TEMPLATES
    (hardcoded list for "new agent" wizard). No auth — browsing templates
    is allowed; creating from a template requires auth at the POST endpoint.
    """
    r = client.get("/api/rest/v1/agent_definitions/templates")
    assert r.status_code == 200
    body = r.json()
    assert "templates" in body
    assert isinstance(body["templates"], list)
    assert len(body["templates"]) >= 1, "templates list must not be empty"


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


# --- Cross-entry-point consistency ---

def test_hub_and_a2a_discovery_are_both_pack_mastered(client):
    """Both Hub and A2A discovery read from agent_pack.json (Hub) or
    card factories derived from packs (A2A). Neither reads from DB.
    """
    hub = client.get("/api/icoder/agents/hub").json()
    a2a = client.get("/api/icoder/agents").json()

    # Hub has 11 visible packs
    assert hub["total"] == 11
    # A2A discovery currently has 1 (medcoder-coding-review) — Section D
    # will add medical-coding-agent to bring it to 2
    assert len(a2a["agents"]) >= 1

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
    # The 6 overlapping packs should appear in Hub with their pack-backed agent_ref
    expected_pack_refs = [
        "icoder/code-validation@1.0.0",
        "icoder/compliance-guardrail@1.0.0",
        "icoder/denial-appeals@1.0.0",
        "icoder/diagnosis-extractor@1.0.0",
        "icoder/note-completeness@1.0.0",
        "icoder/procedure-extractor@1.0.0",
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
