"""E1 (2026-06-26) — spec alignment lockdown for medcoder-coding-review Agent Pack.

Per Agent Card SPEC §3.3 + Q7 decision: each Expert entry in
``experts[]`` must carry the 5件套:

  - id
  - system_prompt
  - tools
  - model
  - non_goals
  - output_contract  (NOTE: SPEC §3.3 Q7 lists 5 items but output_contract
    is the 6th lockdown field — see D3 spec lockdown notes; either
    way it must be present.)

Plus E1 lockdown: the canonical MedCodER Agent path dispatches 4 atomic
expert packs (evidence_extractor / index_navigator / code_reconciler /
tabular_validator) — NOT a single ``coding-expert`` glue.

These tests read the on-disk ``agent_pack.json`` directly so that a
silent rewrite (removing a field, dropping an expert, swapping IDs)
fails loudly at unit-test time.

Why an on-disk lockdown (not just registry-level):
  - The Agent Pack is published to ISVs / Marketplace (Phase 4).
  - Format drift breaks third-party tooling that consumes the JSON.
  - D3 already locked the format to 1.2 with the 5件套; E1 adds the
    4-expert lockdown on top.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# Path: backend/tests/unit/icoder/agent_pack/test_e1_alignment.py
#   → backend/official_agents/medcoder-coding-review/agent_pack.json
# 4 levels up (tests/unit/icoder/agent_pack → backend).
_AGENT_PACK_PATH = (
    Path(__file__).resolve().parents[4]
    / "official_agents"
    / "medcoder-coding-review"
    / "agent_pack.json"
)


@pytest.fixture(scope="module")
def agent_pack() -> dict:
    """Load the published Agent Pack JSON once per module."""
    assert _AGENT_PACK_PATH.exists(), f"Agent Pack not found at {_AGENT_PACK_PATH}"
    return json.loads(_AGENT_PACK_PATH.read_text(encoding="utf-8"))


# ── Top-level E1 lockdown ──


class TestAgentPackStructure:
    """Lockdown the top-level Agent Pack shape (D3 + E1)."""

    def test_format_version_is_1_2(self, agent_pack: dict) -> None:
        """D3 locked format_version to 1.2; E1 inherits the same."""
        assert agent_pack["format_version"] == "1.2"

    def test_agent_ref_is_medcoder_coding_review(self, agent_pack: dict) -> None:
        """The published agent_ref must remain the canonical MedCodER ref."""
        assert agent_pack["agent_ref"] == "icoder/medcoder-coding-review-agent@1.0.0"

    def test_experts_array_has_exactly_4_entries(self, agent_pack: dict) -> None:
        """E1: the canonical MedCodER Agent now dispatches 4 atomic expert
        packs (one per MedCodER stage), NOT a single ``coding-expert``
        glue wrapper. This is the core E1 lockdown."""
        assert "experts" in agent_pack, "experts[] missing — E1 requires 4 experts"
        assert len(agent_pack["experts"]) == 4, (
            f"E1 expects exactly 4 expert packs, got {len(agent_pack['experts'])}: "
            f"{[e.get('id') for e in agent_pack['experts']]}"
        )

    def test_expert_ids_are_canonical_4(self, agent_pack: dict) -> None:
        """E1: the 4 expert IDs must be the canonical D2 EXPERT_ID
        strings — lockdown against silent renames (which would break
        the wiring dispatch in ``build_expert_invoker_for_medcoder``)."""
        ids = {e["id"] for e in agent_pack["experts"]}
        expected = {
            "evidence-extractor",
            "index-navigator",
            "code-reconciler",
            "tabular-validator",
        }
        assert ids == expected, f"E1 expert IDs drift: {ids} != {expected}"

    def test_no_coding_expert_glue_entry(self, agent_pack: dict) -> None:
        """E1 explicitly removes the M1 ``coding-expert`` glue wrapper
        from the canonical Agent Pack. It survives only as opt-in
        back-compat (see ``hybrid_fallback`` wiring argument)."""
        ids = {e["id"] for e in agent_pack["experts"]}
        assert "coding-expert" not in ids, (
            "E1 removes 'coding-expert' from experts[] — it's a back-compat "
            "wrapper reachable via hybrid_fallback, not a published expert."
        )


# ── Per-expert Q7 5件套 lockdown ──


# The 5件套 required by Agent Card SPEC §3.3 / Q7 decision.
# output_contract is the 6th (D3-inherited) lockdown field.
_Q7_FIVE_PIECE = ("id", "system_prompt", "tools", "model", "non_goals")
_Q7_REQUIRED_FIELDS = (*_Q7_FIVE_PIECE, "output_contract")


class TestQ7FivePieceContract:
    """Per-expert Q7 5件套 (id/system_prompt/tools/model/non_goals) +
    D3-inherited output_contract lockdown."""

    @pytest.mark.parametrize("expert_index", [0, 1, 2, 3])
    def test_expert_has_all_required_fields(
        self, agent_pack: dict, expert_index: int,
    ) -> None:
        expert = agent_pack["experts"][expert_index]
        eid = expert.get("id", f"<index {expert_index}>")
        for field in _Q7_REQUIRED_FIELDS:
            assert field in expert, (
                f"expert {eid!r} is missing Q7 5件套 field {field!r} "
                f"(SPEC §3.3 / Q7 / D3)"
            )

    @pytest.mark.parametrize("expert_index", [0, 1, 2, 3])
    def test_expert_id_is_non_empty_string(
        self, agent_pack: dict, expert_index: int,
    ) -> None:
        expert = agent_pack["experts"][expert_index]
        assert isinstance(expert["id"], str) and expert["id"], (
            f"expert[{expert_index}].id must be a non-empty string"
        )

    @pytest.mark.parametrize("expert_index", [0, 1, 2, 3])
    def test_expert_system_prompt_is_non_empty_string(
        self, agent_pack: dict, expert_index: int,
    ) -> None:
        expert = agent_pack["experts"][expert_index]
        prompt = expert["system_prompt"]
        assert isinstance(prompt, str) and prompt.strip(), (
            f"expert {expert['id']!r} system_prompt must be a non-empty string "
            f"(Q7 5件套 — independent Expert system prompt)"
        )

    @pytest.mark.parametrize("expert_index", [0, 1, 2, 3])
    def test_expert_tools_is_list(
        self, agent_pack: dict, expert_index: int,
    ) -> None:
        expert = agent_pack["experts"][expert_index]
        assert isinstance(expert["tools"], list), (
            f"expert {expert['id']!r} tools must be a list (can be empty "
            f"for LLM-only stages)"
        )

    @pytest.mark.parametrize("expert_index", [0, 1, 2, 3])
    def test_expert_model_is_non_empty_string(
        self, agent_pack: dict, expert_index: int,
    ) -> None:
        expert = agent_pack["experts"][expert_index]
        model = expert["model"]
        assert isinstance(model, str) and model.strip(), (
            f"expert {expert['id']!r} model must be a non-empty string "
            f"(Q7 5件套 — explicit model declaration)"
        )

    @pytest.mark.parametrize("expert_index", [0, 1, 2, 3])
    def test_expert_non_goals_is_non_empty_list(
        self, agent_pack: dict, expert_index: int,
    ) -> None:
        expert = agent_pack["experts"][expert_index]
        assert isinstance(expert["non_goals"], list) and expert["non_goals"], (
            f"expert {expert['id']!r} non_goals must be a non-empty list "
            f"(Q7 5件套 — Expert scope lockdown)"
        )

    @pytest.mark.parametrize("expert_index", [0, 1, 2, 3])
    def test_expert_output_contract_has_schema_ref(
        self, agent_pack: dict, expert_index: int,
    ) -> None:
        expert = agent_pack["experts"][expert_index]
        contract = expert["output_contract"]
        assert isinstance(contract, dict), (
            f"expert {expert['id']!r} output_contract must be a dict"
        )
        assert "schema_ref" in contract, (
            f"expert {expert['id']!r} output_contract.schema_ref required "
            f"(D3 lockdown — references icoder/<SchemaName>/v1)"
        )
        assert contract["schema_ref"].startswith("icoder/"), (
            f"expert {expert['id']!r} schema_ref must be namespaced under icoder/"
        )


# ── Per-expert stage mapping lockdown ──


# Each of the 4 experts covers a specific MedCodER pipeline stage. The
# ``role`` field encodes this — lockdown against silent re-mapping.
_EXPECTED_ROLE_BY_ID = {
    "evidence-extractor": "stage1_extraction",
    "index-navigator": "stage2_retrieval",
    "code-reconciler": "stage3_merge_stage4_rerank",
    "tabular-validator": "stage5_calibration",
}


class TestExpertStageMapping:
    """E1 lockdown: each expert's ``role`` must map to its MedCodER stage."""

    def test_role_mapping_complete(self, agent_pack: dict) -> None:
        roles = {e["id"]: e.get("role") for e in agent_pack["experts"]}
        for eid, expected_role in _EXPECTED_ROLE_BY_ID.items():
            assert roles.get(eid) == expected_role, (
                f"expert {eid!r} role drift: got {roles.get(eid)!r}, "
                f"expected {expected_role!r}"
            )


# ── Agent-level invariants preserved by E1 ──


class TestAgentLevelInvariants:
    """These invariants must survive the E1 refactor (carried over from D3)."""

    def test_pipeline_stages_still_5(self, agent_pack: dict) -> None:
        """The Agent-level pipeline remains the 5-stage MedCodER pipeline.
        E1 redistributes expert ownership across stages but does NOT
        collapse or split stages."""
        stages = agent_pack["pipeline"]["stages"]
        stage_names = [s["name"] for s in stages]
        assert stage_names == [
            "extraction", "retrieval", "merge", "rerank", "calibration",
        ], f"MedCodER 5-stage pipeline broken: {stage_names}"

    def test_production_writeback_blocked_still_true(self, agent_pack: dict) -> None:
        """Hard invariant from M2 — never auto-writeback to EMR/HIS/医保."""
        perms = agent_pack["permissions"]
        assert perms["production_writeback_blocked"] is True
        assert perms["tools"]["writeback"] == "blocked"

    def test_phi_redaction_required(self, agent_pack: dict) -> None:
        """Hard invariant — PHI redaction is mandatory at Orchestrator entry."""
        assert agent_pack["phi_redaction"] == "required"

    def test_context_and_recorder_required(self, agent_pack: dict) -> None:
        """Per A2A SPEC §7.2: context + recorder are required for audit trail."""
        assert agent_pack["context_required"] is True
        assert agent_pack["recorder_required"] is True

    def test_human_review_conditions_cover_low_confidence(
        self, agent_pack: dict,
    ) -> None:
        """Medical coding requires human review on low-confidence paths."""
        conditions = agent_pack["human_review_required_when"]
        # Per M2 design: any rule-flagged or low-confidence path triggers
        # human review. The string ``"manual_review_required == true"``
        # encodes the per-disease confidence < 0.5 trigger.
        assert any("manual_review_required" in c for c in conditions), (
            f"human_review_required_when must cover manual_review_required: {conditions}"
        )