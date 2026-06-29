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

P1.1-D: per-agent endpoints (/card, /health, /requirements) now also
answer for metadata_only packs (Loader-driven fallback). The
``patched_app`` fixture imported from ``test_icoder_agents_compat``
sets up 3 synthetic packs: one executable + one metadata_only stub +
one invalid pack, plus a fake registry that only knows the
executable one. Tests under ``TestGet*ForMetadataOnly`` exercise
the new fallback paths.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote

import pytest

# P1.1-D: reuse the synthetic-pack fixture from the compat tests
# (it sets up exactly the 3 pack shapes — exec / metadata_only / invalid
# — we need to exercise the Loader-compat fallback).
from test_icoder_agents_compat import patched_app  # noqa: F401

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


# ── P1.1-D — Per-agent endpoints extended to metadata_only packs ───────────
#
# Uses the patched_app fixture (imported above) which sets up 3 synthetic
# packs on a tmp_path:
#   - test-exec     — v1.1 certified, registered with the fake registry
#   - test-stub     — v1.2 expert-stub, NOT in registry, Loader sees as
#                     metadata_only
#   - test-invalid  — v1.2 reference, NOT in registry, Loader sees as
#                     invalid (missing manifest.version)
#
# The 3 new test classes assert the per-agent endpoints now answer for
# the metadata_only stub and return a distinct error code for the
# invalid pack.


class TestGetAgentCardForMetadataOnly:
    def test_metadata_only_pack_returns_full_a2a_envelope(self, patched_app):
        ref = "icoder/test-stub@1.0.0"
        r = patched_app.get(f"/api/icoder/agents/{_q(ref)}/card")
        assert r.status_code == 200
        body = r.json()
        # Same envelope shape as the registry-path card
        for k in ("name", "version", "provider", "capabilities", "skills",
                  "defaultInputModes", "defaultOutputModes", "securitySchemes",
                  "metadata"):
            assert k in body, f"missing {k}"
        # metadata_only distinguishing flag
        ic = body["metadata"]["icoder"]
        assert ic["status"] == "metadata_only"
        assert ic["production_ready"] is False
        assert ic["agent_ref"] == ref
        assert isinstance(ic["why_not_executable"], list)
        assert len(ic["why_not_executable"]) > 0, (
            "metadata_only stub should surface at least one why_not_executable reason"
        )

    def test_invalid_pack_returns_404_AGENT_NOT_LOADABLE(self, patched_app):
        ref = "icoder/test-invalid@1.0.0"
        r = patched_app.get(f"/api/icoder/agents/{_q(ref)}/card")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "AGENT_NOT_LOADABLE"
        assert detail["agent_id"] == ref
        # Diagnostic info for the front-end
        assert "validation_errors" in detail
        assert "why_not_executable" in detail
        assert isinstance(detail["validation_errors"], list)

    def test_unknown_pack_still_returns_AGENT_NOT_FOUND(self, patched_app):
        r = patched_app.get("/api/icoder/agents/no-such-pack/card")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "AGENT_NOT_FOUND"


class TestGetAgentHealthForMetadataOnly:
    def test_metadata_only_pack_returns_overall_metadata_only(self, patched_app):
        ref = "icoder/test-stub@1.0.0"
        r = patched_app.get(f"/api/icoder/agents/{_q(ref)}/health")
        assert r.status_code == 200
        body = r.json()
        # registry.available flipped to false with reason
        assert body["registry"]["available"] is False
        assert body["registry"]["reason"] == "metadata_only"
        # Overall status set to the new value
        assert body["overall"] == "metadata_only"
        # Blocker explaining the state
        assert any("metadata_only" in b for b in body["blockers"])
        # Global runtime checks are still populated (they reflect the
        # runtime, not the specific pack)
        for k in ("faiss_index", "llm_provider", "mcp_tools", "recorder"):
            assert k in body, f"missing global runtime check: {k}"

    def test_invalid_pack_returns_404_AGENT_NOT_LOADABLE(self, patched_app):
        ref = "icoder/test-invalid@1.0.0"
        r = patched_app.get(f"/api/icoder/agents/{_q(ref)}/health")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "AGENT_NOT_LOADABLE"

    def test_unknown_pack_still_returns_AGENT_NOT_FOUND(self, patched_app):
        r = patched_app.get("/api/icoder/agents/no-such-pack/health")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "AGENT_NOT_FOUND"


class TestGetAgentRequirementsForMetadataOnly:
    def test_metadata_only_pack_returns_requirements_with_suppressed_files(self, patched_app):
        ref = "icoder/test-stub@1.0.0"
        r = patched_app.get(f"/api/icoder/agents/{_q(ref)}/requirements")
        assert r.status_code == 200
        body = r.json()
        # All required keys present
        for k in ("agent_id", "agent_ref", "format_version", "agent_type",
                  "tier", "tier_label", "experimental", "production_ready",
                  "permissions", "files", "mcp_tools", "env_vars", "experts",
                  "requirements", "human_review_required_when"):
            assert k in body, f"missing {k}"
        # metadata_only distinctions
        assert body["production_ready"] is False
        # MedCodER filesystem probe is suppressed for non-runnable packs
        assert body["files"] == []
        # env_vars still surfaces (the hard-coded list applies to all packs)
        assert any(e["name"] == "ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT"
                   for e in body["env_vars"])

    def test_invalid_pack_returns_404_AGENT_NOT_LOADABLE(self, patched_app):
        ref = "icoder/test-invalid@1.0.0"
        r = patched_app.get(f"/api/icoder/agents/{_q(ref)}/requirements")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "AGENT_NOT_LOADABLE"

    def test_unknown_pack_still_returns_AGENT_NOT_FOUND(self, patched_app):
        r = patched_app.get("/api/icoder/agents/no-such-pack/requirements")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "AGENT_NOT_FOUND"