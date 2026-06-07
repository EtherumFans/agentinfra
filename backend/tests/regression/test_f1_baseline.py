"""Regression test for e2e F1 metric — locks in honest measurement.

The old metric was set-based over primary codes only; secondary dx misses
were invisible. This test pins:
  - _norm_code subdivision tolerance (I50.900 ≡ I50.9 ≡ I50.x00)
  - per-case micro-F1 (counts both primary and secondary)
  - repair_success requires hitting gold (not just changing the code)
"""
import pytest

from scripts.e2e_runtime_validation import _norm_code, _compute_case_f1


class TestNormCode:
    def test_strip_trailing_zeros_in_subdivision(self):
        assert _norm_code("I50.900") == _norm_code("I50.9")

    def test_strip_x_placeholder(self):
        assert _norm_code("C20.x00") == _norm_code("C20")

    def test_keep_digits_after_x(self):
        # Z45.800x012: x stripped, digits preserved, dot kept
        assert _norm_code("Z45.800x012") == "Z45.800012"

    def test_strip_trailing_x(self):
        assert _norm_code("M80.900x") == "M80.9"

    def test_case_insensitive(self):
        assert _norm_code("i21.0") == _norm_code("I21.0")

    def test_whitespace_trim(self):
        # I21.0 normalizes to I21 (subdivision .0 = "no subdivision")
        assert _norm_code("  I21.0  ") == "I21"

    def test_subdivision_dot_zero_strips(self):
        # I21.0, I21.00, I21.000 all → I21 (category-level)
        assert _norm_code("I21.0") == "I21"
        assert _norm_code("I21.00") == "I21"
        assert _norm_code("I21.000") == "I21"

    def test_empty_returns_empty(self):
        assert _norm_code("") == ""
        assert _norm_code(None) == ""

    def test_no_dot(self):
        assert _norm_code("I50") == "I50"


class TestPerCaseF1:
    def test_perfect_match(self):
        # Same case after normalization: I50.900 and I50.9 both → I50.9
        f1 = _compute_case_f1({"I50.900", "I10"}, {"I50.9", "I10"})
        assert f1 == 1.0

    def test_partial_credit(self):
        # Gold: 3 codes; predicted: 2 of them
        # tp=2, fp=0, fn=1
        # p=1.0, r=2/3 → f1 = 0.8
        f1 = _compute_case_f1({"I50.900", "I10", "E11.4"}, {"I50.9", "I10"})
        assert abs(f1 - 0.8) < 1e-6

    def test_extra_codes_reduce_precision(self):
        # Gold: 1 code; predicted: 1 correct + 1 extra
        # tp=1, fp=1, fn=0 → p=0.5, r=1.0 → f1 = 2/3
        f1 = _compute_case_f1({"I50.9"}, {"I50.9", "E11.4"})
        assert abs(f1 - 2/3) < 1e-6

    def test_empty_both_sides(self):
        # No gold, no predicted → 1.0 (vacuously satisfied)
        assert _compute_case_f1(set(), set()) == 1.0

    def test_empty_predicted(self):
        # Has gold, predicted nothing → 0
        assert _compute_case_f1({"I50.9"}, set()) == 0.0

    def test_empty_gold(self):
        # No gold, predicted something → 0 (over-prediction)
        assert _compute_case_f1(set(), {"I50.9"}) == 0.0

    def test_secondary_miss_moves_f1(self):
        """The headline bug: secondary dx miss used to be invisible."""
        gold = {"I50.9", "I10", "E11.4", "N18.9"}
        pred_correct_primary = {"I50.9", "I10", "E11.4"}  # missed N18.9
        pred_with_secondary = {"I50.9", "I10", "E11.4", "N18.9"}
        # 3/4 correct is f1 = 2*0.75*1.0/(0.75+1.0) = 0.857
        f1 = _compute_case_f1(gold, pred_correct_primary)
        assert 0.85 < f1 < 0.86
        # Full match = 1.0
        assert _compute_case_f1(gold, pred_with_secondary) == 1.0


class TestRepairSuccessSemantics:
    """The repair_success flag is computed inside run_evaluation, but the
    underlying logic (new code hits gold AND old did not) is what we want
    to lock in. We re-test the condition directly here."""

    def test_repair_only_counts_when_new_hits_gold(self):
        # Old: wrong; New: different wrong; Gold: I50.9
        # Should NOT count as repair success
        old_codes = {"I48.0"}
        new_codes = {"I48.1"}
        gold_norm = {"I50.9"}
        repair_success = bool(new_codes & gold_norm) and not (old_codes & gold_norm)
        assert repair_success is False

    def test_repair_when_old_was_already_correct(self):
        # Old was already right; "repair" didn't fix anything
        old_codes = {"I50.9"}
        new_codes = {"I50.9"}
        gold_norm = {"I50.9"}
        repair_success = bool(new_codes & gold_norm) and not (old_codes & gold_norm)
        assert repair_success is False

    def test_repair_correctly_flips_wrong_to_right(self):
        # Old: I48.0 (wrong); New: I50.9 (matches gold)
        old_codes = {"I48.0"}
        new_codes = {"I50.9"}
        gold_norm = {"I50.9"}
        repair_success = bool(new_codes & gold_norm) and not (old_codes & gold_norm)
        assert repair_success is True
