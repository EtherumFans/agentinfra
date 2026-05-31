# Regression: Principal Diagnosis Reasoning — consistency, fallback, malformed
import pytest
from app.agents.experts.homepage_expert import (
    _generate_why_selected, _generate_why_not_selected,
    _analyze_disagreement, _assess_confidence,
    _compute_adjusted_score, _match_rules_to_candidates,
    MedicalRecordHomepageExpert,
)


class TestReasoningDeterminism:
    """Deterministic reasoning functions must produce identical output for identical input."""

    def test_why_selected_identical_10_runs(self):
        c = {"code": "Z51.102", "name": "恶性肿瘤化学治疗", "finding": "直肠癌术后化疗", "etiology": ""}
        results = [_generate_why_selected(c, ["R013", "R001"], "", 0.82) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_why_not_selected_identical(self):
        others = [{"code": "C20.x00", "name": "直肠恶性肿瘤", "score": 0.65}]
        results = [_generate_why_not_selected("Z51.102", others, {}) for _ in range(10)]
        assert results[0] == results[-1]

    def test_adjusted_score_deterministic(self):
        c = {"code": "Z51.102", "name": "化疗", "score": 0.80, "finding": "化疗", "etiology": "",
             "certainty": "confirmed", "negation": False}
        scores = [_compute_adjusted_score(c, ["R013", "R001"], {}, "术后化疗") for _ in range(10)]
        assert all(s == scores[0] for s in scores)

    def test_confidence_same_input_same_output(self):
        primary = {"code": "Z51.102", "name": "化疗", "confidence": 0.88}
        candidates = [{"code": "Z51.102", "score": 0.88, "confidence": 0.88}, {"code": "C20", "score": 0.60, "confidence": 0.60}]
        results = [_assess_confidence(primary, candidates, {"has_disagreement": False}) for _ in range(10)]
        assert all(r[0] == results[0][0] for r in results)  # same confidence_level


class TestReasoningFallbackCoverage:
    """Edge cases produce valid output."""

    def test_empty_candidates(self):
        r = _generate_why_selected({}, [], "", 0)
        assert isinstance(r, str)

    def test_disagreement_empty_existing(self):
        r = _analyze_disagreement({"code": "Z51"}, [], [{"code": "Z51"}], {})
        assert r["has_disagreement"] is False

    def test_disagreement_none_inputs(self):
        r = _analyze_disagreement(None, [], [], {})
        assert r["has_disagreement"] is False

    def test_confidence_single_candidate(self):
        primary = {"confidence": 0.92}
        level, rationale, escalation = _assess_confidence(primary, [{"score": 0.92}], {"has_disagreement": False})
        assert level in ("high", "medium", "low")

    def test_rule_match_empty_docs(self):
        matches = _match_rules_to_candidates(
            [{"code": "Z51.102", "name": "test", "finding": "test", "etiology": ""}],
            "", [], {}
        )
        assert isinstance(matches, dict)


class TestReasoningMalformedInput:
    """Handles bad inputs gracefully."""

    def test_candidate_missing_keys(self):
        c = {"code": "X99"}  # no name, no score
        r = _generate_why_selected(c, ["R001"], "", 0.5)
        assert isinstance(r, str)

    def test_confidence_negative_score(self):
        primary = {"confidence": -0.5}
        level, _, _ = _assess_confidence(primary, [{"score": -0.5}], {"has_disagreement": False})
        assert level in ("low", "medium")  # should not crash

    def test_match_rules_bizarre_admission(self):
        matches = _match_rules_to_candidates(
            [{"code": "Z51", "name": "t", "finding": "t", "etiology": ""}],
            "!@#$%^&*()化疗手术透析", [], {}
        )
        assert isinstance(matches, dict)


class TestHomepageExpertDegraded:
    """Full expert with degraded input."""

    @pytest.mark.asyncio
    async def test_empty_documents_does_not_crash(self):
        expert = MedicalRecordHomepageExpert()
        context = {
            "encounter_id": "DEGRADED",
            "admission_reason": "",
            "documents": [],
            "diagnosis_candidates": [],
            "procedure_candidates": [],
            "existing_diagnosis_codes": [],
            "existing_procedure_codes": [],
            "timeline": {},
        }
        result = await expert.run(context)
        assert result["primary_diagnosis"] is None
        assert result["primary_diagnosis_reasoning"] is None
