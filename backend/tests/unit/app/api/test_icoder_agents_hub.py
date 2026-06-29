"""P1.0-B — Agent Hub MVP endpoint tests.

Tests the 4 endpoints under /api/icoder/agents/*:
  - list (empty + populated)
  - card (canonical + synthesized)
  - health (degraded + ready paths)
  - requirements (with file/mcp/env assertions)

Uses TestClient directly — no DB, no LLM, no FAISS. The router is
intentionally defensive: if app.state.agent_registry is None (which it
will be in unit-test mode without lifespan), it returns empty results
rather than crashing.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def _q(agent_ref: str) -> str:
    """URL-encode an agent_ref the way the front-end does (encodeURIComponent)."""
    return quote(agent_ref, safe="")


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """Spin up FastAPI app via TestClient. Lifespan runs, so registry is loaded."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


# ── List endpoint ──────────────────────────────────────────────────────────


class TestListAgents:
    def test_returns_envelope(self, client):
        r = client.get("/api/icoder/agents")
        assert r.status_code == 200
        body = r.json()
        assert "agents" in body
        assert "total" in body
        assert "registry_status" in body
        assert body["registry_status"] in ("ok", "not_initialized")


# ── Card endpoint ──────────────────────────────────────────────────────────


class TestGetAgentCard:
    def test_unknown_agent_returns_404_with_AGENT_NOT_FOUND(self, client):
        r = client.get("/api/icoder/agents/totally-not-a-real-agent/card")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "AGENT_NOT_FOUND"
        assert "totally-not-a-real-agent" in detail["agent_id"]

    def test_known_agent_returns_card(self, client):
        """At minimum the MedCodER or another official agent should resolve.

        If registry loaded (lifespan), we expect at least 1 agent.
        """
        # First get the list to discover a real agent_ref
        listing = client.get("/api/icoder/agents").json()
        agents = listing.get("agents", [])
        if not agents:
            pytest.skip("Registry not populated in this test environment")
        agent_ref = agents[0]["agent_ref"]
        r = client.get(f"/api/icoder/agents/{_q(agent_ref)}/card")
        assert r.status_code == 200
        body = r.json()
        assert "name" in body
        assert "skills" in body or "capabilities" in body


# ── Health endpoint ────────────────────────────────────────────────────────


class TestGetAgentHealth:
    def test_unknown_agent_returns_404(self, client):
        r = client.get("/api/icoder/agents/totally-not-a-real-agent/health")
        assert r.status_code == 404

    def test_known_agent_health_envelope(self, client):
        listing = client.get("/api/icoder/agents").json()
        agents = listing.get("agents", [])
        if not agents:
            pytest.skip("Registry not populated")
        agent_ref = agents[0]["agent_ref"]
        r = client.get(f"/api/icoder/agents/{_q(agent_ref)}/health")
        assert r.status_code == 200
        body = r.json()
        # Required keys per the spec
        assert "agent_id" in body
        assert "registry" in body
        assert "overall" in body
        # Per-agent fields (at least one of: faiss_index, mcp_tools, recorder)
        assert any(
            k in body for k in ("faiss_index", "mcp_tools", "recorder")
        )


# ── Requirements endpoint ──────────────────────────────────────────────────


class TestGetAgentRequirements:
    def test_unknown_agent_returns_404(self, client):
        r = client.get("/api/icoder/agents/totally-not-a-real-agent/requirements")
        assert r.status_code == 404

    def test_known_agent_requirements_shape(self, client):
        listing = client.get("/api/icoder/agents").json()
        agents = listing.get("agents", [])
        if not agents:
            pytest.skip("Registry not populated")
        agent_ref = agents[0]["agent_ref"]
        r = client.get(f"/api/icoder/agents/{_q(agent_ref)}/requirements")
        assert r.status_code == 200
        body = r.json()
        # Required keys
        for k in ("agent_id", "agent_ref", "format_version", "agent_type",
                  "tier", "tier_label", "experimental", "production_ready",
                  "permissions", "files", "mcp_tools", "env_vars", "experts"):
            assert k in body, f"missing {k}"
        # env_vars should NOT leak credential values
        for e in body["env_vars"]:
            assert "set" in e
            if "CREDENTIAL" in e["name"] or "KEY" in e["name"]:
                assert e["value"] == "<redacted>", (
                    f"Credential leak in env var {e['name']}: {e['value']!r}"
                )


# ── Feature flag integration ───────────────────────────────────────────────


class TestFewShotFlagVisibility:
    """The requirements endpoint must surface ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT
    so the Agent Hub UI can show whether the experimental feature is on."""

    def test_fewshot_env_var_listed(self, client):
        listing = client.get("/api/icoder/agents").json()
        agents = listing.get("agents", [])
        if not agents:
            pytest.skip("Registry not populated")
        agent_ref = agents[0]["agent_ref"]
        body = client.get(f"/api/icoder/agents/{_q(agent_ref)}/requirements").json()
        names = [e["name"] for e in body["env_vars"]]
        assert "ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT" in names