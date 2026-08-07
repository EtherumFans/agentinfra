"""Sprint 2 (Phase A1E-GP2) — Developer Golden Path verification tests.

Verifies the 6 Sprint 2 goals end-to-end:

  Goal A — Generic Agent Creation: templates endpoint exposes non-medical templates
  Goal B — Runtime decoupling: a DB-stored Generic Agent runs without MedCodER
  Goal C — Test Console path: real runtime call returns structured envelope
  Goal D — API Client lifecycle: rotate / disable / enable roundtrip
  Goal E — Code Tab: covered by frontend snapshot (no backend test needed)
  Goal F — External Consumer: full create-agent → token → run loop

These tests use ``LLM_PROVIDER=mock`` so they don't hit real DeepSeek.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────
# Goal A — Generic Agent templates available
# ─────────────────────────────────────────────────────────────────────


def test_goal_a_generic_templates_present(client: TestClient) -> None:
    """GET /api/rest/v1/agent_definitions/templates surfaces translator-blank + summarizer-blank.

    These two templates are non-medical — they prove the platform can host
    Generic Agents (no MedCodER coupling, no ICD codes, no clinical knowledge).
    """
    resp = client.get("/api/rest/v1/agent_definitions/templates")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    template_ids = {t["id"] for t in templates}
    assert "translator-blank" in template_ids, (
        "Goal A: translator-blank template missing — Sprint 2 Goal A regression"
    )
    assert "summarizer-blank" in template_ids, (
        "Goal A: summarizer-blank template missing — Sprint 2 Goal A regression"
    )


def test_goal_a_generic_template_has_empty_expert_ids(client: TestClient) -> None:
    """Generic Agent templates must not bind to medical experts."""
    resp = client.get("/api/rest/v1/agent_definitions/templates")
    templates = resp.json()["templates"]
    translator = next(t for t in templates if t["id"] == "translator-blank")
    summarizer = next(t for t in templates if t["id"] == "summarizer-blank")
    for tmpl in (translator, summarizer):
        assert tmpl["expert_ids"] == [], (
            f"Goal A: {tmpl['id']} binds to medical experts — breaks Generic Agent contract"
        )
        # No active medical/ICD/MedCodER coupling. We allow negation phrases
        # like "no medical coding" but reject any active invocation.
        # Strip "no X" / "without X" / "not X" phrases before scanning.
        import re
        stripped = re.sub(
            r"\b(?:no|without|not|never)\s+[a-z\s-]{0,30}",
            "",
            tmpl["system_prompt"].lower(),
        )
        for forbidden in ("medcoder", "icd-10", "icd10", "diagnosis"):
            assert forbidden not in stripped, (
                f"Goal A: {tmpl['id']} system_prompt references '{forbidden}' "
                f"outside a negation — not a true Generic Agent"
            )


# ─────────────────────────────────────────────────────────────────────
# Goal B — Runtime decoupling (no MedCodER for generic agents)
# ─────────────────────────────────────────────────────────────────────


def test_goal_b_medical_coding_id_set_does_not_include_generic_agents() -> None:
    """Module-level guard: ``_MEDICAL_CODING_AGENT_IDS`` excludes generic templates.

    This catches accidental coupling — if someone adds translator-blank to the
    Medical Coding routing frozenset, this test fails loudly.
    """
    from app.api.agent_run import _MEDICAL_CODING_AGENT_IDS
    forbidden = {"translator-blank", "summarizer-blank"}
    overlap = _MEDICAL_CODING_AGENT_IDS & forbidden
    assert not overlap, (
        f"Goal B: _MEDICAL_CODING_AGENT_IDS now includes {overlap} — "
        f"Generic Agents must NOT route to CodingRuntimeDispatcher"
    )


def test_goal_b_db_agent_runs_via_synthesized_pack(client: TestClient) -> None:
    """Goal B + C: a DB-stored Agent without an agent_pack.json file still runs.

    Flow:
      1. POST /api/rest/v1/agent_definitions to create a Generic Agent in the DB
      2. POST /api/v1/agents/{id}/run — must NOT 404
      3. Response envelope is well-formed (run_id, trace_id, error flag set)

    Before Goal B fix, this test failed because ``_load_pack_by_agent_id``
    only scanned ``official_agents/`` for .icoder-agent files — DB Agents
    had no pack file to load and the runtime returned ``unknown_agent``.
    """
    # Step 1 — create a DB Agent via the management API
    create = client.post("/api/rest/v1/agent_definitions", json={
        "name": "Sprint2 Generic Test Agent",
        "description": "Goal B verification — DB-stored, no pack file",
        "system_prompt": (
            "<role>\nYou are a friendly test assistant. Echo the user's "
            "input back in uppercase. No medical knowledge required.\n</role>"
        ),
        "icon": "TestTube",
        "category": "通用",
        "expert_ids": [],
        "default_expert_id": "",
        "a2a_enabled": False,
        "config": {},
    })
    assert create.status_code in (200, 201), create.text
    agent_id = create.json()["id"]

    # Step 2 — invoke the runtime (the fix: _load_pack_from_db fallback fires)
    run = client.post(f"/api/v1/agents/{agent_id}/run", json={
        "input": {"text": "hello world"},
        "runtime_mode": "corti_like_fast",
    })
    assert run.status_code == 200, run.text
    data = run.json()

    # Step 3 — envelope sanity
    assert data["agent_id"] == agent_id
    assert data["run_id"].startswith("run-")
    assert data["trace_id"].startswith("trace-")
    # Mock provider succeeds; if real provider had failed, error_reason would
    # explain. The key assertion: NOT ``unknown_agent`` (the pre-fix failure).
    if data["error"]:
        assert data["error_reason"] != "unknown_agent", (
            "Goal B regression: DB-stored Agent returned unknown_agent — "
            "_load_pack_from_db fallback is not firing"
        )


# ─────────────────────────────────────────────────────────────────────
# Goal C — Test Console response envelope shape
# ─────────────────────────────────────────────────────────────────────


_REQUIRED_RUN_FIELDS = (
    "agent_id", "run_id", "trace_id", "trace_url", "runtime_mode", "latency_ms",
    "cost", "summary", "result", "evidence", "warnings",
    "manual_review_required", "trace_events", "error", "error_reason",
)


def test_goal_c_console_envelope_shape(client: TestClient) -> None:
    """Goal C: Test Console response carries all 14 envelope fields.

    The Test Console calls POST /api/v1/agents/{id}/run with streaming=False.
    This test asserts the same envelope the Console relies on.
    """
    create = client.post("/api/rest/v1/agent_definitions", json={
        "name": "Sprint2 Goal C Envelope Test",
        "system_prompt": "Echo test",
        "expert_ids": [],
    })
    agent_id = create.json()["id"]

    resp = client.post(f"/api/v1/agents/{agent_id}/run", json={
        "input": {"text": "test"},
    })
    data = resp.json()
    for field in _REQUIRED_RUN_FIELDS:
        assert field in data, f"Goal C: missing field {field!r} in run envelope"


def test_goal_c_trace_url_is_deep_link(client: TestClient) -> None:
    """Goal C: trace_url is a frontend deep-link, not a backend trace ID."""
    create = client.post("/api/rest/v1/agent_definitions", json={
        "name": "Sprint2 Goal C TraceURL",
        "system_prompt": "Echo",
        "expert_ids": [],
    })
    agent_id = create.json()["id"]
    resp = client.post(f"/api/v1/agents/{agent_id}/run", json={"input": {"text": "x"}})
    data = resp.json()
    assert data["trace_url"] == f"/ai-studio/runs/{data['run_id']}/trace"


# ─────────────────────────────────────────────────────────────────────
# Goal D — API Client lifecycle (rotate / disable / enable)
# ─────────────────────────────────────────────────────────────────────


def test_goal_d_lifecycle_round_trip(client: TestClient) -> None:
    """Goal D: Console can rotate, disable, enable an OAuth Client.

    Asserts the three endpoints the new Console buttons call (oauthApi.rotate /
    disable / enable) actually exist on the backend and round-trip cleanly.
    """
    create = client.post("/api/clients", json={
        "name": "Sprint2 Goal D Client",
        "scopes": "agents:run runs:read",
    })
    assert create.status_code == 201, create.text
    client_id = create.json()["client_id"]
    original_secret = create.json()["client_secret"]

    # Disable
    resp = client.post(f"/api/clients/{client_id}/disable")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Enable
    resp = client.post(f"/api/clients/{client_id}/enable")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    # Rotate
    resp = client.post(f"/api/clients/{client_id}/rotate")
    assert resp.status_code == 200
    new_secret = resp.json()["client_secret"]
    assert new_secret != original_secret, "Goal D: rotate must mint a new secret"
    assert new_secret.startswith("ics_")


def test_goal_d_disabled_client_token_rejected(client: TestClient) -> None:
    """Goal D: disabled OAuth Client cannot mint a token (until re-enabled)."""
    create = client.post("/api/clients", json={
        "name": "Sprint2 Goal D Token Reject",
        "scopes": "agents:run",
    })
    client_id = create.json()["client_id"]
    secret = create.json()["client_secret"]

    # Disable
    client.post(f"/api/clients/{client_id}/disable")

    # Token mint must now fail
    resp = client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
        "scope": "agents:run",
    })
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Goal F — External Consumer end-to-end (token + agent run)
# ─────────────────────────────────────────────────────────────────────


def test_goal_f_external_consumer_e2e(client: TestClient) -> None:
    """Goal F: external consumer can mint token + invoke a Generic Agent.

    This is the canonical "external consumer" verification — uses only the
    public OAuth + agent run endpoints, exactly like run-agent.mjs.
    """
    # 1. Create OAuth Client (in Console this happens via UI)
    create_client = client.post("/api/clients", json={
        "name": "Sprint2 External Consumer",
        "scopes": "agents:run runs:read",
    })
    assert create_client.status_code == 201
    client_id = create_client.json()["client_id"]
    client_secret = create_client.json()["client_secret"]

    # 2. Create a Generic Agent to invoke
    create_agent = client.post("/api/rest/v1/agent_definitions", json={
        "name": "Sprint2 Goal F Echo Agent",
        "system_prompt": "Echo the input verbatim.",
        "expert_ids": [],
    })
    agent_id = create_agent.json()["id"]

    # 3. Mint token (external consumers do this every call)
    token_resp = client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "agents:run",
    })
    assert token_resp.status_code == 200
    access_token = token_resp.json()["access_token"]

    # 4. Invoke the agent as a Bearer-authenticated external caller
    run_resp = client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={"input": {"text": "hello from external consumer"}},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["run_id"].startswith("run-")
    assert data["trace_id"]
    # The pre-Goal-B bug was unknown_agent here; that must not regress.
    if data["error"]:
        assert data["error_reason"] != "unknown_agent"
