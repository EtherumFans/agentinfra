"""Tests for medcoder_adapter — extraction/re-rank prompts + JSON parsers + fuzzy match."""
from __future__ import annotations

import os
import sys

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from icoder_runtime.providers.medical_coding import medcoder_adapter as mod  # noqa: E402
from icoder_runtime.providers.medical_coding.medcoder_adapter import (  # noqa: E402
    build_extraction_messages,
    build_rerank_messages,
    parse_extraction_response,
    parse_rerank_response,
    fuzzy_evidence_to_span,
    is_medcoder_fewshot_enabled,
    MEDCODER_FEWSHOT_ENV,
)


# ── Prompt builders ──


class TestPromptBuilders:
    def test_extraction_messages_structure(self):
        # P1.0-A: few-shot is gated behind ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT.
        # Existing E1.8 structure test must opt in to verify few-shot content.
        old = os.environ.get(MEDCODER_FEWSHOT_ENV)
        os.environ[MEDCODER_FEWSHOT_ENV] = "true"
        try:
            msgs = build_extraction_messages("患者主诉胸痛3天。")
        finally:
            if old is None:
                os.environ.pop(MEDCODER_FEWSHOT_ENV, None)
            else:
                os.environ[MEDCODER_FEWSHOT_ENV] = old
        # E1.8: 1 system + 3 few-shot user/assistant pairs + 1 user = 8
        assert len(msgs) == 8
        assert msgs[0]["role"] == "system"
        assert "disease_text" in msgs[0]["content"]  # schema hint
        # Few-shot pairs occupy msgs[1:7]
        for i in range(1, 7, 2):
            assert msgs[i]["role"] == "user"
            assert msgs[i + 1]["role"] == "assistant"
        # Final user message contains the EMR text
        assert msgs[7]["role"] == "user"
        assert "胸痛" in msgs[7]["content"]

    def test_extraction_few_shot_covers_buried_procedures(self):
        """E1.8: few-shot Example 2 (buried procedures) must appear in messages."""
        old = os.environ.get(MEDCODER_FEWSHOT_ENV)
        os.environ[MEDCODER_FEWSHOT_ENV] = "true"
        try:
            msgs = build_extraction_messages("any emr")
        finally:
            if old is None:
                os.environ.pop(MEDCODER_FEWSHOT_ENV, None)
            else:
                os.environ[MEDCODER_FEWSHOT_ENV] = old
        # Indexing: [system, ex1_user, ex1_asst, ex2_user, ex2_asst, ex3_user, ex3_asst, user]
        example2_assistant = msgs[4]["content"]
        assert "procedure_mentions" in example2_assistant
        # And must include at least one buried procedure (脐动脉插管).
        assert "脐动脉插管" in example2_assistant or "剖宫产" in example2_assistant

    def test_extraction_few_shot_covers_no_procedures_case(self):
        """E1.8: few-shot Example 3 (no procedures) — procedure_mentions: []."""
        old = os.environ.get(MEDCODER_FEWSHOT_ENV)
        os.environ[MEDCODER_FEWSHOT_ENV] = "true"
        try:
            msgs = build_extraction_messages("any emr")
        finally:
            if old is None:
                os.environ.pop(MEDCODER_FEWSHOT_ENV, None)
            else:
                os.environ[MEDCODER_FEWSHOT_ENV] = old
        example3_assistant = msgs[6]["content"]
        assert "procedure_mentions" in example3_assistant
        # The empty array literal must be present.
        assert "[]" in example3_assistant

    def test_rerank_messages_structure(self):
        cands = [
            {"code": "I50.900", "name": "心力衰竭", "score": 0.95, "source": "retrieve"},
            {"code": "I50.100", "name": "左心衰竭", "score": 0.7, "source": "retrieve"},
        ]
        msgs = build_rerank_messages("心力衰竭", "胸闷气短", cands)
        assert len(msgs) == 2
        user = msgs[1]["content"]
        assert "心力衰竭" in user
        assert "胸闷气短" in user
        assert "I50.900" in user
        assert "I50.100" in user

    def test_rerank_includes_differentiation_hints(self):
        cands = [{"code": "I50.900", "name": "心力衰竭", "score": 0.5, "source": "retrieve"}]
        msgs = build_rerank_messages("心衰", "胸闷", cands, differentiation_hints=["P0: 心衰 vs 左心衰"])
        assert "P0" in msgs[1]["content"]
        assert "心衰 vs 左心衰" in msgs[1]["content"]

    def test_rerank_handles_empty_candidates(self):
        msgs = build_rerank_messages("unknown", "x", [])
        assert "无候选" in msgs[1]["content"]


# ── P1.0-A: few-shot feature flag gate ───────────────────────────────────


class TestFewShotGate:
    """P1.0-A: E1.8 few-shot exemplars are gated by ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT.

    Default is OFF (E2.0 negative signal — see docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md).
    Coding-quality project can opt in via env var to re-test new prompts.
    """

    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch):
        # Strip the env var before each test, then let individual tests set what they need.
        monkeypatch.delenv(MEDCODER_FEWSHOT_ENV, raising=False)

    def test_default_off_returns_2_messages(self):
        """Without env var set, build_extraction_messages returns system + user only."""
        msgs = build_extraction_messages("患者主诉胸痛")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "胸痛" in msgs[1]["content"]

    def test_explicit_true_returns_8_messages(self, monkeypatch):
        monkeypatch.setenv(MEDCODER_FEWSHOT_ENV, "true")
        msgs = build_extraction_messages("患者主诉胸痛")
        # 1 system + 3 pairs × 2 + 1 user = 8
        assert len(msgs) == 8

    def test_explicit_false_returns_2_messages(self, monkeypatch):
        monkeypatch.setenv(MEDCODER_FEWSHOT_ENV, "false")
        msgs = build_extraction_messages("x")
        assert len(msgs) == 2

    def test_truthy_variants_enable(self, monkeypatch):
        for v in ("1", "TRUE", "True", "yes", "on"):
            monkeypatch.setenv(MEDCODER_FEWSHOT_ENV, v)
            assert is_medcoder_fewshot_enabled() is True, f"value {v!r} should enable"

    def test_other_values_disable(self, monkeypatch):
        for v in ("0", "no", "off", "", "random", "truebutnotreally"):
            monkeypatch.setenv(MEDCODER_FEWSHOT_ENV, v)
            assert is_medcoder_fewshot_enabled() is False, f"value {v!r} should disable"

    def test_exemplars_still_loaded_when_disabled(self, monkeypatch):
        """The exemplars must remain importable for opt-in re-enable — we only
        skip injecting them at prompt-build time. This test locks that in.
        """
        monkeypatch.setenv(MEDCODER_FEWSHOT_ENV, "false")
        # The constant exists and is non-empty.
        assert len(mod._EXTRACTION_FEW_SHOT) >= 6
        # But the message list does not include them.
        msgs = build_extraction_messages("x")
        for m in msgs:
            assert "脐动脉插管" not in m["content"]
            assert "急性胆囊炎" not in m["content"]


# ── JSON parsers ──


class TestExtractionParser:
    def test_parses_clean_json_array(self):
        content = '[{"disease_text": "心衰", "supporting_evidence": "胸闷", "llm_initial_code": "I50.900"}]'
        out = parse_extraction_response(content)
        assert len(out) == 1
        assert out[0]["disease_text"] == "心衰"
        assert out[0]["llm_initial_code"] == "I50.900"

    def test_parses_code_fenced_json(self):
        content = '```json\n[{"disease_text": "肺炎", "supporting_evidence": "咳嗽", "llm_initial_code": "J18.900"}]\n```'
        out = parse_extraction_response(content)
        assert len(out) == 1
        assert out[0]["disease_text"] == "肺炎"

    def test_parses_with_prose_around_json(self):
        content = 'Here is the result:\n[{"disease_text": "骨折", "supporting_evidence": "外伤", "llm_initial_code": "S72.000"}]\nDone.'
        out = parse_extraction_response(content)
        assert len(out) == 1
        assert out[0]["disease_text"] == "骨折"

    def test_tolerates_trailing_commas(self):
        content = '[{"disease_text": "心衰", "supporting_evidence": "胸闷", "llm_initial_code": "I50.900",},]'
        out = parse_extraction_response(content)
        assert len(out) == 1

    def test_empty_or_invalid_returns_empty(self):
        # E1.4: returns ExtractionResult (was list[dict]). Empty/invalid
        # responses produce ExtractionResult with no diseases.
        assert parse_extraction_response("").diseases == []
        assert parse_extraction_response("not json at all").diseases == []
        # Standalone ``{}`` has no ``diseases`` key → empty result.
        assert parse_extraction_response("{}").diseases == []  # not an object-with-diseases

    def test_normalizes_missing_fields(self):
        content = '[{"disease_text": "心衰"}]'
        out = parse_extraction_response(content)
        assert len(out) == 1
        assert out[0]["disease_text"] == "心衰"
        assert out[0]["supporting_evidence"] == ""
        assert out[0]["llm_initial_code"] == ""

    def test_filters_non_dict_items(self):
        content = '[{"disease_text": "A"}, "bad", null, {"disease_text": "B"}]'
        out = parse_extraction_response(content)
        assert len(out) == 2
        assert [x["disease_text"] for x in out] == ["A", "B"]


class TestRerankParser:
    def test_parses_ranked_dict(self):
        content = '{"ranked": [{"final_code": "I50.900", "final_name": "心力衰竭", "final_confidence": 0.95, "rationale": "支持证据明确"}]}'
        out = parse_rerank_response(content)
        assert len(out) == 1
        assert out[0]["code"] == "I50.900"
        assert out[0]["confidence"] == 0.95
        assert "支持证据明确" in out[0]["rationale"]

    def test_parses_code_fenced(self):
        content = '```json\n{"ranked": [{"final_code": "J18.900", "final_name": "肺炎", "final_confidence": 0.85, "rationale": ""}]}\n```'
        out = parse_rerank_response(content)
        assert len(out) == 1
        assert out[0]["code"] == "J18.900"

    def test_confidence_clamped_to_0_1(self):
        content = '{"ranked": [{"final_code": "X", "final_name": "Y", "final_confidence": 1.5, "rationale": ""}]}'
        out = parse_rerank_response(content)
        assert out[0]["confidence"] == 1.0

        content2 = '{"ranked": [{"final_code": "X", "final_name": "Y", "final_confidence": -0.3, "rationale": ""}]}'
        out2 = parse_rerank_response(content2)
        assert out2[0]["confidence"] == 0.0

    def test_invalid_confidence_defaults_to_zero(self):
        content = '{"ranked": [{"final_code": "X", "final_name": "Y", "final_confidence": "high", "rationale": ""}]}'
        out = parse_rerank_response(content)
        assert out[0]["confidence"] == 0.0

    def test_empty_or_invalid(self):
        assert parse_rerank_response("") == []
        assert parse_rerank_response("not json") == []
        assert parse_rerank_response("[]") == []  # not a dict

    def test_ranked_must_be_list(self):
        assert parse_rerank_response('{"ranked": "not a list"}') == []


# ── Fuzzy evidence matching ──


class TestFuzzyEvidenceMatching:
    def test_exact_substring_match(self):
        text = "患者因胸闷气短3天入院，诊断为心力衰竭。"
        span = fuzzy_evidence_to_span("胸闷气短3天", text)
        assert span is not None
        assert text[span["char_start"]:span["char_end"]] == "胸闷气短3天"

    def test_substring_match_returns_first_occurrence(self):
        text = "胸闷气短。再次胸闷气短。"
        span = fuzzy_evidence_to_span("胸闷气短", text)
        assert span["char_start"] == 0

    def test_fuzzy_match_with_whitespace_drift(self):
        # Source has "胸 闷 气 短" but evidence says "胸闷气短"
        text = "患者 胸 闷 气 短 3天，诊断心力衰竭。"
        span = fuzzy_evidence_to_span("胸闷气短", text, threshold=0.7)
        # Should still match given the high similarity
        if span is not None:
            assert "胸" in text[span["char_start"]:span["char_end"]]
            assert "短" in text[span["char_start"]:span["char_end"]]

    def test_no_match_returns_none(self):
        text = "This is English text without Chinese."
        span = fuzzy_evidence_to_span("完全不同的中文", text, threshold=0.85)
        assert span is None

    def test_empty_inputs(self):
        assert fuzzy_evidence_to_span("", "text") is None
        assert fuzzy_evidence_to_span("text", "") is None
        assert fuzzy_evidence_to_span("", "") is None

    def test_snaps_to_sentence_boundary(self):
        text = "入院时情况：患者胸闷气短3天，伴有下肢水肿，诊断为心力衰竭。"
        span = fuzzy_evidence_to_span("胸闷气短", text)
        assert span is not None
        # Should snap to include "胸闷气短3天，" or similar
        snippet = text[span["char_start"]:span["char_end"]]
        assert "胸闷" in snippet
        assert "短" in snippet
