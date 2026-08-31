"""Regression tests for raw vs safety-conditioned CDI parity metrics."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "corti_parity"
    / "track_h"
    / "04_normalize_and_compare.py"
)
SPEC = importlib.util.spec_from_file_location("h34_normalizer", MODULE_PATH)
assert SPEC and SPEC.loader
NORMALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZER)


def test_conditioned_metrics_do_not_hide_raw_product_gap() -> None:
    rows = [
        {
            "abs_query_count_delta": 0,
            "corti_in_range": True,
            "icoder_in_range": True,
        },
        {
            "abs_query_count_delta": 3,
            "corti_in_range": False,
            "icoder_in_range": True,
        },
    ]

    metrics = NORMALIZER._agreement_metrics(rows)

    assert metrics["raw"] == {
        "cases": 2,
        "avg_abs_query_count_delta": 1.5,
        "agreement_rate_delta_le_1": 0.5,
    }
    assert metrics["when_corti_in_expected_range"] == {
        "cases": 1,
        "avg_abs_query_count_delta": 0.0,
        "agreement_rate_delta_le_1": 1.0,
    }
    assert metrics["corti_range_conformance_rate"] == 0.5
    assert metrics["icoder_range_conformance_rate"] == 1.0


def test_divergence_class_distinguishes_safety_from_range_defect() -> None:
    base = {
        "expected_query_min": 1,
        "expected_query_max": 2,
        "corti_query_count": 3,
        "icoder_query_count": 1,
        "query_count_delta": -2,
        "corti_in_range": False,
        "icoder_in_range": True,
    }
    assert NORMALIZER._classify_query_count_divergence(base) == (
        "safety_preserving_divergence_corti_out_of_range"
    )

    under = dict(base, icoder_query_count=0, icoder_in_range=False)
    assert NORMALIZER._classify_query_count_divergence(under) == (
        "icoder_under_expected_range_defect"
    )

    both_safe = dict(
        base,
        corti_query_count=2,
        corti_in_range=True,
        query_count_delta=-1,
    )
    assert NORMALIZER._classify_query_count_divergence(both_safe) == (
        "product_behavior_divergence_within_expected_range"
    )
