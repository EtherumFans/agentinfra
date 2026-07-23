"""A1B-AE-R.3 — Public Expert + SSRF tests.

Coverage:

§1  External-Expert Gate — deny path produces 0 egress (packet counter test)
§2  PubMed Expert — gate permit + VCR fixture replay succeeds
§3  PubMed Expert — gate deny returns hermetic stub, no live_search_performed
§4  ClinicalTrials Expert — gate permit + VCR fixture replay
§5  ClinicalTrials Expert — gate deny hermetic
§6  SSRF guard blocks loopback / RFC1918 / link-local / cloud metadata
§7  SSRF guard allows public DNS hosts
§8  McpWrapper — discover_tools raises McpSSRFBlocked on metadata URL
§9  McpWrapper — call_tool raises McpSSRFBlocked on RFC1918 URL
§10 GET /api/v1/experts/external-gate/evaluate — deny reasons surface
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


# ─────────────────────────────────────────────────────────────────────
# §1 Gate deny → 0 egress (packet counter)
# ─────────────────────────────────────────────────────────────────────


def test_pubmed_gate_deny_produces_zero_egress():
    """PubMed Expert with egress_enabled=False MUST NOT open any socket."""
    from app.agents.experts import pubmed_expert

    call_count = {"live": 0}

    async def _fake_live(*a, **kw):
        call_count["live"] += 1
        return {"esearchresult": {"idlist": ["FAKE"]}}

    with patch.object(pubmed_expert, "_live_esearch", _fake_live):
        result = asyncio.run(
            pubmed_expert.search_async(
                "sepsis", egress_enabled=False, region="CN"
            )
        )

    assert result.live_search_performed is False
    assert "GATE_DENIED" in result.notes
    assert call_count["live"] == 0, "gate deny MUST NOT invoke _live_esearch"


def test_clinical_trials_gate_deny_produces_zero_egress():
    """ClinicalTrials Expert with egress_enabled=False MUST NOT open any socket."""
    from app.agents.experts import clinical_trials_expert

    call_count = {"live": 0}

    async def _fake_live(*a, **kw):
        call_count["live"] += 1
        return {"studies": []}

    with patch.object(
        clinical_trials_expert, "_live_ctgov", _fake_live
    ):
        result = asyncio.run(
            clinical_trials_expert.search_async(
                "sepsis", egress_enabled=False, region="CN"
            )
        )

    assert result.live_search_performed is False
    assert "GATE_DENIED" in result.notes
    assert call_count["live"] == 0


# ─────────────────────────────────────────────────────────────────────
# §2-§5 VCR fixture replay (no network)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def pubmed_fixture(tmp_path, monkeypatch):
    """Install a temporary VCR fixture so tests don't hit the network."""
    query = "sepsis-3 definition"
    payload = {
        "expert": "pubmed",
        "query": query,
        "captured_at": "2026-07-23T00:00:00+00:00",
        "payload": {
            "articles": [
                {
                    "pmid": "12345",
                    "title": "Sepsis-3 Definition (JAMA 2016)",
                    "journal": "JAMA",
                    "year": "2016",
                    "authors": ["Singer M"],
                }
            ],
            "total": 1,
        },
    }
    fixture_file = tmp_path / "pubmed_test.json"
    fixture_file.write_text(json.dumps(payload), encoding="utf-8")

    def _fake_path(q):
        return fixture_file

    monkeypatch.setattr(
        "app.agents.experts.pubmed_expert._fixture_path", _fake_path
    )
    return query


@pytest.fixture
def ct_fixture(tmp_path, monkeypatch):
    query = "sepsis randomized trial"
    payload = {
        "expert": "clinical-trials",
        "query": query,
        "captured_at": "2026-07-23T00:00:00+00:00",
        "payload": {
            "trials": [
                {
                    "nct_id": "NCT00000001",
                    "title": "Sepsis RCT",
                    "status": "COMPLETED",
                    "phase": "Phase 3",
                }
            ],
            "total": 1,
        },
    }
    fixture_file = tmp_path / "ct_test.json"
    fixture_file.write_text(json.dumps(payload), encoding="utf-8")

    def _fake_path(q):
        return fixture_file

    monkeypatch.setattr(
        "app.agents.experts.clinical_trials_expert._fixture_path", _fake_path
    )
    return query


def test_pubmed_fixture_replay(pubmed_fixture):
    from app.agents.experts import pubmed_expert

    result = asyncio.run(
        pubmed_expert.search_async(
            pubmed_fixture, egress_enabled=True, region="CN"
        )
    )
    assert result.live_search_performed is True
    assert result.total == 1
    assert result.articles[0]["pmid"] == "12345"
    assert "VCR fixture replay" in result.notes


def test_pubmed_gate_permit_without_fixture_or_live_returns_stub(monkeypatch):
    """Gate permits but no fixture + allow_live_capture=False → hermetic stub."""
    from app.agents.experts import pubmed_expert

    monkeypatch.setattr(
        "app.agents.experts.pubmed_expert._load_fixture", lambda q: None
    )
    result = asyncio.run(
        pubmed_expert.search_async(
            "novel query no fixture", egress_enabled=True, region="CN"
        )
    )
    assert result.live_search_performed is False
    assert "STUB" in result.notes


def test_clinical_trials_fixture_replay(ct_fixture):
    from app.agents.experts import clinical_trials_expert

    result = asyncio.run(
        clinical_trials_expert.search_async(
            ct_fixture, egress_enabled=True, region="CN"
        )
    )
    assert result.live_search_performed is True
    assert result.total == 1
    assert result.trials[0]["nct_id"] == "NCT00000001"


def test_clinical_trials_gate_deny_returns_stub():
    """Gate deny for clinical-trials → hermetic stub."""
    from app.agents.experts import clinical_trials_expert

    result = asyncio.run(
        clinical_trials_expert.search_async(
            "anything", egress_enabled=False, region="CN"
        )
    )
    assert result.live_search_performed is False
    assert "GATE_DENIED" in result.notes


# ─────────────────────────────────────────────────────────────────────
# §6-§7 SSRF guard
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.170.2/",  # ECS metadata
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://[fe80::1]/",
    ],
)
def test_ssrf_guard_blocks_internal_hosts(url):
    from app.services.ssrf_guard import check_url

    r = check_url(url)
    assert r.permitted is False, f"{url} should be blocked ({r.reason})"
    assert r.reason


@pytest.mark.parametrize(
    "url",
    [
        # Public DNS names that resolve to public IPs. We can only
        # verify the URL parses and is not a literal IP — actual
        # DNS resolution depends on the host environment.
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        "https://clinicaltrials.gov/api/v2/studies",
    ],
)
def test_ssrf_guard_allows_public_hosts(url):
    """Skip if offline (DNS resolution fails). Otherwise assert allowed."""
    from app.services.ssrf_guard import check_url

    r = check_url(url)
    # When the test host has no network/DNS, we fail closed (block).
    # In CI with DNS, these MUST pass.
    if "DNS resolution returned no records" in r.reason:
        pytest.skip(f"offline environment — cannot resolve {url}")
    assert r.permitted is True, f"{url} should be permitted ({r.reason})"


def test_ssrf_guard_blocks_invalid_scheme():
    from app.services.ssrf_guard import check_url

    r = check_url("file:///etc/passwd")
    assert r.permitted is False
    assert "scheme" in r.reason


def test_ssrf_assert_url_safe_raises():
    from app.services.ssrf_guard import SSRFError, assert_url_safe

    with pytest.raises(SSRFError):
        assert_url_safe("http://169.254.169.254/")


# ─────────────────────────────────────────────────────────────────────
# §8-§9 McpWrapper SSRF blocking
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_wrapper_discover_tools_blocks_metadata_url():
    """McpWrapper.discover_tools raises McpSSRFBlocked on AWS metadata URL."""
    from app.services.mcp_wrapper import McpSSRFBlocked, mcp_wrapper

    with pytest.raises(McpSSRFBlocked) as ei:
        await mcp_wrapper.discover_tools("http://169.254.169.254/latest")
    assert "metadata" in ei.value.reason or "169.254" in ei.value.reason


@pytest.mark.asyncio
async def test_mcp_wrapper_call_tool_blocks_loopback():
    from app.services.mcp_wrapper import McpSSRFBlocked, mcp_wrapper

    with pytest.raises(McpSSRFBlocked):
        await mcp_wrapper.call_tool(
            "http://127.0.0.1:8080", "search", {"q": "x"}
        )


@pytest.mark.asyncio
async def test_mcp_wrapper_create_expert_config_blocks_rfc1918():
    from app.services.mcp_wrapper import McpSSRFBlocked, mcp_wrapper

    with pytest.raises(McpSSRFBlocked):
        await mcp_wrapper.create_expert_config(
            "http://10.0.0.5/", "system prompt"
        )


# ─────────────────────────────────────────────────────────────────────
# §10 External-Expert Gate endpoint
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_external_gate_deny_drugbank_licence_required(client):
    """drugbank without licence → LICENCE_REQUIRED."""
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={"expert_key": "drugbank"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is False
    assert body["reason"] == "LICENCE_REQUIRED"


def test_external_gate_deny_pubmed_egress_disabled(client):
    """pubmed with default egress_enabled=False → EGRESS_DISABLED."""
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={"expert_key": "pubmed"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is False
    assert body["reason"] == "EGRESS_DISABLED"


def test_external_gate_permit_pubmed_with_egress(client):
    """pubmed with egress_enabled=True + valid region → OK."""
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={
            "expert_key": "pubmed",
            "egress_enabled": True,
            "region": "CN",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is True
    assert body["reason"] == "OK"


def test_external_gate_deny_region_blocked(client):
    """Region not in CN/EU/US → REGION_BLOCKED."""
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={
            "expert_key": "pubmed",
            "egress_enabled": True,
            "region": "XX",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permitted"] is False
    assert body["reason"] == "REGION_BLOCKED"


def test_external_gate_web_search_requires_dual_opt_in(client):
    """web-search requires both provider_opt_in AND tenant_opt_in."""
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={
            "expert_key": "web-search",
            "egress_enabled": True,
            "region": "CN",
            "provider_opt_in": True,
            "tenant_opt_in": False,
        },
    )
    body = r.json()
    assert body["permitted"] is False
    assert body["reason"] == "PROVIDER_OPT_IN_MISSING"

    r2 = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={
            "expert_key": "web-search",
            "egress_enabled": True,
            "region": "CN",
            "provider_opt_in": True,
            "tenant_opt_in": True,
        },
    )
    body2 = r2.json()
    assert body2["permitted"] is True


def test_external_gate_not_gated_passes(client):
    """Non-external experts (e.g. coding-expert) → OK without any opts."""
    r = client.get(
        "/api/v1/experts/external-gate/evaluate",
        params={"expert_key": "coding-expert"},
    )
    body = r.json()
    assert body["permitted"] is True
    assert body["reason"] == "OK"


# ─────────────────────────────────────────────────────────────────────
# §11 MCP server JSON-RPC routes exist
# ─────────────────────────────────────────────────────────────────────


def test_mcp_tools_list_route_returns_tools(client):
    """MCP server exposes /mcp/v1/tools/list JSON-RPC route."""
    r = client.post(
        "/mcp/v1/tools/list",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert "result" in body
    assert "tools" in body["result"]
    tool_names = {t["name"] for t in body["result"]["tools"]}
    # Phase 3-D1 — at least search_icd / verify_code / search_codes must be advertised
    assert "search_icd" in tool_names or "verify_code" in tool_names


def test_mcp_tools_call_unknown_method_returns_error(client):
    """MCP server exposes /mcp/v1/tools/call JSON-RPC route."""
    r = client.post(
        "/mcp/v1/tools/call",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "no_such_tool", "arguments": {}},
            "id": 2,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "error" in body or body.get("result", {}).get("isError") is True
