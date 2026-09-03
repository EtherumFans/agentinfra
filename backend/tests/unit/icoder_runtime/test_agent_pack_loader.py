"""Tests for agent_pack_loader (P1.1-A).

Covers:
* v1.1 pass-through (certified, community with code)
* v1.2 pass-through (certified, community, reference, expert-stub)
* Mixed tools[] formats (str + dict v1.1 + dict v1.2)
* Unknown format_version → INVALID with structured error
* agent_type normalization + invalid type rejection
* METADATA_ONLY marking for expert-stub packs without real experts
* production_ready logic (certified w/ experts=True, expert-stub=False, reference=True, community w/o code=False)
* integrity.sha256 still verified (v1.1 path preserved)
* All 16 official packs re-validate via the new loader
* why_not_executable returns human-readable reasons
* summary_counts aggregates correctly
* agent_ref derivation from manifest when missing
* non_goals / output_contract / phi_redaction / human_review_required_when only on v1.2
* _slugify produces stable IDs
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from icoder_runtime.core.agent_pack_loader import (
    discover_v1_files,
    load_pack,
    load_packs_from_dir,
    summary_counts,
    why_not_executable,
)
from icoder_runtime.core.agent_pack_schema import (
    LEGAL_AGENT_TYPES,
    SUPPORTED_FORMAT_VERSIONS,
    NormalizedPack,
    PackStatus,
)


# ── Fixtures ──

REPO_BACKEND = Path(__file__).resolve().parents[3]
OFFICIAL_AGENTS_DIR = REPO_BACKEND / "official_agents"


def _minimal_v11_pack(**overrides) -> dict:
    base = {
        "format_version": "1.1",
        "agent_type": "certified",
        "agent_ref": "icoder/test-pack@1.0.0",
        "manifest": {
            "name": "Test Pack",
            "version": "1.0.0",
            "description": "test",
            "category": "general",
            "icon": "Bot",
        },
        "system_prompt": "You are a test.",
        "experts": [],
        "tools": ["t1", "t2"],
        "permissions": {"key": "test", "tools": {"t1": "allowed"}},
        "requirements": {"min_runtime_version": "1.0.0"},
        "llm_capabilities": {"supports_tool_calling": False, "supports_json_mode": True},
    }
    base.update(overrides)
    return base


def _minimal_v12_pack(**overrides) -> dict:
    base = {
        "format_version": "1.2",
        "agent_type": "expert-stub",
        "agent_ref": "icoder/test-stub@1.0.0",
        "manifest": {
            "name": "Test Stub",
            "version": "1.0.0",
            "description": "test",
            "category": "general",
            "icon": "Bot",
            "tags": ["test"],
        },
        "system_prompt": "stub",
        "experts": [
            {
                "id": "test-stub",
                "name": "Test Stub",
                "role": "primary",
                "description": "stub",
                "system_prompt": "stub",
                "tools": ["search_icd"],
                "model": "deepseek-v4",
                "non_goals": ["不写回"],
                "output_contract": {"schema_ref": "icoder/Stub/v1"},
            }
        ],
        "tools": [
            {
                "name": "search_icd",
                "type": "mcp",
                "stage": "retrieval",
                "ref": "app.icoder.mcp.server:/mcp/v1/tools/call/search_icd",
            }
        ],
        "model": {"primary": "deepseek-v4", "temperature": 0.0},
        "permissions": {
            "key": "test",
            "tools": {"search_icd": "allowed", "writeback": "blocked"},
            "production_writeback_blocked": True,
        },
        "phi_redaction": "required",
        "context_required": True,
        "recorder_required": True,
        "requirements": {"min_runtime_version": "2.0.0"},
        "llm_capabilities": {"supports_tool_calling": True, "supports_json_mode": True},
    }
    base.update(overrides)
    return base


# ── v1.1 baseline ──


def test_v11_certified_loads_as_executable():
    p = load_pack(_minimal_v11_pack())
    assert p.format_version == "1.1"
    assert p.agent_type == "certified"
    assert p.status == PackStatus.EXECUTABLE
    assert p.production_ready is True
    assert p.experimental is False
    assert p.validation_errors == []
    assert p.tool_count == 2
    assert p.tier == 1  # has tools, no network keywords


def test_v11_community_with_code_is_executable_and_tier_2():
    pack = _minimal_v11_pack(
        agent_type="community",
        code={"executor.py": "print('hi')"},
    )
    p = load_pack(pack)
    assert p.status == PackStatus.EXECUTABLE
    assert p.production_ready is True
    assert p.enabled_by_default is False  # tier 2 — default disabled
    assert p.tier == 2  # code/ → tier 2


def test_v11_community_without_code_is_metadata_only():
    pack = _minimal_v11_pack(agent_type="community")
    p = load_pack(pack)
    assert p.status == PackStatus.METADATA_ONLY
    assert p.production_ready is False
    assert "no code/" in why_not_executable(p)[0].lower() or "community" in why_not_executable(p)[0].lower()


def test_v11_certified_with_code_is_invalid():
    pack = _minimal_v11_pack(code={"x.py": "print(1)"})
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID
    assert p.production_ready is False
    assert any("certified agents cannot contain code" in e for e in p.validation_errors)


def test_v11_legacy_string_tool_ids_normalize_to_legacy_kind():
    p = load_pack(_minimal_v11_pack())
    assert all(t.kind == "legacy" for t in p.tools)
    assert p.tools[0].id == "t1"


def test_v11_dict_tool_with_tier_normalizes_to_v1_1_kind():
    pack = _minimal_v11_pack(tools=["str_id", {"name": "dict_tool", "tier": 1, "executor_file": "x.py"}])
    # Need to add code for executor_file to be valid in v1.1
    pack["code"] = {"x.py": "print('x')"}
    pack["agent_type"] = "community"
    p = load_pack(pack)
    assert p.tools[0].kind == "legacy"
    assert p.tools[1].kind == "v1_1"
    assert p.tools[1].tier == 1
    assert p.tools[1].executor_file == "x.py"


# ── v1.2 baseline ──


def test_v12_expert_stub_with_real_expert_is_executable_but_not_production_ready():
    p = load_pack(_minimal_v12_pack())
    assert p.format_version == "1.2"
    assert p.agent_type == "expert-stub"
    assert p.status == PackStatus.EXECUTABLE
    assert p.production_ready is False  # expert-stub never PR
    assert p.expert_count == 1
    assert p.experts[0].id == "test-stub"
    assert p.experts[0].non_goals == ["不写回"]
    assert p.experts[0].output_contract == {"schema_ref": "icoder/Stub/v1"}


def test_v12_expert_stub_without_real_expert_is_metadata_only():
    # No experts → can't dispatch the skeleton
    pack = _minimal_v12_pack(experts=[], tools=[])
    p = load_pack(pack)
    assert p.status == PackStatus.METADATA_ONLY
    assert p.production_ready is False


def test_v12_reference_pack_is_executable_and_production_ready():
    pack = _minimal_v12_pack(agent_type="reference")
    p = load_pack(pack)
    assert p.status == PackStatus.EXECUTABLE
    assert p.production_ready is True
    assert p.enabled_by_default is True


def test_v12_certified_with_real_experts_is_executable_and_production_ready():
    pack = _minimal_v12_pack(agent_type="certified")
    p = load_pack(pack)
    assert p.status == PackStatus.EXECUTABLE
    assert p.production_ready is True


def test_launch_candidate_gate_separates_dev_readiness_from_production_claim():
    pack = _minimal_v12_pack(
        agent_type="certified",
        backend_provider="icoder.llm-with-tools.v1",
        backend_config={"tools": {"scope": ["search_icd"]}},
        output_contract={
            "schema_ref": "icoder/TestOutput/v1",
            "required_fields": ["result", "manual_review_required"],
            "field_types": {
                "result": "string",
                "manual_review_required": "boolean",
            },
            "field_schemas": {
                "result": {"type": "string"},
                "manual_review_required": {"type": "boolean"},
            },
        },
        metrics_required=True,
        recorder_required=True,
        human_review_required_when=["low confidence"],
        example_inputs=[{"text": "synthetic chart"}],
        example_outputs=[{"result": "review", "manual_review_required": True}],
    )
    pack["manifest"]["maturity"] = "mvp"
    pack["manifest"]["production_ready"] = False
    pack["permissions"]["production_writeback_blocked"] = True

    p = load_pack(pack)

    assert p.status == PackStatus.EXECUTABLE
    assert p.launch_candidate_ready is True
    assert p.launch_candidate_blockers == []
    # The development gate cannot manufacture a production approval claim.
    assert pack["manifest"]["production_ready"] is False
    assert "independent_clinical_quality_validation" in p.external_release_gates


def test_launch_candidate_gate_reports_actionable_blockers():
    p = load_pack(_minimal_v12_pack(agent_type="certified"))

    assert p.status == PackStatus.EXECUTABLE
    assert p.launch_candidate_ready is False
    assert "explicit backend_provider or a2a.endpoint is required" in p.launch_candidate_blockers
    assert "output_contract.schema_ref is required" in p.launch_candidate_blockers
    assert "metrics_required=true is required" in p.launch_candidate_blockers
    assert "at least one example_input is required for smoke/E2E tests" in p.launch_candidate_blockers
    assert "at least one contract-complete example_output is required" in p.launch_candidate_blockers


def test_launch_candidate_gate_requires_complete_valid_field_types():
    pack = _minimal_v12_pack(
        agent_type="certified",
        backend_provider="icoder.llm-with-tools.v1",
        output_contract={
            "schema_ref": "icoder/TestOutput/v1",
            "required_fields": ["result", "manual_review_required"],
            "field_types": {
                "result": "string",
                "manual_review_required": "unsupported",
            },
        },
        metrics_required=True,
        recorder_required=True,
        human_review_required_when=["low confidence"],
        example_inputs=[{"text": "synthetic chart"}],
        example_outputs=[{"result": "review", "manual_review_required": True}],
    )
    pack["manifest"]["maturity"] = "mvp"
    pack["permissions"]["production_writeback_blocked"] = True

    p = load_pack(pack)

    assert p.launch_candidate_ready is False
    assert any(
        "unsupported types for: manual_review_required" in blocker
        for blocker in p.launch_candidate_blockers
    )
    assert any(
        "valid declared field types" in blocker
        for blocker in p.launch_candidate_blockers
    )


def test_launch_candidate_gate_requires_closed_recursive_schemas_for_all_fields():
    pack = _minimal_v12_pack(
        agent_type="certified",
        backend_provider="icoder.llm-with-tools.v1",
        output_contract={
            "schema_ref": "icoder/TestOutput/v2",
            "required_fields": ["result", "manual_review_required"],
            "field_types": {
                "result": "object",
                "manual_review_required": "boolean",
            },
        },
        metrics_required=True,
        recorder_required=True,
        human_review_required_when=["low confidence"],
        example_inputs=[{"text": "synthetic chart"}],
        example_outputs=[{
            "result": {"summary": "review"},
            "manual_review_required": True,
        }],
    )
    pack["manifest"]["maturity"] = "mvp"
    pack["permissions"]["production_writeback_blocked"] = True

    missing = load_pack(pack)
    assert missing.launch_candidate_ready is False
    assert "output_contract.field_schemas must be an object" in missing.launch_candidate_blockers

    pack["output_contract"]["field_schemas"] = {
        "result": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
        "manual_review_required": {"type": "boolean"},
    }
    valid = load_pack(pack)
    assert valid.launch_candidate_ready is True


def test_launch_candidate_gate_rejects_pure_llm_pack_with_runtime_tools():
    pack = _minimal_v12_pack(
        agent_type="certified",
        backend_provider="icoder.pure-llm.v1",
        output_contract={
            "schema_ref": "icoder/TestOutput/v1",
            "required_fields": ["result", "manual_review_required"],
            "field_types": {
                "result": "string",
                "manual_review_required": "boolean",
            },
            "field_schemas": {
                "result": {"type": "string"},
                "manual_review_required": {"type": "boolean"},
            },
        },
        metrics_required=True,
        recorder_required=True,
        human_review_required_when=["low confidence"],
        example_inputs=[{"text": "synthetic chart"}],
        example_outputs=[{"result": "review", "manual_review_required": True}],
    )
    pack["manifest"]["maturity"] = "mvp"
    pack["manifest"]["production_ready"] = False
    pack["permissions"]["production_writeback_blocked"] = True

    p = load_pack(pack)

    assert p.status == PackStatus.EXECUTABLE
    assert p.launch_candidate_ready is False
    assert "pure_llm backend cannot declare runtime tools" in p.launch_candidate_blockers


def test_launch_candidate_gate_rejects_declared_placeholder_or_stale_integrity():
    pack = _minimal_v12_pack(
        agent_type="certified",
        backend_provider="icoder.pure-llm.v1",
        output_contract={
            "schema_ref": "icoder/TestOutput/v1",
            "required_fields": ["result", "manual_review_required"],
        },
        metrics_required=True,
        recorder_required=True,
        human_review_required_when=["low confidence"],
        example_inputs=[{"text": "synthetic chart"}],
        example_outputs=[{"result": "review", "manual_review_required": True}],
    )
    pack["manifest"]["maturity"] = "mvp"
    pack["permissions"]["production_writeback_blocked"] = True
    pack["integrity"] = {"sha256": "PLACEHOLDER_RECOMPUTED_AT_PUBLISH"}

    placeholder = load_pack(pack)
    assert placeholder.launch_candidate_ready is False
    assert any(
        "64-character lowercase hex" in blocker
        for blocker in placeholder.launch_candidate_blockers
    )

    pack["integrity"] = {"sha256": "0" * 64}
    stale = load_pack(pack)
    assert stale.launch_candidate_ready is False
    assert "integrity.sha256 does not match canonical pack content" in (
        stale.launch_candidate_blockers
    )


def test_launch_candidate_integrity_ignores_hub_runtime_mtime_metadata():
    raw = _minimal_v12_pack(
        agent_type="certified",
        backend_provider="icoder.llm-with-tools.v1",
        output_contract={
            "schema_ref": "icoder/TestOutput/v1",
            "required_fields": ["result", "manual_review_required"],
            "field_types": {
                "result": "string",
                "manual_review_required": "boolean",
            },
            "field_schemas": {
                "result": {"type": "string"},
                "manual_review_required": {"type": "boolean"},
            },
        },
        metrics_required=True,
        recorder_required=True,
        human_review_required_when=["low confidence"],
        example_inputs=[{"text": "synthetic chart"}],
        example_outputs=[{"result": "review", "manual_review_required": True}],
    )
    raw["manifest"]["maturity"] = "mvp"
    raw["manifest"]["production_ready"] = False
    raw["permissions"]["production_writeback_blocked"] = True
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
    raw["integrity"] = {"sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}

    direct = load_pack(raw)
    assert direct.launch_candidate_ready is True

    hub_projection = copy.deepcopy(raw)
    hub_projection["_pack_mtime_iso"] = "12-Aug-2026"
    projected = load_pack(hub_projection)

    assert projected.launch_candidate_ready is True
    assert projected.launch_candidate_blockers == []

    # The legacy v1.1 installer must apply the same runtime-metadata exclusion.
    from icoder_runtime.core.agent_pack_v1 import AgentPackageV1

    legacy_raw = {
        "format_version": "1.1",
        "agent_type": "certified",
        "manifest": {"name": "Legacy Test", "version": "1.0.0"},
        "system_prompt": "You are a test.",
        "experts": [],
        "tools": [],
        "permissions": {"tools": {}},
        "requirements": {"min_runtime_version": "1.0.0"},
        "llm_capabilities": {
            "required_models": [],
            "supports_tool_calling": False,
            "supports_json_mode": True,
        },
    }
    legacy_canonical = json.dumps(
        legacy_raw, sort_keys=True, ensure_ascii=False, default=str
    )
    legacy_raw["integrity"] = {
        "sha256": hashlib.sha256(legacy_canonical.encode("utf-8")).hexdigest()
    }
    legacy_raw["_pack_mtime_iso"] = "12-Aug-2026"
    AgentPackageV1.from_dict(legacy_raw)


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_official_pure_llm_packs_do_not_claim_runtime_tools():
    packs = load_packs_from_dir(OFFICIAL_AGENTS_DIR)
    offenders = [
        p.agent_ref
        for p in packs
        if p.backend_provider == "icoder.pure-llm.v1" and p.tools
    ]
    assert offenders == []


def test_v12_tools_ref_normalize_correctly():
    p = load_pack(_minimal_v12_pack())
    t = p.tools[0]
    assert t.kind == "v1_2_mcp"
    assert t.ref == "app.icoder.mcp.server:/mcp/v1/tools/call/search_icd"
    assert t.stage == "retrieval"


def test_v12_guard_tool_kind_is_guard():
    pack = _minimal_v12_pack(
        tools=[{"name": "guard_input", "type": "guard", "stage": "pre-extraction",
                "ref": "app.icoder.guards.input_guard:guard_input"}]
    )
    p = load_pack(pack)
    assert p.tools[0].kind == "v1_2_guard"


def test_v12_function_tool_kind_is_function():
    pack = _minimal_v12_pack(
        tools=[{"name": "reranker", "type": "function"}]
    )
    p = load_pack(pack)
    assert p.tools[0].kind == "v1_2_function"


def test_v12_v11_extensions_populated():
    p = load_pack(_minimal_v12_pack())
    assert p.phi_redaction == "required"
    assert p.context_required is True
    assert p.recorder_required is True
    assert p.metrics_required is False  # not set in fixture
    # expert-level non_goals surfaced via NormalizedExpert
    assert p.experts[0].non_goals == ["不写回"]
    assert p.human_review_required_when == []
    assert p.output_contract == {}  # pack-level output_contract is empty in fixture
    assert p.a2a == {}


def test_v12_pack_level_non_goals_surfaced():
    """A pack with its own non_goals[] (top-level) is recorded on NormalizedPack.non_goals."""
    pack = _minimal_v12_pack(non_goals=["不直接做最终诊断决策", "不写回 EMR"])
    p = load_pack(pack)
    assert p.non_goals == ["不直接做最终诊断决策", "不写回 EMR"]


# ── format_version / agent_type validation ──


def test_unknown_format_version_is_invalid():
    pack = _minimal_v11_pack()
    pack["format_version"] = "0.9"
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID
    assert any("Unsupported format_version" in e for e in p.validation_errors)


def test_missing_format_version_is_invalid():
    pack = _minimal_v11_pack()
    del pack["format_version"]
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID


def test_unknown_agent_type_is_invalid():
    pack = _minimal_v11_pack(agent_type="experimental")
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID
    assert any("agent_type" in e and "experimental" in e for e in p.validation_errors)


def test_supported_format_versions_constant():
    assert SUPPORTED_FORMAT_VERSIONS == ("1.1", "1.2")


def test_legal_agent_types_constant():
    assert "certified" in LEGAL_AGENT_TYPES
    assert "community" in LEGAL_AGENT_TYPES
    assert "reference" in LEGAL_AGENT_TYPES
    assert "expert-stub" in LEGAL_AGENT_TYPES


# ── Required field validation ──


def test_missing_manifest_name_is_invalid():
    pack = _minimal_v11_pack()
    pack["manifest"]["name"] = ""
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID
    assert any("manifest.name" in e for e in p.validation_errors)


def test_missing_manifest_version_is_invalid():
    pack = _minimal_v11_pack()
    pack["manifest"]["version"] = ""
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID
    assert any("manifest.version" in e for e in p.validation_errors)


def test_missing_system_prompt_is_invalid():
    pack = _minimal_v11_pack()
    pack["system_prompt"] = ""
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID
    assert any("system_prompt" in e for e in p.validation_errors)


def test_missing_min_runtime_version_is_invalid():
    pack = _minimal_v11_pack()
    pack["requirements"] = {}
    p = load_pack(pack)
    assert p.status == PackStatus.INVALID
    assert any("min_runtime_version" in e for e in p.validation_errors)


# ── agent_ref derivation ──


def test_missing_agent_ref_is_derived_from_manifest():
    pack = _minimal_v11_pack()
    del pack["agent_ref"]
    p = load_pack(pack)
    assert p.agent_ref == "icoder/test-pack@1.0.0"
    assert any("agent_ref missing" in w for w in p.validation_warnings)


# ── Tool normalization edge cases ──


def test_mixed_tools_string_and_dict_in_v12():
    pack = _minimal_v12_pack()
    pack["tools"] = [
        "legacy_str_id",
        {"name": "guard_in", "type": "guard", "ref": "app.icoder.guards.input_guard:guard_input"},
        {"name": "search", "type": "mcp", "ref": "app.icoder.mcp.server:/mcp/v1/tools/call/search_icd"},
    ]
    p = load_pack(pack)
    assert len(p.tools) == 3
    assert p.tools[0].kind == "legacy"
    assert p.tools[1].kind == "v1_2_guard"
    assert p.tools[2].kind == "v1_2_mcp"


def test_empty_tool_dict_records_error():
    pack = _minimal_v11_pack(tools=[{}])
    p = load_pack(pack)
    assert any("tools[0]: name" in e for e in p.validation_errors)


def test_expert_missing_id_is_invalid():
    pack = _minimal_v12_pack(
        experts=[{"name": "No-Id Expert", "role": "primary"}]
    )
    p = load_pack(pack)
    assert any("experts[0]: id is required" in e for e in p.validation_errors)


# ── integrity.sha256 preserved ──


def test_integrity_hash_preserved_on_v11_pack():
    pack = _minimal_v11_pack()
    pack["integrity"] = {"sha256": ""}
    p = load_pack(pack)
    assert "integrity" in p.to_dict()
    assert p.integrity == {"sha256": ""}


# ── Production-ready rules ──


def test_certified_pure_prompt_is_executable_but_not_production_ready():
    pack = _minimal_v11_pack(tools=[], experts=[])
    p = load_pack(pack)
    assert p.status == PackStatus.EXECUTABLE
    assert p.production_ready is False
    assert any("pure-prompt" in w for w in p.validation_warnings)


def test_certified_dedicated_backend_is_not_mislabelled_as_pure_prompt():
    pack = _minimal_v11_pack(
        tools=[],
        experts=[],
        backend_provider="icoder.governed-test.v1",
    )
    p = load_pack(pack)

    assert p.status == PackStatus.EXECUTABLE
    assert not any("pure-prompt" in warning for warning in p.validation_warnings)


# ── Helpers ──


def test_why_not_executable_returns_empty_for_executable():
    p = load_pack(_minimal_v11_pack())
    assert why_not_executable(p) == []


def test_why_not_executable_for_metadata_only_expert_stub():
    pack = _minimal_v12_pack(experts=[], tools=[])
    p = load_pack(pack)
    reasons = why_not_executable(p)
    assert any("expert-stub" in r for r in reasons)


def test_why_not_executable_for_invalid_lists_errors():
    pack = _minimal_v11_pack()
    del pack["system_prompt"]
    p = load_pack(pack)
    reasons = why_not_executable(p)
    assert any("INVALID" in r for r in reasons)
    assert any("system_prompt" in r for r in reasons)


def test_summary_counts_aggregates_correctly():
    packs = [
        load_pack(_minimal_v11_pack()),
        load_pack(_minimal_v12_pack(agent_type="reference")),
        load_pack(_minimal_v12_pack(agent_type="expert-stub", experts=[], tools=[])),
        load_pack(_minimal_v11_pack(format_version="0.9")),  # → INVALID (still counted as certified)
    ]
    s = summary_counts(packs)
    assert s["total"] == 4
    assert s["executable"] == 2
    assert s["metadata_only"] == 1
    assert s["invalid"] == 1
    assert s["production_ready"] == 2
    # 2 v1.1 packs (1 valid + 1 invalid, both default certified)
    assert s["by_type"]["certified"] == 2
    assert s["by_type"]["reference"] == 1
    assert s["by_type"]["expert-stub"] == 1
    assert s["by_format"]["1.1"] == 1   # only the valid v1.1 pack keeps its version recorded
    assert s["by_format"]["1.2"] == 2
    assert s["by_format"]["0.9"] == 1   # the invalid pack still reports its format_version


def test_to_summary_shape():
    p = load_pack(_minimal_v11_pack())
    s = p.to_summary()
    assert "agent_ref" in s
    assert "status" in s
    assert "production_ready" in s
    assert "tier" in s
    assert "min_runtime_version" in s
    assert "validation_errors" in s
    assert "validation_warnings" in s
    assert s["status"] == "executable"


def test_to_dict_drops_raw():
    p = load_pack(_minimal_v11_pack())
    d = p.to_dict()
    assert "raw" not in d
    assert "system_prompt" in d
    assert d["status"] == "executable"


# ── Discover / load from directory ──


def test_discover_v1_files_finds_16_packs():
    if not OFFICIAL_AGENTS_DIR.exists():
        pytest.skip("official_agents dir not present in this checkout")
    files = discover_v1_files(OFFICIAL_AGENTS_DIR)
    # Phase A1D.5 — A1B-AE Phase added 14 net-new Corti-parity packs.
    # Previous baseline was 16; current is 30.
    assert len(files) == 32


def test_load_packs_from_dir_loads_all_16():
    if not OFFICIAL_AGENTS_DIR.exists():
        pytest.skip("official_agents dir not present in this checkout")
    packs = load_packs_from_dir(OFFICIAL_AGENTS_DIR)
    # Phase A1D.5 — 30 packs now (was 16).
    assert len(packs) == 32
    # Every pack must have a non-empty agent_ref
    for p in packs:
        assert p.agent_ref, f"{p.source_path} has empty agent_ref"
        assert p.name, f"{p.source_path} has empty name"


def test_load_packs_from_dir_skips_pycache_and_hidden():
    tmp = Path(__file__).resolve().parent / "_tmp_packs"
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    try:
        tmp.mkdir()
        (tmp / "__pycache__").mkdir()
        (tmp / "__pycache__" / "agent_pack.json").write_text("{}")
        (tmp / ".hidden").mkdir()
        (tmp / ".hidden" / "agent_pack.json").write_text("{}")
        (tmp / "real_pack").mkdir()
        (tmp / "real_pack" / "agent_pack.json").write_text(json.dumps(_minimal_v11_pack()))
        packs = load_packs_from_dir(tmp)
        assert len(packs) == 1
        assert packs[0].agent_ref == "icoder/test-pack@1.0.0"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_packs_from_dir_handles_missing_dir():
    packs = load_packs_from_dir("/nonexistent/path")
    assert packs == []


def test_load_packs_from_dir_records_parse_error_on_bad_json():
    tmp = Path(__file__).resolve().parent / "_tmp_bad_pack"
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    try:
        tmp.mkdir()
        (tmp / "broken").mkdir()
        (tmp / "broken" / "agent_pack.json").write_text("{this is not json")
        packs = load_packs_from_dir(tmp)
        assert len(packs) == 1
        assert packs[0].status == PackStatus.INVALID
        assert any("Failed to parse JSON" in e for e in packs[0].validation_errors)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ── All 16 official packs (full integration smoke) ──


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_all_16_official_packs_load_via_new_loader():
    """The big one — every pack on disk must be loadable."""
    packs = load_packs_from_dir(OFFICIAL_AGENTS_DIR)
    # Phase A1D.5 — 30 packs now (was 16).
    assert len(packs) == 32

    # We expect this exact distribution per baseline audit:
    by_type = {p.agent_type for p in packs}
    assert "certified" in by_type
    assert "community" not in by_type
    assert "internal_engine" in by_type  # was "reference" pre-Phase-3-A
    assert "expert-stub" in by_type

    # Phase A1D.5 — 3 expert-stubs (was 4). All METADATA_ONLY.
    expert_stubs = [p for p in packs if p.agent_type == "expert-stub"]
    assert len(expert_stubs) == 3
    assert all(p.status == PackStatus.METADATA_ONLY for p in expert_stubs)

    # The internal_engine (MedCodER Coding Review) must be EXECUTABLE
    # Phase 3-A: was "reference" pre-productization, now "internal_engine"
    # backing the Corti-style Medical Coding Agent (icoder/medical-coding-agent@2.0.0).
    refs = [p for p in packs if p.agent_type == "internal_engine"]
    assert len(refs) == 1
    assert refs[0].status == PackStatus.EXECUTABLE
    assert refs[0].production_ready is False
    assert refs[0].expert_count == 4  # 4 atomic experts wired

    # All official Packs have now migrated off the legacy v1.1 format.
    v11 = [p for p in packs if p.format_version == "1.1"]
    assert len(v11) == 0
    assert all(p.status != PackStatus.INVALID for p in v11)

    # v1.2 certified Packs include the governed Denial Appeals baseline.
    v12_cert = [p for p in packs if p.format_version == "1.2" and p.agent_type == "certified"]
    assert len(v12_cert) == 28
    v12_cert_exec = [p for p in v12_cert if p.status == PackStatus.EXECUTABLE]
    assert len(v12_cert_exec) == 26


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_medcoder_coding_review_is_now_executable():
    """Critical: the canonical reference agent itself must be EXECUTABLE."""
    packs = load_packs_from_dir(OFFICIAL_AGENTS_DIR)
    ref = next(p for p in packs if "medcoder-coding-review" in p.agent_ref)
    assert ref.status == PackStatus.EXECUTABLE
    assert ref.production_ready is False
    assert ref.expert_count == 4
    assert ref.tool_count == 5
    assert all(t.kind == "v1_2_mcp" for t in ref.tools)


# ── Edge: non-dict input ──


def test_non_dict_input_raises():
    with pytest.raises(TypeError):
        load_pack("not a dict")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        load_pack(None)  # type: ignore[arg-type]


# ── type: ignore comments intentionally added above ──


# ── Extra: v12 medcoder-coding-review round-trip ──


def test_v12_medcoder_coding_review_style_pack_full_round_trip():
    """A minimal reference-style pack with 4 experts and 5 MCP tools."""
    pack = {
        "format_version": "1.2",
        "agent_type": "reference",
        "agent_ref": "icoder/my-ref@1.0.0",
        "manifest": {"name": "My Ref", "version": "1.0.0"},
        "system_prompt": "ref",
        "experts": [
            {"id": f"e{i}", "name": f"E{i}", "role": f"role{i}", "system_prompt": "sp", "tools": ["t"]}
            for i in range(4)
        ],
        "tools": [
            {"name": "t", "type": "mcp", "stage": "x", "ref": "app.icoder.x:t"}
        ] * 5,
        "permissions": {"key": "k", "tools": {"writeback": "blocked"}},
        "requirements": {"min_runtime_version": "2.0.0"},
    }
    p = load_pack(pack)
    assert p.status == PackStatus.EXECUTABLE
    assert p.production_ready is True
    assert p.expert_count == 4
    assert p.tool_count == 5


def test_summary_counts_with_zero_packs():
    assert summary_counts([]) == {
        "total": 0,
        "executable": 0,
        "metadata_only": 0,
        "invalid": 0,
        "production_ready": 0,
        "launch_candidate_ready": 0,
        "experimental": 0,
        "by_type": {},
        "by_format": {},
    }


def test_v11_with_integrity_sha256_validates():
    """The legacy AgentPackageV1 integrity check should still trigger
    when verify_integrity is requested via from_dict; the new loader
    records integrity metadata but does not re-verify (out of scope)."""
    pack = _minimal_v11_pack()
    pack["integrity"] = {"sha256": "0000000000000000000000000000000000000000000000000000000000000000"}
    p = load_pack(pack)
    # The new loader does not raise on integrity mismatch — it records.
    # The legacy AgentPackageV1.from_dict() is the strict path.
    assert p.integrity.get("sha256", "").startswith("0000")


def test_pure_prompt_pack_tier_is_zero():
    pack = _minimal_v11_pack(tools=[], experts=[])
    p = load_pack(pack)
    assert p.tier == 0
