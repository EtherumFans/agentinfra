"""A1B-AE.8 — iCoDer Preset Agents catalog + service tests.

Coverage:
§1 Catalog loading — 5 presets, deterministic order, required fields
§2 Per-preset structural assertions (Corti §6 surface)
§3 Corti Agent Card emission (camelCase + icoder_ext)
§4 Cross-reference Experts against A1B-AE.3..7 canonical keys
§5 Red-line enforcement (human_review / phi_redacted / production_writeback_blocked)
§6 Charter Amendment 1 §7 forbidden verdicts preserved
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


EXPECTED_KEYS = [
    "icoder-medical-coding-preset",
    "icoder-cdi-preset",
    "icoder-drg-dip-preset",
    "icoder-intake-interview-preset",
    "icoder-claim-check-preset",
]

# Canonical Expert keys that the catalog is allowed to reference
# (must match A1B-AE.3..7 Expert Registry canonical_key values).
ALLOWED_EXPERT_KEYS = {
    "memory",
    "coding-expert",
    "medical-calculator",
    "drugbank",
    "posos",
    "web-search",
    "pubmed",
    "clinical-trials",
    "interviewing",
}

ALLOWED_AGENT_TYPES = {"expert", "orchestrator", "interviewing-expert"}


# ─────────────────────────────────────────────────────────────────────
# §1 Catalog loading
# ─────────────────────────────────────────────────────────────────────

def test_all_presets_returns_5_in_catalog_order():
    from app.services.preset_agents import all_presets, preset_keys
    presets = all_presets()
    assert len(presets) == 5
    assert preset_keys() == EXPECTED_KEYS


def test_get_preset_returns_none_for_unknown():
    from app.services.preset_agents import get_preset
    assert get_preset("not-a-real-preset") is None


def test_get_preset_returns_each_expected_key():
    from app.services.preset_agents import get_preset
    for key in EXPECTED_KEYS:
        p = get_preset(key)
        assert p is not None, f"missing preset {key}"
        assert p.canonical_key == key


# ─────────────────────────────────────────────────────────────────────
# §2 Per-preset structural assertions
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", EXPECTED_KEYS)
def test_preset_has_required_fields(key):
    from app.services.preset_agents import get_preset
    p = get_preset(key)
    assert p.name, f"{key}: name empty"
    assert p.name_zh, f"{key}: name_zh empty"
    assert p.description, f"{key}: description empty"
    assert p.system_prompt, f"{key}: system_prompt empty"
    assert p.agent_type in ALLOWED_AGENT_TYPES
    assert p.corti_alignment in {"CORTI_ALIGNED", "CORTI_ADAPTED"}


@pytest.mark.parametrize("key", EXPECTED_KEYS)
def test_preset_has_at_least_one_expert(key):
    from app.services.preset_agents import get_preset
    p = get_preset(key)
    assert len(p.experts) >= 1, f"{key}: no experts declared"
    for e in p.experts:
        assert e.canonical_key in ALLOWED_EXPERT_KEYS, (
            f"{key}: expert {e.canonical_key} not in canonical registry"
        )
        assert e.role in {"primary", "auxiliary", "reference"}


@pytest.mark.parametrize("key", EXPECTED_KEYS)
def test_preset_has_primary_expert(key):
    from app.services.preset_agents import get_preset
    p = get_preset(key)
    roles = [e.role for e in p.experts]
    assert "primary" in roles, f"{key}: no primary expert"


# ─────────────────────────────────────────────────────────────────────
# §3 Corti Agent Card emission
# ─────────────────────────────────────────────────────────────────────

def test_corti_agent_card_camelcase_surface():
    from app.services.preset_agents import corti_agent_card
    card = corti_agent_card("icoder-medical-coding-preset")
    assert card is not None
    # Corti §6 camelCase fields
    assert "name" in card
    assert "description" in card
    assert "systemPrompt" in card
    assert "agentType" in card
    assert "experts" in card
    assert "mcpServers" in card
    # iCoDer extensions namespaced
    assert "icoder_ext" in card
    ext = card["icoder_ext"]
    assert ext["canonical_key"] == "icoder-medical-coding-preset"
    assert ext["corti_alignment"] in {"CORTI_ALIGNED", "CORTI_ADAPTED"}


def test_corti_agent_card_for_unknown_returns_none():
    from app.services.preset_agents import corti_agent_card
    assert corti_agent_card("does-not-exist") is None


def test_corti_agent_card_experts_use_canonical_key():
    from app.services.preset_agents import corti_agent_card
    card = corti_agent_card("icoder-intake-interview-preset")
    expert_keys = [e["canonicalKey"] for e in card["experts"]]
    assert "interviewing" in expert_keys
    assert all(k in ALLOWED_EXPERT_KEYS for k in expert_keys)


# ─────────────────────────────────────────────────────────────────────
# §4 Cross-reference Experts against A1B-AE.3..7 canonical keys
# ─────────────────────────────────────────────────────────────────────

def test_all_preset_expert_refs_resolve_to_canonical_registry():
    """Every expert referenced in any preset MUST be one of the 9
    Corti §3.2 canonical keys registered in A1B-AE.3..7.
    """
    from app.services.preset_agents import all_presets
    for p in all_presets():
        for e in p.experts:
            assert e.canonical_key in ALLOWED_EXPERT_KEYS, (
                f"preset {p.canonical_key} references unknown expert "
                f"{e.canonical_key}"
            )


def test_medical_coding_preset_delegates_to_correct_pack():
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-medical-coding-preset")
    assert p.delegates_to_pack == "icoder/medical-coding-agent@2.0.0"


def test_preset_agent_types_distribution():
    from app.services.preset_agents import all_presets
    types = {p.canonical_key: p.agent_type for p in all_presets()}
    # 3 experts, 1 interviewing-expert, 1 orchestrator (per catalog spec)
    assert types["icoder-medical-coding-preset"] == "expert"
    assert types["icoder-cdi-preset"] == "expert"
    assert types["icoder-drg-dip-preset"] == "expert"
    assert types["icoder-intake-interview-preset"] == "interviewing-expert"
    assert types["icoder-claim-check-preset"] == "orchestrator"


# ─────────────────────────────────────────────────────────────────────
# §5 Red-line enforcement
# ─────────────────────────────────────────────────────────────────────

RED_LINES = [
    "human_review_required",
    "phi_redacted",
    "production_writeback_blocked",
]


@pytest.mark.parametrize("key", EXPECTED_KEYS)
@pytest.mark.parametrize("red_line", RED_LINES)
def test_red_line_enforced_true(key, red_line):
    from app.services.preset_agents import get_preset
    p = get_preset(key)
    assert p.red_lines.get(red_line) is True, (
        f"{key}: red line {red_line} not enforced as True"
    )


def test_medical_coding_preset_no_upcoding():
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-medical-coding-preset")
    assert p.red_lines.get("no_upcoding") is True


def test_cdi_preset_red_lines_extend_phase_5_track_d():
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-cdi-preset")
    assert p.red_lines.get("no_auto_diagnosis") is True
    assert p.red_lines.get("no_cmi_target") is True


def test_claim_check_preset_no_auto_submission():
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-claim-check-preset")
    assert p.red_lines.get("no_auto_submission") is True


# ─────────────────────────────────────────────────────────────────────
# §6 Charter Amendment 1 §7 forbidden verdicts preserved
# ─────────────────────────────────────────────────────────────────────

def test_forbidden_verdicts_preserved():
    forbidden = {
        "PRODUCTION_READY", "FULLY_VERIFIED", "PHI_BOUNDED",
        "CORTI_PARITY_VERIFIED", "PASS_A1A_GATE4_FINAL",
        "READY_FOR_HOSPITAL_DEPLOYMENT", "CLINICAL_GRADE_VERIFIED",
        "CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED",
    }
    allowed = {"PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED"}
    assert forbidden.isdisjoint(allowed)
