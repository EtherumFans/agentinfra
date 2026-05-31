# Inter-Rater Agreement — unit tests
import pytest
from app.services.inter_rater import (
    compute_inter_rater, compute_multi_rater_agreement,
    _cohen_kappa, _fleiss_kappa,
)


class TestCohenKappa:
    def test_perfect_agreement(self):
        k = _cohen_kappa(["A", "B", "C"], ["A", "B", "C"])
        assert k == 1.0

    def test_complete_disagreement(self):
        k = _cohen_kappa(["A", "B", "C"], ["B", "C", "A"])
        assert k < 0.0  # worse than chance

    def test_empty_lists(self):
        k = _cohen_kappa([], [])
        assert k == 0.0

    def test_single_item_agreement(self):
        k = _cohen_kappa(["Z51.102"], ["C20.x00"])
        assert k == 0.0  # single disagreement with 2 categories = chance-level


class TestFleissKappa:
    def test_perfect_agreement(self):
        data = {"R1": ["A", "B"], "R2": ["A", "B"], "R3": ["A", "B"]}
        k = _fleiss_kappa(data)
        assert k == 1.0

    def test_mixed_agreement(self):
        data = {"R1": ["A", "A", "B"], "R2": ["A", "B", "B"], "R3": ["A", "A", "B"]}
        k = _fleiss_kappa(data)
        assert 0.0 <= k <= 1.0

    def test_single_rater_returns_none(self):
        k = _fleiss_kappa({"R1": ["A", "B"]})
        assert k is None


class TestComputeInterRater:
    def test_returns_expected_structure(self):
        result = compute_inter_rater(
            ["Z51.102", "C20.x00", "M80.900"],
            ["Z51.102", "C20.x00", "M80.000"],
        )
        for key in ("percent_agreement", "cohens_kappa", "n_pairs", "per_code_agreement", "interpretation"):
            assert key in result

    def test_perfect_agreement_metrics(self):
        result = compute_inter_rater(
            ["Z51.102", "C20.x00", "M80.900"],
            ["Z51.102", "C20.x00", "M80.900"],
        )
        assert result["percent_agreement"] == 1.0
        assert result["cohens_kappa"] == 1.0
        assert result["interpretation"] == "几乎完全一致 (Almost Perfect)"

    def test_two_of_three_agreement(self):
        result = compute_inter_rater(
            ["Z51.102", "C20.x00", "M80.900"],
            ["Z51.102", "C20.x00", "E11.900"],
        )
        assert round(result["percent_agreement"], 2) == 0.67

    def test_empty_lists(self):
        result = compute_inter_rater([], [])
        assert result["n_pairs"] == 0

    def test_unequal_lengths_raises(self):
        with pytest.raises(ValueError):
            compute_inter_rater(["A"], ["A", "B"])


class TestMultiRater:
    def test_returns_pairwise_matrix(self):
        data = {
            "coder_a": ["Z51.102", "C20.x00", "M80.900"],
            "coder_b": ["Z51.102", "C20.x00", "M80.000"],
            "coder_c": ["Z51.102", "C20.x00", "M80.900"],
        }
        result = compute_multi_rater_agreement(data)
        assert result["n_raters"] == 3
        assert result["n_cases"] == 3
        assert "coder_a_vs_coder_b" in result["pairwise_kappa"]
        assert "coder_a_vs_coder_c" in result["pairwise_kappa"]
        assert "coder_b_vs_coder_c" in result["pairwise_kappa"]
        assert result["avg_cohens_kappa"] > 0.0

    def test_single_rater_error(self):
        result = compute_multi_rater_agreement({"r1": ["A", "B"]})
        assert "error" in result

    def test_unequal_cases_error(self):
        data = {"r1": ["A", "B"], "r2": ["A"]}
        result = compute_multi_rater_agreement(data)
        assert "error" in result

    def test_perfect_multi_rater(self):
        data = {
            "r1": ["Z51", "C20", "M80"],
            "r2": ["Z51", "C20", "M80"],
            "r3": ["Z51", "C20", "M80"],
        }
        result = compute_multi_rater_agreement(data)
        assert result["avg_cohens_kappa"] == 1.0
        assert result["fleiss_kappa"] == 1.0
