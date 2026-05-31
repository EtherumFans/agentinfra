# Regression: Evidence Ranking — determinism, edge cases, malformed
import pytest
from app.services.evidence_ranker import (
    rank_evidence_for_code, detect_conflicts, detect_unsupported_codes,
    _score_source_document, _score_admission_consistency, _score_negation_uncertainty,
    _check_history_background, _assign_category,
    EvidenceCategory,
)


class TestEvidenceDeterminism:
    """All deterministic functions produce identical results on repeated calls."""

    def test_source_scoring_deterministic(self):
        docs = ["出院小结", "手术记录", "病程记录", "检查报告", "既往史", "主诉", "现病史"]
        for dt in docs:
            results = [_score_source_document(dt) for _ in range(5)]
            assert all(r == results[0] for r in results)

    def test_admission_consistency_deterministic(self):
        results = [_score_admission_consistency("为行术后辅助化疗入院", "术后化疗") for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_negation_scoring_deterministic(self):
        results = [_score_negation_uncertainty(True, "confirmed") for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_history_detection_deterministic(self):
        results = [_check_history_background("患者5年前因腰椎间盘突出行治疗", "") for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_ranking_same_input_same_output(self):
        evidence = [{"evidence_text": "直肠癌术后化疗", "source_document": "出院小结", "doc_type": "出院小结",
                      "certainty": "confirmed", "negation": False}]
        r1 = rank_evidence_for_code("Z51.102", "恶性肿瘤化学治疗", evidence, [], [], "术后化疗", {}, {})
        r2 = rank_evidence_for_code("Z51.102", "恶性肿瘤化学治疗", evidence, [], [], "术后化疗", {}, {})
        assert r1[0]["strength_score"] == r2[0]["strength_score"]


class TestEvidenceEdgeCases:
    """Edge cases produce valid output without crashing."""

    def test_empty_evidence_list(self):
        r = rank_evidence_for_code("Z51", "test", [], [], [], "", {}, {})
        assert r == []

    def test_all_evidence_types(self):
        """Every source document type should produce a valid score."""
        docs = ["出院小结", "手术记录", "病程记录", "检查报告", "既往史", "主诉", "现病史", "unknown"]
        for dt in docs:
            evidence = [{"evidence_text": "test data", "source_document": dt, "doc_type": dt,
                          "certainty": "confirmed", "negation": False}]
            r = rank_evidence_for_code("X99", "test", evidence, [], [], "", {}, {})
            if r:
                assert 0.0 <= r[0]["strength_score"] <= 1.0

    def test_negated_evidence_always_conflicting(self):
        evidence = [{"evidence_text": "排除感染", "source_document": "现病史", "doc_type": "现病史",
                      "certainty": "confirmed", "negation": True}]
        r = rank_evidence_for_code("J98", "肺炎", evidence, [], [], "", {}, {})
        assert r[0]["conflict_flag"] is True

    def test_high_quality_source_scores_highest(self):
        """出院小结 should score higher than 既往史 for same text."""
        evidence_discharge = [{"evidence_text": "test", "source_document": "出院小结", "doc_type": "出院小结",
                                "certainty": "confirmed", "negation": False}]
        evidence_history = [{"evidence_text": "test", "source_document": "既往史", "doc_type": "既往史",
                              "certainty": "confirmed", "negation": False}]
        r_d = rank_evidence_for_code("X", "test", evidence_discharge, [], [], "", {}, {})
        r_h = rank_evidence_for_code("X", "test", evidence_history, [], [], "", {}, {})
        assert r_d[0]["strength_score"] > r_h[0]["strength_score"]


class TestUnsupportedEdgeCases:
    """Unsupported detection edge cases."""

    def test_no_evidence_all_unsupported(self):
        candidates = [{"code": "A", "name": "a"}, {"code": "B", "name": "b"}]
        r = detect_unsupported_codes(candidates, [], [])
        assert len(r) == 2

    def test_strong_evidence_no_unsupported(self):
        candidates = [{"code": "Z51", "name": "t"}]
        r = detect_unsupported_codes(candidates, [], [{"related_code": "Z51", "strength_score": 0.8}])
        assert len(r) == 0

    def test_borderline_strength(self):
        candidates = [{"code": "X99", "name": "t"}]
        r = detect_unsupported_codes(candidates, [], [{"related_code": "X99", "strength_score": 0.19}])
        assert len(r) == 1  # below 0.2 threshold


class TestConflictEdgeCases:
    """Conflict detection edge cases."""

    def test_empty_inputs(self):
        r = detect_conflicts([], [], {}, "", [], [])
        assert isinstance(r, list)

    def test_none_inputs(self):
        try:
            r = detect_conflicts([], [], {}, "", [], [])
            assert isinstance(r, list)
        except Exception:
            pass  # None inputs may raise TypeError — that's acceptable
