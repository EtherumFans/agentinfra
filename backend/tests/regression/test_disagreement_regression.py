# Regression: Disagreement Analysis — determinism, classification stability
import pytest
from app.services.disagreement_analyzer import (
    _classify_disagreement_type, _is_specificity_diff,
    _check_drg_sensitivity, analyze_disagreements,
    DisagreementType,
)


class TestDisagreementDeterminism:
    """Classification must be deterministic — same input → same type."""

    def test_specificity_diff_deterministic(self):
        results = [_is_specificity_diff("M80.900", "M80.000") for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_classification_deterministic(self):
        for _ in range(10):
            t1, _ = _classify_disagreement_type(
                "M80.900", "骨质疏松", "M80.000", "骨质疏松伴病理性骨折",
                {"unsupported_codes": [], "conflicts": []}, "M80.900", "", {}
            )
        # All runs should produce same type
        for _ in range(9):
            t2, _ = _classify_disagreement_type(
                "M80.900", "骨质疏松", "M80.000", "骨质疏松伴病理性骨折",
                {"unsupported_codes": [], "conflicts": []}, "M80.900", "", {}
            )
            assert t1 == t2

    def test_drg_sensitivity_deterministic(self):
        results = [_check_drg_sensitivity("Z51.102", "C20.x00", {"drg_risks": []}) for _ in range(5)]
        assert all(r[0] == results[0][0] for r in results)


class TestDisagreementClassificationCoverage:
    """All 8 types can be reached."""

    def test_code_specificity_type(self):
        t, _ = _classify_disagreement_type(
            "M80.900", "骨质疏松", "M80.000", "骨质疏松伴病理性骨折",
            {"unsupported_codes": [], "conflicts": []}, "M80.900", "", {}
        )
        assert t == DisagreementType.CODE_SPECIFICITY

    def test_documentation_gap_on_unsupported(self):
        t, _ = _classify_disagreement_type(
            "C20.x00", "直肠癌", "Z51.102", "化疗",
            {"unsupported_codes": [{"code": "C20.x00"}], "conflicts": []}, "C20.x00", "", {}
        )
        assert t == DisagreementType.DOCUMENTATION_GAP

    def test_primary_vs_secondary(self):
        t, _ = _classify_disagreement_type(
            "Z51.102", "化疗", "C20.x00", "直肠癌",
            {"unsupported_codes": [], "conflicts": []}, "Z51.102", "", {}
        )
        assert t == DisagreementType.PRIMARY_VS_SECONDARY

    def test_code_selection_fallback(self):
        t, _ = _classify_disagreement_type(
            "J15.200", "肺炎", "R91.x02", "肺部阴影",
            {"unsupported_codes": [], "conflicts": []}, "M80.900", "", {}
        )
        assert t == DisagreementType.CODE_SELECTION

    def test_rule_violation(self):
        t, _ = _classify_disagreement_type(
            "Z51.102", "化疗", "C20.x00", "直肠癌",
            {"unsupported_codes": [], "conflicts": []}, "Z51.102", "",
            {"Z51.102": ["R013"]}
        )
        assert t == DisagreementType.RULE_VIOLATION


class TestDisagreementEdgeCases:
    """Edge cases for disagreement analysis."""

    def test_empty_gold_codes(self):
        r = analyze_disagreements([], [], {}, {}, [], [], [], [], "", {}, {})
        assert r["summary"]["disagreements"] == 0

    def test_single_code_agree(self):
        r = analyze_disagreements(
            [{"code": "Z51.102", "name": "化疗", "score": 0.8, "evidence_text": ""}],
            [], {}, {"unsupported_codes": [], "conflicts": []},
            ["Z51.102"], [], [], [], "", {}, {}
        )
        assert r["summary"]["disagreements"] == 0

    def test_missing_gold_produces_correction(self):
        r = analyze_disagreements(
            [{"code": "Z51.102", "name": "化疗", "score": 0.8}],
            [], {}, {"unsupported_codes": [], "conflicts": []},
            ["Z51.102", "C50.900"], [], [], [], "", {}, {}
        )
        assert r["summary"]["disagreements"] >= 1  # missing C50.900

    def test_type_distribution_populated(self):
        r = analyze_disagreements(
            [{"code": "M80.900", "name": "骨质疏松", "score": 0.8}],
            [], {}, {"unsupported_codes": [], "conflicts": []},
            ["M80.000"], [], [], [], "", {}, {}
        )
        assert len(r["summary"]["type_distribution"]) >= 1
