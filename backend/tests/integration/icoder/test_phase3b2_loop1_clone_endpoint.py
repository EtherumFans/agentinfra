"""Phase 3-B2 Loop 1 — Hub Clone endpoint tests (Gap 2.3).

Verifies the ``POST /api/icoder/agents/{agent_id}/clone`` endpoint per the
Phase 3-B2 Loop 1 acceptance criteria:

1. Hub card (``GET /api/icoder/agents/hub``) includes ``clone_url``,
   ``chat_url``, ``customize_url``, ``run_url`` fields for runnable agents.
2. ``POST /api/icoder/agents/medical-coding-agent/clone`` returns 201 on
   first clone, Body includes all URL fields
   (``project_agent_id``, ``runtime_agent_id``, ``source_agent_ref``,
   ``chat_url``, ``customize_url``, ``run_url``, ``cloned: True``).
3. DB has a new project-scoped (org-scoped) ``Agent`` row after clone.
4. Duplicate clone (same org, same source_agent_ref) returns 200 OK with
   ``cloned: False`` and the existing record's URLs (idempotent strategy).
5. 404 when ``agent_id`` not found among prebuilt agents.
6. 401 when no auth token (permissions scenario).

Auth bypass (``ICODER_DISABLE_AUTH_FOR_TESTS=1``) is on by default for
the success paths; the 401 test temporarily removes the override to
exercise the real ``get_current_user`` / ``get_current_organization``
dependencies.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

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


@pytest.fixture(autouse=True)
def _cleanup_cloned_agents():
    """Delete any cloned Agents (is_prebuilt=False) before each test so
    clone-state is isolated: the first clone in each test gets 201, not
    200 from a previous test's residue.

    Prebuilt agents (is_prebuilt=True) are NOT touched — they're seeded
    at lifespan startup and must remain visible across tests.
    """
    import asyncio
    from sqlalchemy import delete
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent

    async def _purge():
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Agent).where(Agent.is_prebuilt == False)  # noqa: E712
            )
            await session.commit()
    asyncio.run(_purge())
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clone(client: TestClient, agent_id: str, body: dict | None = None):
    """POST /api/icoder/agents/{agent_id}/clone."""
    return client.post(f"/api/icoder/agents/{agent_id}/clone", json=body or {})


# ---------------------------------------------------------------------------
# 1. Hub card includes the 4 action URL fields
# ---------------------------------------------------------------------------

def test_hub_card_includes_action_urls_for_runnable_agent(client):
    """Hub card for medical-coding-agent must include clone_url, chat_url,
    customize_url, run_url (Phase 3-B2 Loop 1 Gap 2.3 contract)."""
    r = client.get("/api/icoder/agents/hub")
    assert r.status_code == 200, f"Hub returned {r.status_code}: {r.text}"
    cards_by_ref = {c["agent_ref"]: c for c in r.json()["agents"]}
    assert "icoder/medical-coding-agent@2.0.0" in cards_by_ref, (
        "Medical Coding Agent must appear in Hub"
    )
    card = cards_by_ref["icoder/medical-coding-agent@2.0.0"]
    assert card["runnable"] is True, "Medical Coding Agent must be runnable"
    # 4 action URL fields (Loop 1 Gap 2.3 contract)
    assert card.get("clone_url") == "/api/icoder/agents/medical-coding-agent/clone", (
        f"clone_url mismatch: {card.get('clone_url')!r}"
    )
    assert card.get("chat_url") == "/agents/{project_agent_id}/chat", (
        f"chat_url template mismatch: {card.get('chat_url')!r}"
    )
    assert card.get("customize_url") == "/ai-studio/agents/{project_agent_id}", (
        f"customize_url template mismatch: {card.get('customize_url')!r}"
    )
    # run_url should be set to the A2A endpoint for runnable agents
    assert card.get("run_url") is not None, "run_url must be set for runnable agent"
    assert "medical-coding-agent" in card["run_url"], (
        f"run_url should reference medical-coding-agent: {card['run_url']!r}"
    )
    # agent_id short form derived from agent_ref
    assert card.get("agent_id") == "medical-coding-agent", (
        f"agent_id short form mismatch: {card.get('agent_id')!r}"
    )


def test_hub_exposes_only_runnable_cards(client):
    """Non-runnable (metadata-only) packs must have null action URLs —
    no clone/chat/customize/run buttons on the frontend."""
    r = client.get("/api/icoder/agents/hub")
    cards = r.json()["agents"]
    assert cards, "Hub must expose launch-candidate agents"
    non_runnable_refs = [c["agent_ref"] for c in cards if not c["runnable"]]
    assert non_runnable_refs == [], (
        f"metadata-only/internal packs leaked into Hub: {non_runnable_refs}"
    )


# ---------------------------------------------------------------------------
# 2. POST /clone returns 201 on first clone with all URL fields
# ---------------------------------------------------------------------------

def test_clone_first_call_returns_201_with_all_url_fields(client):
    """First clone of medical-coding-agent must return 201 Created with
    project_agent_id, runtime_agent_id, source_runtime_agent_id,
    source_agent_ref, chat_url,
    customize_url, run_url, cloned=True."""
    r = _clone(client, "medical-coding-agent")
    assert r.status_code == 201, (
        f"first clone must return 201; got {r.status_code}: {r.text}"
    )
    body = r.json()
    # All required CloneResponse fields present
    assert "project_agent_id" in body and body["project_agent_id"], (
        "project_agent_id must be a non-empty string (DB UUID)"
    )
    assert body["runtime_agent_id"] == body["project_agent_id"], (
        f"runtime_agent_id mismatch: {body.get('runtime_agent_id')!r}"
    )
    assert body["source_runtime_agent_id"] == "medical-coding-agent"
    assert body["source_agent_ref"] == "icoder/medical-coding-agent@2.0.0", (
        f"source_agent_ref mismatch: {body.get('source_agent_ref')!r}"
    )
    assert body["chat_url"] == f"/agents/{body['project_agent_id']}/chat", (
        f"chat_url must point to /agents/<id>/chat: {body.get('chat_url')!r}"
    )
    assert body["customize_url"] == f"/ai-studio/agents/{body['project_agent_id']}", (
        f"customize_url must point to /ai-studio/agents/<id>: "
        f"{body.get('customize_url')!r}"
    )
    assert body["run_url"] == (
        f"/api/icoder/agents/{body['project_agent_id']}/v1/message:send"
    ), (
        f"run_url must reference the project Agent A2A path: "
        f"{body.get('run_url')!r}"
    )
    assert body["cloned"] is True, "first clone must set cloned=True"


# ---------------------------------------------------------------------------
# 3. DB has new project-scoped (org-scoped) Agent row after clone
# ---------------------------------------------------------------------------

def test_clone_creates_org_scoped_agent_row_in_db(client):
    """Cloning must insert a new Agent row with is_prebuilt=False and
    organization_id set to the caller's org (project-scoped)."""
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent

    # Count prebuilt and cloned agents before
    async def _count():
        async with AsyncSessionLocal() as session:
            prebuilt = await session.execute(
                select(Agent).where(Agent.is_prebuilt == True)  # noqa: E712
            )
            cloned = await session.execute(
                select(Agent).where(Agent.is_prebuilt == False)  # noqa: E712
            )
            return (
                len(prebuilt.scalars().all()),
                len(cloned.scalars().all()),
            )
    # TestClient owns a separate portal thread. Python 3.12 no longer creates
    # a main-thread event loop implicitly, so run these direct DB assertions in
    # explicit, short-lived loops.
    import asyncio
    pre_before, cloned_before = asyncio.run(_count())

    # Clone
    r = _clone(client, "medical-coding-agent")
    assert r.status_code == 201, f"clone failed: {r.status_code}: {r.text}"
    project_agent_id = r.json()["project_agent_id"]

    # Count after
    pre_after, cloned_after = asyncio.run(_count())
    assert pre_after == pre_before, "prebuilt count must not change"
    assert cloned_after == cloned_before + 1, (
        f"cloned count must increase by 1: {cloned_before} → {cloned_after}"
    )

    # Verify the new row's fields
    async def _get_cloned():
        async with AsyncSessionLocal() as session:
            q = select(Agent).where(Agent.id == project_agent_id)
            result = await session.execute(q)
            return result.scalar_one_or_none()
    new_agent = asyncio.run(_get_cloned())
    assert new_agent is not None, f"new Agent row not found: id={project_agent_id}"
    assert new_agent.is_prebuilt is False, "cloned Agent must have is_prebuilt=False"
    assert new_agent.organization_id is not None, (
        "cloned Agent must have organization_id set (project-scoped)"
    )
    cfg = new_agent.config or {}
    assert cfg.get("source_agent_ref") == "icoder/medical-coding-agent@2.0.0", (
        f"config.source_agent_ref mismatch: {cfg.get('source_agent_ref')!r}"
    )
    assert cfg.get("cloned_from_prebuilt") is True, (
        "config.cloned_from_prebuilt must be True"
    )


# ---------------------------------------------------------------------------
# 4. Duplicate clone returns 200 OK with cloned=False (idempotent)
# ---------------------------------------------------------------------------

def test_clone_duplicate_returns_200_with_existing_record(client):
    """Second clone (same org, same source_agent_ref) must return 200 OK
    with cloned=False and the existing record's URLs — idempotent
    strategy (no duplicate row created)."""
    # First clone — 201
    r1 = _clone(client, "medical-coding-agent")
    assert r1.status_code == 201, f"first clone failed: {r1.status_code}: {r1.text}"
    first = r1.json()
    assert first["cloned"] is True

    # Second clone — 200, same project_agent_id, cloned=False
    r2 = _clone(client, "medical-coding-agent")
    assert r2.status_code == 200, (
        f"duplicate clone must return 200 (idempotent); got {r2.status_code}: {r2.text}"
    )
    second = r2.json()
    assert second["cloned"] is False, "duplicate clone must set cloned=False"
    assert second["project_agent_id"] == first["project_agent_id"], (
        "idempotent clone must return the same project_agent_id"
    )
    assert second["chat_url"] == first["chat_url"], "chat_url must match"
    assert second["customize_url"] == first["customize_url"], "customize_url must match"
    assert second["run_url"] == first["run_url"], "run_url must match"
    assert second["source_agent_ref"] == first["source_agent_ref"], (
        "source_agent_ref must match"
    )


# ---------------------------------------------------------------------------
# 5. 404 when agent_id not found among prebuilt agents
# ---------------------------------------------------------------------------

def test_clone_returns_404_for_unknown_agent_id(client):
    """Cloning an unknown agent_id must return 404 with AGENT_NOT_FOUND."""
    r = _clone(client, "nonexistent-fake-agent-xyz")
    assert r.status_code == 404, (
        f"unknown agent must return 404; got {r.status_code}: {r.text}"
    )
    body = r.json()
    detail = body.get("detail", {})
    assert isinstance(detail, dict), f"detail must be a dict: {detail!r}"
    assert detail.get("error_code") == "AGENT_NOT_FOUND", (
        f"error_code mismatch: {detail.get('error_code')!r}"
    )
    assert "nonexistent-fake-agent-xyz" in detail.get("message", ""), (
        f"404 message must include the unknown agent_id: {detail.get('message')!r}"
    )


def test_clone_returns_404_for_stub_agent_id(client):
    """Cloning an agent_id whose source pack is hidden (expert-stub or
    internal_engine) must return 404 — those packs are not Hub-visible
    and have no prebuilt Agent row.

    The medcoder-coding-review-agent pack is internal_engine. It may have a
    derived prebuilt DB projection for runtime administration, but the Hub
    does not publish it and Clone must therefore reject the real short ID.
    """
    r = _clone(client, "medcoder-coding-review-agent")
    assert r.status_code == 404, (
        f"unknown agent must return 404; got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# 6. 401 when no auth token (permissions scenario)
# ---------------------------------------------------------------------------

def test_clone_returns_401_without_auth_token(client):
    """Without a valid Bearer token, the clone endpoint must return 401
    (real auth path, no test bypass).

    This temporarily removes the get_current_user / get_current_organization
    dependency overrides so the real JWT validation kicks in.
    """
    from app.main import app
    from app.middleware.auth import get_current_user, get_current_organization

    saved_user = app.dependency_overrides.get(get_current_user)
    saved_org = app.dependency_overrides.get(get_current_organization)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_organization, None)
    try:
        r = client.post(
            "/api/icoder/agents/medical-coding-agent/clone",
            json={},
            # No Authorization header
        )
        assert r.status_code == 401, (
            f"unauthenticated clone must return 401; got {r.status_code}: {r.text}"
        )
    finally:
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user
        if saved_org is not None:
            app.dependency_overrides[get_current_organization] = saved_org


# ---------------------------------------------------------------------------
# Body overrides — name / description
# ---------------------------------------------------------------------------

def test_clone_with_name_override(client):
    """Caller can override the cloned Agent's name via request body."""
    r = _clone(client, "medical-coding-agent", body={
        "name": "My Custom Coding Agent",
        "description": "Custom description for my org",
    })
    assert r.status_code == 201, f"clone with override failed: {r.status_code}: {r.text}"
    body = r.json()
    assert body["cloned"] is True
    # Verify the name was applied (would need to query DB to confirm)
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent
    import asyncio

    async def _get():
        async with AsyncSessionLocal() as session:
            q = select(Agent).where(Agent.id == body["project_agent_id"])
            result = await session.execute(q)
            return result.scalar_one_or_none()
    agent = asyncio.run(_get())
    assert agent is not None
    assert agent.name == "My Custom Coding Agent", (
        f"name override not applied: {agent.name!r}"
    )
    assert agent.description == "Custom description for my org", (
        f"description override not applied: {agent.description!r}"
    )
