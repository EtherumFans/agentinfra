"""Phase 4-F (2026-07-09) — v1.3 spec schema + loader tests.

Covers the 5 new NormalizedPack fields added for the Corti-like
Prebuilt Agent System:
  - default_runtime_mode
  - available_runtime_modes
  - example_inputs
  - example_outputs
  - built_by

Verifies:
  1. Fields populate from top-level pack JSON
  2. Fields populate from agent-nested placement
  3. Legacy packs without the fields load fine (backward compat)
  4. to_summary() includes the new fields
  5. Type mismatches produce validation_warnings (not errors)
"""
from __future__ import annotations

from icoder_runtime.core.agent_pack_loader import load_pack
from icoder_runtime.core.agent_pack_schema import NormalizedPack


# ── Test fixtures ───────────────────────────────────────────────────────


_V13_TOP_LEVEL_PACK = {
    "agent_ref": "icoder/medical-coding-agent@2.0.0",
    "format_version": "1.2",
    "agent_type": "certified",
    "manifest": {
        "name": "Medical Coding Agent",
        "version": "2.0.0",
        "description": "Predict ICD-10-CN codes.",
        "category": "Coding",
    },
    "system_prompt": "You are a medical coding assistant.",
    "experts": [
        {"id": "coding-expert", "name": "Coding Expert"},
    ],
    "requirements": {"min_runtime_version": "1.0"},
    "default_runtime_mode": "corti_like_fast",
    "available_runtime_modes": ["corti_like_fast", "medcoder_deep"],
    "example_inputs": [
        {"title": "T12 fracture", "input_text": "MRI: T12 compression fracture."},
    ],
    "example_outputs": [
        {"primary_diagnosis": "S22.0"},
    ],
    "built_by": "icoder",
}


_V13_NESTED_PACK = {
    "agent_ref": "icoder/principal-diagnosis-review@1.0.0",
    "format_version": "1.2",
    "agent_type": "certified",
    "manifest": {
        "name": "Principal Diagnosis Review Agent",
        "version": "1.0.0",
        "description": "Review principal diagnosis choice.",
        "category": "Review",
    },
    "system_prompt": "You are a principal diagnosis reviewer.",
    "experts": [
        {"id": "pdx-expert", "name": "Principal Dx Expert"},
    ],
    "requirements": {"min_runtime_version": "1.0"},
    "agent": {
        "default_runtime_mode": "a2a_pure_llm",
        "available_runtime_modes": ["a2a_pure_llm"],
        "example_inputs": [
            {"title": "Multi-dx discharge", "input_text": "Patient with multiple dx..."},
        ],
        "built_by": "icoder",
    },
}


_LEGACY_V12_PACK_NO_V13_FIELDS = {
    "agent_ref": "icoder/legacy-pack@1.0.0",
    "format_version": "1.2",
    "agent_type": "certified",
    "manifest": {
        "name": "Legacy Pack",
        "version": "1.0.0",
        "description": "Pre-Phase-4-F pack without v1.3 fields.",
        "category": "general",
    },
    "system_prompt": "You are a legacy assistant.",
    "experts": [
        {"id": "legacy-expert", "name": "Legacy Expert"},
    ],
    "requirements": {"min_runtime_version": "1.0"},
}


_V13_TYPE_MISMATCH_PACK = {
    "agent_ref": "icoder/bad-pack@1.0.0",
    "format_version": "1.2",
    "agent_type": "certified",
    "manifest": {
        "name": "Bad Pack",
        "version": "1.0.0",
        "description": "Type mismatches in v1.3 fields.",
        "category": "general",
    },
    "system_prompt": "You are an assistant.",
    "experts": [
        {"id": "expert", "name": "Expert"},
    ],
    "requirements": {"min_runtime_version": "1.0"},
    "default_runtime_mode": 123,        # int, not str
    "available_runtime_modes": "corti_like_fast",  # str, not list
    "example_inputs": "not a list",
    "built_by": False,
}


# ── Tests ───────────────────────────────────────────────────────────────


def test_v13_top_level_fields_populate() -> None:
    """default_runtime_mode etc. populate from top-level pack JSON."""
    p = load_pack(_V13_TOP_LEVEL_PACK)
    assert isinstance(p, NormalizedPack)
    assert p.default_runtime_mode == "corti_like_fast"
    assert p.available_runtime_modes == ["corti_like_fast", "medcoder_deep"]
    assert len(p.example_inputs) == 1
    assert p.example_inputs[0]["title"] == "T12 fracture"
    assert len(p.example_outputs) == 1
    assert p.built_by == "icoder"


def test_v13_nested_fields_populate() -> None:
    """v1.3 fields under `agent: {...}` also populate (alternative placement)."""
    p = load_pack(_V13_NESTED_PACK)
    assert p.default_runtime_mode == "a2a_pure_llm"
    assert p.available_runtime_modes == ["a2a_pure_llm"]
    assert len(p.example_inputs) == 1
    assert p.example_inputs[0]["title"] == "Multi-dx discharge"
    assert p.built_by == "icoder"


def test_v13_top_level_takes_precedence_over_nested() -> None:
    """When both top-level and nested exist, top-level wins (per _populate_v13_extensions rule)."""
    pack = dict(_V13_TOP_LEVEL_PACK)
    pack["agent"] = {
        "default_runtime_mode": "should_be_ignored",
        "built_by": "should_be_ignored",
    }
    p = load_pack(pack)
    assert p.default_runtime_mode == "corti_like_fast"
    assert p.built_by == "icoder"


def test_legacy_pack_without_v13_fields_loads_clean() -> None:
    """Legacy v1.2 packs without v1.3 fields load with empty defaults."""
    p = load_pack(_LEGACY_V12_PACK_NO_V13_FIELDS)
    assert p.default_runtime_mode == ""
    assert p.available_runtime_modes == []
    assert p.example_inputs == []
    assert p.example_outputs == []
    assert p.built_by == ""
    # No validation errors — backward compat preserved.
    assert p.validation_errors == []


def test_to_summary_includes_v13_fields() -> None:
    """to_summary() surfaces the 5 new fields for Hub card / Agent Detail UI."""
    p = load_pack(_V13_TOP_LEVEL_PACK)
    s = p.to_summary()
    assert s["default_runtime_mode"] == "corti_like_fast"
    assert s["available_runtime_modes"] == ["corti_like_fast", "medcoder_deep"]
    assert len(s["example_inputs"]) == 1
    assert len(s["example_outputs"]) == 1
    assert s["built_by"] == "icoder"


def test_v13_type_mismatches_produce_warnings_not_errors() -> None:
    """Bad types in v1.3 fields produce validation_warnings (not errors)."""
    p = load_pack(_V13_TYPE_MISMATCH_PACK)
    # The pack itself should still load (no validation_errors from v1.3 fields).
    # But each mismatched field should add a warning.
    warnings_text = " ".join(p.validation_warnings)
    assert "default_runtime_mode" in warnings_text
    assert "available_runtime_modes" in warnings_text
    assert "example_inputs" in warnings_text
    assert "built_by" in warnings_text
    # Defaulted to empty values.
    assert p.default_runtime_mode == ""
    assert p.available_runtime_modes == []
    assert p.example_inputs == []
    assert p.built_by == ""
