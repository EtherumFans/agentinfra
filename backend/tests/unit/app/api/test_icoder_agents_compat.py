"""P1.1-C — per-agent validation + compatibility endpoints.

Tests ``/api/icoder/agents/{agent_id}/{validation,compatibility}``.

Strategy: monkeypatch ``_official_agents_dir()`` to a tmp_path populated
with three synthetic packs (executable / metadata_only / invalid) and
monkeypatch ``_get_registry()`` to return a fake registry index. This
isolates the test from the 16 on-disk packs while exercising the real
endpoints via TestClient.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from urllib.parse import quote

import pytest


def _enc(ref: str) -> str:
    """URL-encode an agent_ref the way the front-end does (encodeURIComponent)."""
    return quote(ref, safe="")

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


# ── Fixtures ────────────────────────────────────────────────────────────────


def _write_pack(root, name: str, pack: dict) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent_pack.json").write_text(json.dumps(pack), encoding="utf-8")


def _executable_v11_pack() -> dict:
    return {
        "agent_ref": "icoder/test-exec@1.0.0",
        "format_version": "1.1",
        "agent_type": "certified",
        "manifest": {
            "name": "Test Executable",
            "version": "1.0.0",
            "description": "V1.1 certified with real expert.",
        },
        "system_prompt": "You are test.",
        "requirements": {"min_runtime_version": "1.0.0"},
        "experts": [
            {
                "id": "main",
                "name": "Main",
                "role": "primary",
                "description": "primary expert",
                "system_prompt": "do thing",
                "tools": ["tool_a"],
                "model": "deepseek-v4-flash",
            }
        ],
        "tools": [
            {"id": "tool_a", "name": "tool_a", "tier": 1, "executor_file": "x.py"}
        ],
    }


def _metadata_only_v12_pack() -> dict:
    return {
        "agent_ref": "icoder/test-stub@1.0.0",
        "format_version": "1.2",
        "agent_type": "expert-stub",
        "manifest": {
            "name": "Test Stub",
            "version": "1.0.0",
            "description": "expert-stub skeleton, no real expert.",
        },
        "system_prompt": "stub.",
        "requirements": {"min_runtime_version": "1.0.0"},
        "experts": [
            {"id": "stub", "name": "Stub", "role": "primary", "description": "skeleton"}
        ],
        "tools": [],
    }


def _invalid_v12_pack() -> dict:
    return {
        "agent_ref": "icoder/test-invalid@1.0.0",
        "format_version": "1.2",
        "agent_type": "reference",
        "manifest": {
            # missing version -> INVALID
            "name": "Test Invalid",
        },
        "system_prompt": "x",
        "requirements": {"min_runtime_version": "1.0.0"},
        "experts": [],
        "tools": [],
    }


@pytest.fixture
def patched_app(tmp_path, monkeypatch):
    """Spin up the app with agents_dir replaced by a tmp_path with 3 packs,
    and a fake registry that registers only the v1.1 executable pack."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import icoder_agents_compat, icoder_agents_hub

    # 3 synthetic packs on tmp_path
    _write_pack(tmp_path, "test-exec", _executable_v11_pack())
    _write_pack(tmp_path, "test-stub", _metadata_only_v12_pack())
    _write_pack(tmp_path, "test-invalid", _invalid_v12_pack())

    monkeypatch.setattr(icoder_agents_compat, "_official_agents_dir", lambda: tmp_path)
    monkeypatch.setattr(icoder_agents_hub, "_official_agents_dir", lambda: tmp_path)

    # Fake registry: the v1.1 pack is "registered" with id = exec_id
    fake_rec = SimpleNamespace(
        agent_id="test-exec-id",
        pack_data={"agent_ref": "icoder/test-exec@1.0.0"},
    )

    def fake_get_registry():
        return SimpleNamespace(list_all=lambda: [fake_rec])

    monkeypatch.setattr(icoder_agents_compat, "_get_registry", fake_get_registry)
    monkeypatch.setattr(icoder_agents_hub, "_get_registry", fake_get_registry)

    with TestClient(app) as c:
        yield c


# ── /validation ────────────────────────────────────────────────────────────


class TestAgentValidation:
    def test_unknown_agent_returns_404_AGN(self, patched_app):
        r = patched_app.get("/api/icoder/agents/no-such-pack/validation")
        assert r.status_code == 404
        body = r.json()
        assert body["detail"]["error_code"] == "AGENT_NOT_FOUND"
        assert body["detail"]["agent_id"] == "no-such-pack"

    def test_executable_pack_returns_status(self, patched_app):
        r = patched_app.get(f"/api/icoder/agents/{_enc('icoder/test-exec@1.0.0')}/validation")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "executable"
        assert body["production_ready"] is True
        assert body["agent_type"] == "certified"
        assert body["format_version"] == "1.1"
        assert body["validation_errors"] == []
        assert body["why_not_executable"] == []
        assert body["expert_count"] == 1
        assert body["tool_count"] == 1

    def test_metadata_only_pack_returns_why(self, patched_app):
        r = patched_app.get(f"/api/icoder/agents/{_enc('icoder/test-stub@1.0.0')}/validation")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "metadata_only"
        assert body["production_ready"] is False
        assert body["agent_type"] == "expert-stub"
        # expert-stub skeleton: no real expert wired
        assert any("expert-stub" in r for r in body["why_not_executable"])
        assert body["validation_errors"] == []

    def test_invalid_pack_returns_errors(self, patched_app):
        r = patched_app.get(f"/api/icoder/agents/{_enc('icoder/test-invalid@1.0.0')}/validation")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "invalid"
        assert body["production_ready"] is False
        # Should have at least the missing version error
        assert any("version" in e for e in body["validation_errors"])
        # why_not_executable should lead with INVALID
        assert any("INVALID" in w for w in body["why_not_executable"])


# ── /compatibility ─────────────────────────────────────────────────────────


class TestAgentCompatibility:
    def test_unknown_agent_returns_404_AGN(self, patched_app):
        r = patched_app.get("/api/icoder/agents/no-such-pack/compatibility")
        assert r.status_code == 404
        body = r.json()
        assert body["detail"]["error_code"] == "AGENT_NOT_FOUND"

    def test_known_pack_returns_entry_and_summary(self, patched_app):
        r = patched_app.get(f"/api/icoder/agents/{_enc('icoder/test-exec@1.0.0')}/compatibility")
        assert r.status_code == 200
        body = r.json()
        assert "entry" in body
        assert "report_summary" in body
        e = body["entry"]
        assert e["agent_ref"] == "icoder/test-exec@1.0.0"
        assert e["status"] == "executable"
        assert e["registered"] is True
        assert e["registry_agent_id"] == "test-exec-id"
        # summary counters
        rs = body["report_summary"]
        assert rs["total_discovered"] == 3
        assert rs["total_registered"] == 1
        assert rs["by_status"]["executable"] == 1
        assert rs["by_status"]["metadata_only"] == 1
        assert rs["by_status"]["invalid"] == 1

    def test_metadata_only_pack_reports_not_registered(self, patched_app):
        r = patched_app.get(f"/api/icoder/agents/{_enc('icoder/test-stub@1.0.0')}/compatibility")
        assert r.status_code == 200
        e = r.json()["entry"]
        assert e["status"] == "metadata_only"
        assert e["registered"] is False
        assert e["registry_agent_id"] is None

    def test_invalid_pack_reports_not_registered(self, patched_app):
        r = patched_app.get(f"/api/icoder/agents/{_enc('icoder/test-invalid@1.0.0')}/compatibility")
        assert r.status_code == 200
        e = r.json()["entry"]
        assert e["status"] == "invalid"
        assert e["registered"] is False


# ── /api/icoder/agents list endpoint (P1.1-C: Loader-driven) ──────────────


class TestListAgentsP11C:
    def test_list_includes_loader_discovered_packs(self, patched_app):
        # P1.1-C contract: list_agents is Loader-driven, so packs surfaced
        # by the Loader (via the patched _official_agents_dir) MUST appear.
        # The real official_agents/ may or may not be shadowed depending on
        # import order, so we assert >= 3 (the 3 synthetic packs) rather
        # than an exact count.
        r = patched_app.get("/api/icoder/agents")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 3
        assert "summary" in body
        s = body["summary"]
        # executable + metadata_only + invalid at minimum
        assert s["executable"] >= 1
        assert s["metadata_only"] >= 1
        assert s["invalid"] >= 1

    def test_list_summary_shape(self, patched_app):
        r = patched_app.get("/api/icoder/agents")
        body = r.json()
        s = body["summary"]
        for k in ("total_discovered", "total_registered", "executable",
                  "metadata_only", "invalid", "production_ready"):
            assert k in s, f"missing {k}"

    def test_list_agents_have_loader_fields(self, patched_app):
        r = patched_app.get("/api/icoder/agents")
        agents = r.json()["agents"]
        # Each entry must carry the new P1.1-C fields
        for a in agents:
            assert "status" in a
            assert a["status"] in ("executable", "metadata_only", "invalid", "unknown")
            assert "agent_type" in a
            assert "format_version" in a
            assert "registered" in a
            assert isinstance(a["registered"], bool)
            assert "production_ready" in a
            assert "agent_ref" in a
