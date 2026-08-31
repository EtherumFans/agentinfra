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
    """Phase A1D.5 — compliance-guardrail now ships a real backend_provider
    (``icoder.rule-engine.v1``) instead of the empty legacy default. The
    pack was upgraded as part of the v1.2 migration; the test was
    asserting the pre-migration state.
    """
    pack = _load_official_pack("compliance-guardrail")
    p = load_pack(pack)
    assert p.backend_provider == "icoder.rule-engine.v1"
    assert p.backend_config  # populated dict


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
    """Phase A1D.5 — compliance-guardrail summary now shows the real
    backend_provider after the v1.2 migration upgrade.
    """
    pack = _load_official_pack("compliance-guardrail")
    p = load_pack(pack)
    summary = p.to_summary()
    assert summary["backend_provider"] == "icoder.rule-engine.v1"
    assert summary["has_backend_config"] is True


# ── Note Completeness: local deterministic documentation rules ─────


def test_note_completeness_pack_declares_documentation_rule_backend():
    """The user path is local and does not require an external model."""
    pack = _load_official_pack("note-completeness")
    p = load_pack(pack)
    assert p.backend_provider == "icoder.documentation-rule-engine.v1"
    assert isinstance(p.backend_config, dict)
    assert p.backend_config["rules"]["network_required"] is False


def test_note_completeness_pack_summary_shows_documentation_rules():
    """Agent Hub summary reflects the deterministic backend."""
    pack = _load_official_pack("note-completeness")
    p = load_pack(pack)
    summary = p.to_summary()
    assert summary["backend_provider"] == "icoder.documentation-rule-engine.v1"
    assert summary["has_backend_config"] is True


# ── Code Validation: governed local baseline + optional semantic review ──


def test_code_validation_pack_declares_governed_catalog_backend():
    pack = _load_official_pack("code-validation")
    p = load_pack(pack)
    assert p.backend_provider == "icoder.governed-code-validation.v1"
    assert p.backend_config["catalog_baseline"]["integrity_required"] is True
    assert p.backend_config["catalog_baseline"]["billing_authoritative"] is False
    assert p.backend_config["semantic_enhancement"]["default_enabled"] is False
    assert p.raw["manifest"]["human_review"] == "required"
    assert p.raw["llm_capabilities"]["required_models"] == []


def test_icd10_navigator_pack_declares_governed_local_index_backend():
    pack = _load_official_pack("icd10_navigator")
    p = load_pack(pack)
    assert p.backend_provider == "icoder.governed-icd-navigator.v1"
    config = p.backend_config["catalog_navigation"]
    assert config["asset_id"] == "cn.icd10cn.catalog"
    assert config["integrity_required"] is True
    assert config["network_required"] is False
    assert config["maximum_candidate_blocks"] == 3
    assert config["maximum_rephrasing_attempts"] == 1
    assert config["instructional_notes_available"] is False
    assert config["billing_authoritative"] is False
    assert p.raw["llm_capabilities"]["required_models"] == []
    assert p.raw["manifest"]["human_review"] == "required"
    assert p.raw["output_contract"]["schema_ref"] == (
        "icoder/Icd10NavigatorOutput/v4"
    )


def test_evidence_ranker_pack_declares_documentation_grounding_only_backend():
    pack = _load_official_pack("evidence-ranker")
    p = load_pack(pack)
    assert p.backend_provider == "icoder.governed-evidence-ranker.v1"
    config = p.backend_config["documentation_grounding"]
    assert config["policy_id"] == "icoder.documentation-grounding-ranking"
    assert config["maximum_evidence_items"] == 50
    assert config["source_span_exact_match"] is True
    assert config["clinical_support_assessed"] is False
    assert config["network_required"] is False
    assert p.raw["llm_capabilities"]["required_models"] == []
    assert p.raw["manifest"]["human_review"] == "required"
    assert p.raw["output_contract"]["schema_ref"] == (
        "icoder/EvidenceRankerOutput/v4"
    )
    schemas = p.raw["output_contract"]["field_schemas"]
    assert schemas["ranking_basis"]["const"] == "DOCUMENTATION_GROUNDING_ONLY"
    assert schemas["ranked_evidence"]["maxItems"] == 50
    score = schemas["ranked_evidence"]["items"]["properties"][
        "documentation_grounding_score"
    ]
    assert score["minimum"] == 0
    assert score["maximum"] == 1


def test_evidence_extractor_pack_declares_governed_exact_mention_backend():
    pack = _load_official_pack("evidence_extractor")
    p = load_pack(pack)
    assert p.backend_provider == "icoder.governed-evidence-extractor.v1"
    config = p.backend_config["exact_mention_extraction"]
    assert config["asset_id"] == "cn.icd10cn.catalog"
    assert config["integrity_required"] is True
    assert config["network_required"] is False
    assert config["maximum_input_codes"] == 20
    assert config["maximum_mentions_per_code"] == 5
    assert config["clinical_support_assessed"] is False
    assert config["billing_authoritative"] is False
    assert p.raw["llm_capabilities"]["required_models"] == []
    assert p.raw["manifest"]["human_review"] == "required"
    assert p.raw["output_contract"]["schema_ref"] == "icoder/CodedEvidence/v11"
    schemas = p.raw["output_contract"]["field_schemas"]
    assert schemas["match_basis"]["const"] == (
        "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY"
    )
    assert schemas["uncoded_findings"]["maxItems"] == 0


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
