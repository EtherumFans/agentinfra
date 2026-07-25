"""A1B-AE.7 — Interviewing + Coding wrapper + external-Expert gates.

Coverage:
§1 Coding Expert wrapper (delegates to icoder/medical-coding-agent@2.0.0)
§2 DrugBank stub (licence-required, no LLM fallback)
§3 POSOS stub (licence-required, no LLM fallback)
§4 Web Search Expert (3-value policy gate)
§5 Interviewing Expert (schema-driven, branching, transcript)
§6 External-Expert Gate (5 gated experts, 5 reasons)
§7 Charter Amendment 1 §7 forbidden verdicts preserved
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


# ─────────────────────────────────────────────────────────────────────
# §1 Coding Expert wrapper
# ─────────────────────────────────────────────────────────────────────

def test_coding_expert_constants():
    from app.agents.experts.coding_expert import (
        CODING_EXPERT_CANONICAL_KEY,
        CODING_EXPERT_DELEGATES_TO,
        CODING_EXPERT_OUTPUT_CONTRACT,
    )
    assert CODING_EXPERT_CANONICAL_KEY == "coding-expert"
    assert CODING_EXPERT_DELEGATES_TO == "icoder/medical-coding-agent@2.0.0"
    assert CODING_EXPERT_OUTPUT_CONTRACT == "icoder/MedicalCodingAgentOutputV2/v1"


def test_coding_expert_delegate_without_pack_output():
    from app.agents.experts.coding_expert import delegate
    r = delegate("MRI T12 压缩性骨折")
    assert r.delegation.input_text.startswith("MRI")
    assert r.delegation.human_review_required is True
    assert r.delegation.phi_redacted is True
    assert r.delegation.production_writeback_blocked is True
    assert r.extracted_from_pack is False
    assert r.pack_output == {}
    assert "caller" in r.notes


def test_coding_expert_delegate_surfaces_pack_output_verbatim():
    from app.agents.experts.coding_expert import delegate
    pack_output = {
        "primary_diagnosis": "S22.000",
        "human_review": {"required": True},
    }
    r = delegate("gold case", pack_output=pack_output)
    assert r.extracted_from_pack is True
    assert r.pack_output == pack_output


def test_coding_expert_runtime_mode_passthrough():
    from app.agents.experts.coding_expert import delegate
    r = delegate("foo", runtime_mode="medcoder_deep")
    assert r.delegation.runtime_mode == "medcoder_deep"


# ─────────────────────────────────────────────────────────────────────
# §2 DrugBank stub
# ─────────────────────────────────────────────────────────────────────

def test_drugbank_constants():
    from app.agents.experts.drugbank_expert import (
        DRUGBANK_EXPERT_CANONICAL_KEY,
        DRUGBANK_LICENCE_REQUIRED,
        DRUGBANK_LLM_FALLBACK_ALLOWED,
    )
    assert DRUGBANK_EXPERT_CANONICAL_KEY == "drugbank"
    assert DRUGBANK_LICENCE_REQUIRED is True
    assert DRUGBANK_LLM_FALLBACK_ALLOWED is False  # red line


def test_drugbank_stub_returns_empty_with_flag():
    from app.agents.experts.drugbank_expert import lookup
    r = lookup("metformin interactions")
    assert r.live_lookup_performed is False
    assert r.drug_info == {}
    assert r.interactions == []
    assert "STUB" in r.notes


def test_drugbank_stub_empty_query():
    from app.agents.experts.drugbank_expert import lookup
    r = lookup("")
    assert r.live_lookup_performed is False
    assert r.notes == "empty query"


def test_drugbank_stub_no_llm_fallback_marker():
    from app.agents.experts.drugbank_expert import DRUGBANK_LLM_FALLBACK_ALLOWED
    # Red line: drug-interaction data must NEVER come from an LLM.
    assert DRUGBANK_LLM_FALLBACK_ALLOWED is False


# ─────────────────────────────────────────────────────────────────────
# §3 POSOS stub
# ─────────────────────────────────────────────────────────────────────

def test_posos_constants():
    from app.agents.experts.posos_expert import (
        POSOS_EXPERT_CANONICAL_KEY,
        POSOS_LICENCE_REQUIRED,
        POSOS_LLM_FALLBACK_ALLOWED,
    )
    assert POSOS_EXPERT_CANONICAL_KEY == "posos"
    assert POSOS_LICENCE_REQUIRED is True
    assert POSOS_LLM_FALLBACK_ALLOWED is False


def test_posos_stub_returns_empty_with_flag():
    from app.agents.experts.posos_expert import guide
    r = guide("renal dose adjustment metformin")
    assert r.live_lookup_performed is False
    assert r.guidance == {}
    assert "STUB" in r.notes


def test_posos_stub_empty_query():
    from app.agents.experts.posos_expert import guide
    r = guide("")
    assert r.live_lookup_performed is False
    assert r.notes == "empty query"


# ─────────────────────────────────────────────────────────────────────
# §4 Web Search Expert policy gate
# ─────────────────────────────────────────────────────────────────────

def test_web_search_constants():
    from app.agents.experts.web_search_expert import (
        WEB_SEARCH_EXPERT_CANONICAL_KEY,
        WEB_SEARCH_POLICY_DISABLED,
        WEB_SEARCH_POLICY_OPT_IN,
        WEB_SEARCH_POLICY_ENABLED,
    )
    assert WEB_SEARCH_EXPERT_CANONICAL_KEY == "web-search"
    assert WEB_SEARCH_POLICY_DISABLED == "DISABLED_BY_DEFAULT"
    assert WEB_SEARCH_POLICY_OPT_IN == "OPT_IN_PER_PROVIDER"
    assert WEB_SEARCH_POLICY_ENABLED == "ENABLED_FOR_TENANT"


def test_web_search_default_policy_is_disabled():
    from app.agents.experts.web_search_expert import (
        search,
        WEB_SEARCH_POLICY_DISABLED,
    )
    r = search("diabetes guidelines 2026")
    assert r.policy == WEB_SEARCH_POLICY_DISABLED
    assert r.live_search_performed is False
    assert r.results == []


def test_web_search_partial_opt_in_resolves_to_opt_in():
    from app.agents.experts.web_search_expert import (
        search,
        WEB_SEARCH_POLICY_OPT_IN,
    )
    r = search("foo", tenant_opt_in=True, provider_opt_in=False)
    assert r.policy == WEB_SEARCH_POLICY_OPT_IN


def test_web_search_dual_opt_in_resolves_to_enabled():
    from app.agents.experts.web_search_expert import (
        search,
        WEB_SEARCH_POLICY_ENABLED,
    )
    r = search("foo", tenant_opt_in=True, provider_opt_in=True)
    assert r.policy == WEB_SEARCH_POLICY_ENABLED


def test_web_search_explicit_policy_wins():
    from app.agents.experts.web_search_expert import (
        search,
        WEB_SEARCH_POLICY_DISABLED,
    )
    r = search(
        "foo",
        policy=WEB_SEARCH_POLICY_DISABLED,
        tenant_opt_in=True,
        provider_opt_in=True,
    )
    assert r.policy == WEB_SEARCH_POLICY_DISABLED


def test_web_search_invalid_policy_raises():
    from app.agents.experts.web_search_expert import search
    with pytest.raises(ValueError):
        search("foo", policy="NOT_A_REAL_POLICY")


def test_web_search_still_returns_empty_when_enabled():
    """A1B-AE.7 never performs a live web call — even when policy=ENABLED."""
    from app.agents.experts.web_search_expert import (
        search,
        WEB_SEARCH_POLICY_ENABLED,
    )
    r = search("foo", policy=WEB_SEARCH_POLICY_ENABLED)
    assert r.live_search_performed is False
    assert "STUB" in r.notes


# ─────────────────────────────────────────────────────────────────────
# §5 Interviewing Expert
# ─────────────────────────────────────────────────────────────────────

def test_interviewing_constants():
    from app.agents.experts.interviewing_expert import (
        INTERVIEWING_EXPERT_CANONICAL_KEY,
        INTERVIEW_COMPLETE,
    )
    assert INTERVIEWING_EXPERT_CANONICAL_KEY == "interviewing"
    assert INTERVIEW_COMPLETE == "INTERVIEW_COMPLETE"


def test_interviewing_start_requires_questions():
    from app.agents.experts.interviewing_expert import start_interview
    with pytest.raises(ValueError):
        start_interview("q", [])


def test_interviewing_linear_progression():
    from app.agents.experts.interviewing_expert import (
        start_interview,
        advance,
        QuestionSpec,
    )
    state = start_interview(
        "intake",
        [
            QuestionSpec(key="name", prompt="What is your name?"),
            QuestionSpec(key="age", prompt="What is your age?", kind="number"),
        ],
    )

    s1 = advance(state)  # prime
    assert s1.complete is False
    assert s1.next_question.key == "name"

    s2 = advance(state, answer="Alice")
    assert s2.complete is False
    assert s2.next_question.key == "age"

    s3 = advance(state, answer=42)
    assert s3.complete is True
    assert s3.next_question is None


def test_interviewing_branching_skip():
    from app.agents.experts.interviewing_expert import (
        start_interview,
        advance,
        QuestionSpec,
    )

    def has_smoking_history(answers):
        return answers.get("smoking") == "yes"

    state = start_interview(
        "triage",
        [
            QuestionSpec(key="smoking", prompt="Do you smoke?", kind="boolean"),
            QuestionSpec(
                key="cigarettes_per_day",
                prompt="How many cigarettes per day?",
                kind="number",
                ask_if=has_smoking_history,
            ),
            QuestionSpec(key="exercise", prompt="Exercise frequency?"),
        ],
    )

    advance(state)  # prime → smoking
    s_after_smoking_no = advance(state, answer="no")  # smoking=no → skip cigarettes_per_day → exercise
    s = advance(state, answer="3x/week")  # answer exercise → done

    assert s.complete is True
    assert "cigarettes_per_day" in s_after_smoking_no.skipped_keys
    assert state.answers["smoking"] == "no"
    assert state.answers["exercise"] == "3x/week"
    assert "cigarettes_per_day" not in state.answers


def test_interviewing_transcript():
    from app.agents.experts.interviewing_expert import (
        start_interview,
        advance,
        transcript,
        QuestionSpec,
    )
    state = start_interview(
        "q",
        [QuestionSpec(key="a", prompt="A?"), QuestionSpec(key="b", prompt="B?")],
    )
    advance(state)
    advance(state, answer="yes")
    t = transcript(state)
    assert t["questionnaire_key"] == "q"
    assert t["question_count"] == 2
    assert t["answered_count"] == 1
    assert t["answers"] == {"a": "yes"}


# ─────────────────────────────────────────────────────────────────────
# §6 External-Expert Gate
# ─────────────────────────────────────────────────────────────────────

def test_gate_constants():
    from app.agents.experts.external_expert_gate import (
        GATED_EXPERTS,
        GATE_REASON_OK,
        GATE_REASON_LICENCE_REQUIRED,
        GATE_REASON_EGRESS_DISABLED,
        GATE_REASON_REGION_BLOCKED,
        GATE_REASON_PROVIDER_OPT_IN_MISSING,
    )
    assert GATED_EXPERTS == frozenset(
        {"pubmed", "clinical-trials", "drugbank", "posos", "web-search"}
    )
    assert GATE_REASON_OK == "OK"
    assert GATE_REASON_LICENCE_REQUIRED == "LICENCE_REQUIRED"


def test_gate_non_gated_expert_passes_through():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_OK,
    )
    d = evaluate("coding-expert")
    assert d.permitted is True
    assert d.reason == GATE_REASON_OK


def test_gate_drugbank_requires_licence():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_LICENCE_REQUIRED,
    )
    d = evaluate("drugbank", egress_enabled=True, region="EU")
    assert d.permitted is False
    assert d.reason == GATE_REASON_LICENCE_REQUIRED


def test_gate_posos_requires_licence():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_LICENCE_REQUIRED,
    )
    d = evaluate("posos", egress_enabled=True, region="EU")
    assert d.permitted is False
    assert d.reason == GATE_REASON_LICENCE_REQUIRED


def test_gate_drugbank_with_licence_then_requires_egress():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_EGRESS_DISABLED,
    )
    d = evaluate("drugbank", licence_tokens=["fake-licence"])
    assert d.permitted is False
    assert d.reason == GATE_REASON_EGRESS_DISABLED


def test_gate_drugbank_licence_and_egress_then_region_check():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_REGION_BLOCKED,
    )
    d = evaluate(
        "drugbank",
        licence_tokens=["x"],
        egress_enabled=True,
        region="UNKNOWN",
    )
    assert d.permitted is False
    assert d.reason == GATE_REASON_REGION_BLOCKED


def test_gate_drugbank_all_conditions_met_permits():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_OK,
    )
    d = evaluate(
        "drugbank",
        licence_tokens=["x"],
        egress_enabled=True,
        region="eu",
    )
    assert d.permitted is True
    assert d.reason == GATE_REASON_OK


def test_gate_pubmed_requires_egress():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_EGRESS_DISABLED,
    )
    d = evaluate("pubmed")
    assert d.permitted is False
    assert d.reason == GATE_REASON_EGRESS_DISABLED


def test_gate_pubmed_egress_region_ok_permits():
    from app.agents.experts.external_expert_gate import evaluate
    d = evaluate("pubmed", egress_enabled=True, region="US")
    assert d.permitted is True


def test_gate_web_search_requires_dual_opt_in():
    from app.agents.experts.external_expert_gate import (
        evaluate,
        GATE_REASON_PROVIDER_OPT_IN_MISSING,
    )
    d = evaluate(
        "web-search",
        egress_enabled=True,
        region="EU",
        provider_opt_in=True,
        tenant_opt_in=False,
    )
    assert d.permitted is False
    assert d.reason == GATE_REASON_PROVIDER_OPT_IN_MISSING


def test_gate_web_search_dual_opt_in_permits():
    from app.agents.experts.external_expert_gate import evaluate
    d = evaluate(
        "web-search",
        egress_enabled=True,
        region="EU",
        provider_opt_in=True,
        tenant_opt_in=True,
    )
    assert d.permitted is True


def test_gate_is_gated_helper():
    from app.agents.experts.external_expert_gate import is_gated
    assert is_gated("pubmed") is True
    assert is_gated("memory") is False
    assert is_gated("coding-expert") is False


# ─────────────────────────────────────────────────────────────────────
# §7 Charter Amendment 1 §7 forbidden verdicts preserved
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
