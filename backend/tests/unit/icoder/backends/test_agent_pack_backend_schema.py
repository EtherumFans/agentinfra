"""Tests for agent_pack schema backend_provider extension — Phase 4-A Task 3.

Verifies:
  - Old packs without backend_provider load cleanly (legacy path).
  - backend_provider can be top-level OR nested under agent.
  - backend_config can be a dict at top-level OR nested.
  - to_summary() exposes backend_provider + has_backend_config.
  - backend_config.tools.scope validation (mandatory ⊆ scope, forbidden ∩ scope = ∅).
  - All 4 runnable agents still load without regression.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from icoder_runtime.core.agent_pack_loader import load_pack
from icoder_runtime.core.agent_pack_schema import PackStatus


REPO_ROOT = Path(__file__).resolve().parents[4]  # tests/unit/icoder/backends → backend
OFFICIAL_AGENTS = REPO_ROOT / "official_agents"


# ── Helpers ─────────────────────────────────────────────────────────


def _load_official_pack(rel_path: str):
    path = OFFICIAL_AGENTS / rel_path / "agent_pack.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Backward compat: old packs without backend_provider ────────────


@pytest.mark.parametrize("agent_dir", [
    "compliance-guardrail",
    "code-validation",
    "note-completeness",
    "medical_coding",
])
def test_official_pack_loads_without_regression(agent_dir):
    """4 runnable agents must load without errors after the schema change."""
    pack = _load_official_pack(agent_dir)
    p = load_pack(pack)
    assert p.status in (PackStatus.EXECUTABLE, PackStatus.METADATA_ONLY)
    # No new validation errors introduced by the schema change.
    backend_errors = [
        e for e in p.validation_errors if "backend_" in e
    ]
    assert backend_errors == [], (
        f"agent {agent_dir} has backend_provider/backend_config errors: {backend_errors}"
    )
    # backend_provider defaults to empty (legacy path).
    # medical_coding may already have one if we add it later, but for now empty.
    assert isinstance(p.backend_provider, str)
    assert isinstance(p.backend_config, dict)


def test_old_pack_defaults_backend_provider_to_empty():
    """Old packs without backend_provider → backend_provider == '' (legacy)."""
    pack = _load_official_pack("compliance-guardrail")
    p = load_pack(pack)
    assert p.backend_provider == ""
    assert p.backend_config == {}


# ── New packs with backend_provider (top-level) ───────────────────


def test_pack_with_top_level_backend_provider_loads():
    """Packs can declare backend_provider at the top level."""
    pack = {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test-agent@1.0.0",
        "manifest": {"name": "Test Agent", "version": "1.0.0"},
        "system_prompt": "test",
        "requirements": {"min_runtime_version": "1.0.0"},
        "backend_provider": "icoder.rule-engine.v1",
        "backend_config": {"mode": "deterministic"},
    }
    p = load_pack(pack)
    assert p.backend_provider == "icoder.rule-engine.v1"
    assert p.backend_config == {"mode": "deterministic"}


def test_pack_with_nested_backend_provider_loads():
    """Packs can declare backend_provider nested under 'agent'."""
    pack = {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test-agent@1.0.0",
        "manifest": {"name": "Test Agent", "version": "1.0.0"},
        "system_prompt": "test",
        "requirements": {"min_runtime_version": "1.0.0"},
        "agent": {
            "backend_provider": "icoder.pure-llm.v1",
            "backend_config": {"llm": {"model": "deepseek-v4-flash"}},
        },
    }
    p = load_pack(pack)
    assert p.backend_provider == "icoder.pure-llm.v1"
    assert p.backend_config == {"llm": {"model": "deepseek-v4-flash"}}


# ── to_summary exposes backend fields ──────────────────────────────


def test_to_summary_includes_backend_provider_field():
    """Agent Hub card can read backend_provider via to_summary (Task 3 req #4)."""
    pack = {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test-agent@1.0.0",
        "manifest": {"name": "Test", "version": "1.0.0"},
        "system_prompt": "",
        "requirements": {"min_runtime_version": "1.0.0"},
        "backend_provider": "icoder.llm-with-tools.v1",
        "backend_config": {"tools": {"scope": ["verify"]}},
    }
    p = load_pack(pack)
    summary = p.to_summary()
    assert summary["backend_provider"] == "icoder.llm-with-tools.v1"
    assert summary["has_backend_config"] is True


def test_to_summary_for_legacy_pack_shows_empty_backend():
    """Old packs show empty backend_provider in summary."""
    pack = _load_official_pack("compliance-guardrail")
    p = load_pack(pack)
    summary = p.to_summary()
    assert summary["backend_provider"] == ""
    assert summary["has_backend_config"] is False


# ── Phase 4-B: note-completeness migrated to PureLLMProvider ──────


def test_note_completeness_pack_declares_pure_llm_backend():
    """Phase 4-B: note-completeness pack now declares backend_provider='icoder.pure-llm.v1'."""
    pack = _load_official_pack("note-completeness")
    p = load_pack(pack)
    assert p.backend_provider == "icoder.pure-llm.v1"
    # backend_config should now be populated with llm/fallback keys.
    assert isinstance(p.backend_config, dict)
    assert "llm" in p.backend_config
    assert p.backend_config["llm"]["model"] == "deepseek-chat"
    assert "fallback" in p.backend_config


def test_note_completeness_pack_summary_shows_pure_llm():
    """Agent Hub card summary reflects the migrated backend."""
    pack = _load_official_pack("note-completeness")
    p = load_pack(pack)
    summary = p.to_summary()
    assert summary["backend_provider"] == "icoder.pure-llm.v1"
    assert summary["has_backend_config"] is True


# ── Schema validation: backend_config.tools ───────────────────────


def test_backend_config_tools_mandatory_subset_scope_passes():
    pack = {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"name": "T", "version": "1.0.0"},
        "system_prompt": "",
        "requirements": {"min_runtime_version": "1.0.0"},
        "backend_provider": "icoder.llm-with-tools.v1",
        "backend_config": {
            "tools": {
                "scope": ["verify", "guidelines", "explore", "search"],
                "mandatory": ["verify", "guidelines"],
                "forbidden": [],
            }
        },
    }
    p = load_pack(pack)
    backend_errors = [e for e in p.validation_errors if "backend_config" in e]
    assert backend_errors == []


def test_backend_config_tools_mandatory_not_in_scope_fails():
    """Code Validation pattern: mandatory ⊆ scope."""
    pack = {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"name": "T", "version": "1.0.0"},
        "system_prompt": "",
        "requirements": {"min_runtime_version": "1.0.0"},
        "backend_provider": "icoder.llm-with-tools.v1",
        "backend_config": {
            "tools": {
                "scope": ["verify"],  # missing 'guidelines' (mandatory)
                "mandatory": ["verify", "guidelines"],
            }
        },
    }
    p = load_pack(pack)
    assert any("mandatory must be subset" in e for e in p.validation_errors)


def test_backend_config_tools_forbidden_in_scope_fails():
    """Compliance Guardrail pattern: forbidden ∩ scope = ∅."""
    pack = {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"name": "T", "version": "1.0.0"},
        "system_prompt": "",
        "requirements": {"min_runtime_version": "1.0.0"},
        "backend_provider": "icoder.llm-with-tools.v1",
        "backend_config": {
            "tools": {
                "scope": ["verify", "guidelines", "explore", "search"],
                "forbidden": ["search"],
            }
        },
    }
    p = load_pack(pack)
    assert any("forbidden must not intersect" in e for e in p.validation_errors)


def test_backend_config_non_dict_warns():
    """Non-dict backend_config produces a validation_warning."""
    pack = {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"name": "T", "version": "1.0.0"},
        "system_prompt": "",
        "requirements": {"min_runtime_version": "1.0.0"},
        "backend_provider": "icoder.rule-engine.v1",
        "backend_config": "not a dict",  # invalid
    }
    p = load_pack(pack)
    assert any("backend_config" in w for w in p.validation_warnings)
