"""MedCodER Coding Review Agent Card tests (M0 — Phase 2 standard).

Per ``MEDCODER_CAPABILITY_AUDIT.md`` (2026-06-21) and the M0 plan, the
canonical Phase 2 Agent Card for medical coding is ``medcoder_coding_review_card``
in ``app.icoder.agent_runtime.a2a.agent_card``. It declares:

  - coding-expert as the sole Expert
  - 5 MCP tools (search_icd / verify_code / get_differentiation_hint /
    rerank_codes / calibrate_confidence)
  - 6 non_goals (production_writeback_blocked, no fully automated claims, etc.)
  - production_writeback_blocked=true, phi_redaction=required

Phase D3 (2026-06-26): the legacy 14-stage ``homepage-coding-review``
agent and its ``homepage_coding_review_card`` fixture have been removed.
The MedCodER card is the only published agent card; the
``pipeline.replaces`` field preserves the deprecation history string.
"""

from __future__ import annotations

from app.icoder.agent_runtime.a2a.agent_card import (
    medcoder_coding_review_card,
)


_EXPECTED_MCP_TOOLS = {
    "search_icd",
    "verify_code",
    "get_differentiation_hint",
    "rerank_codes",
    "calibrate_confidence",
}

_EXPECTED_PIPELINE_STAGES = (
    "extraction",
    "retrieval",
    "merge",
    "rerank",
    "calibration",
)


# ---------------------------------------------------------------------------
# 5-piece Agent Card completeness
# ---------------------------------------------------------------------------


def test_medcoder_card_has_five_pieces():
    """system_prompt / experts / tools / non_goals / output_contract all present."""
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    assert card.description  # system_prompt-equivalent
    assert md["experts"] == ["coding-expert"]
    assert md["mcp_tools"]
    assert md["non_goals"]
    assert md["output_contract"]["schema_ref"] == "icoder/MedicalCodingOutputSchema/v1"


# ---------------------------------------------------------------------------
# coding-expert declared
# ---------------------------------------------------------------------------


def test_medcoder_card_declares_coding_expert():
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    assert "coding-expert" in md["experts"]
    # Skills also surface the expert explicitly via orchestration skill
    orchestration = next(s for s in card.skills if s.id == "medcoder_5_stage_pipeline")
    assert orchestration.description


# ---------------------------------------------------------------------------
# 5 MCP tools enumerated
# ---------------------------------------------------------------------------


def test_medcoder_card_enumerates_five_mcp_tools():
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    assert set(md["mcp_tools"]) == _EXPECTED_MCP_TOOLS
    # Each MCP tool also has a corresponding AgentSkill (5 skills)
    skill_ids = {s.id for s in card.skills}
    for tool in _EXPECTED_MCP_TOOLS:
        assert tool in skill_ids, f"missing AgentSkill for MCP tool {tool!r}"


def test_medcoder_card_pipeline_stages_complete():
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    assert tuple(md["pipeline"]["stages"]) == _EXPECTED_PIPELINE_STAGES


# ---------------------------------------------------------------------------
# non_goals includes 'not fully automated' + writeback blocked
# ---------------------------------------------------------------------------


def test_medcoder_card_non_goals_block_fully_automated_claim():
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    joined = "\n".join(md["non_goals"])
    assert "fully automated" in joined, (
        "non_goals must explicitly forbid 'fully automated coding' claim — "
        "MedCodER is AI-assisted, not automated."
    )
    assert "写回" in joined or "writeback" in joined.lower(), (
        "non_goals must forbid writeback to EMR/HIS/医保"
    )
    assert md["production_writeback_blocked"] is True
    assert md["phi_redaction"] == "required"


# ---------------------------------------------------------------------------
# production_writeback_blocked is true (Phase 1 hard requirement)
# ---------------------------------------------------------------------------


def test_medcoder_card_writeback_blocked_and_phi_required():
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    assert md["production_writeback_blocked"] is True
    assert md["phi_redaction"] == "required"
    # Context + Recorder + Metrics integration must be required (Phase 1 closes)
    assert md["context_required"] is True
    assert md["recorder_required"] is True
    assert md["metrics_required"] is True


# ---------------------------------------------------------------------------
# Replaces homepage-coding-review (no parallel 14-stage)
# Phase D3 (2026-06-26): the homepage-coding-review agent is removed, but
# the replaces string in the medcoder card's pipeline metadata preserves
# the deprecation history for downstream log readers.
# ---------------------------------------------------------------------------


def test_medcoder_card_replaces_homepage_14_stage():
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    assert "homepage-coding-review" in md["pipeline"]["replaces"]
    assert "14-stage" in md["pipeline"]["replaces"]


# ---------------------------------------------------------------------------
# output_contract: extracted_diagnoses is REQUIRED (MedCodER signature)
# ---------------------------------------------------------------------------


def test_medcoder_card_output_contract_requires_extracted_diagnoses():
    card = medcoder_coding_review_card()
    md = card.metadata["icoder"]
    assert md["output_contract"]["extracted_diagnoses_required"] is True
    triggers = md["output_contract"]["human_review_required_when"]
    assert "manual_review_required == true" in triggers
    assert any("issues_found" in t for t in triggers)


# ---------------------------------------------------------------------------
# discovery: card url matches the A2A route pattern
# ---------------------------------------------------------------------------


def test_medcoder_card_url_points_to_message_send_endpoint():
    card = medcoder_coding_review_card()
    assert card.url == "/api/icoder/agents/medcoder-coding-review/v1/message:send"
    # With base_url override
    card2 = medcoder_coding_review_card(base_url="https://icoder.example.com")
    assert card2.url == "https://icoder.example.com/api/icoder/agents/medcoder-coding-review/v1/message:send"


def test_medcoder_card_declares_three_rule_sets():
    """The MedCodER agent card must declare the 3 rule_sets used by the
    compliance engine (medical_coding / drg_dip / audit). External A2A
    consumers rely on this metadata to route the right rule_set to the
    right agent. Regression locked down after D3 migration lost this
    field (Finding-004 from D4 QA)."""
    card = medcoder_coding_review_card()
    rule_sets = card.metadata["icoder"]["rule_sets"]
    assert isinstance(rule_sets, list), f"rule_sets must be a list, got {type(rule_sets)}"
    assert set(rule_sets) == {"medical_coding", "drg_dip", "audit"}, (
        f"rule_sets must be exactly {{medical_coding, drg_dip, audit}}, got {rule_sets}"
    )
    # Order-preserving check: medical_coding first (primary), audit last
    assert rule_sets[0] == "medical_coding", (
        f"rule_sets[0] must be 'medical_coding' (primary), got {rule_sets[0]}"
    )
    assert rule_sets[-1] == "audit", (
        f"rule_sets[-1] must be 'audit' (downstream), got {rule_sets[-1]}"
    )
