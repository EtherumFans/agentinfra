# Regression: Confidence Calibration — determinism, edge cases, routing
import pytest
from app.services.confidence_calibrator import (
    calibrate_confidence, route_code, calibrate_all,
    RoutingTier, _clamp,
)


class TestConfidenceDeterminism:
    """Calibration must be deterministic — same input → same calibrated score."""

    def test_calibration_deterministic(self):
        results = []
        for _ in range(10):
            r = calibrate_confidence(
                "Z51.102", "恶性肿瘤化学治疗", 0.85,
                [{"code": "Z51.102", "name": "化疗", "score": 0.85, "negation": False}],
                [], "Z51.102", {}, {}, {}
            )
            results.append(r["calibrated_score"])
        assert all(s == results[0] for s in results)

    def test_routing_deterministic(self):
        conf = {"code": "Z51.102", "code_type": "primary_diagnosis", "calibrated_score": 0.92}
        results = [route_code(conf, [{"code": "Z51.102", "name": "化疗"}], [], "Z51.102", {}, {}) for _ in range(5)]
        assert all(r["tier"] == results[0]["tier"] for r in results)

    def test_full_calibration_deterministic(self):
        results = [calibrate_all(
            [{"code": "Z51.102", "name": "化疗", "score": 0.88, "negation": False}],
            [], {"code": "Z51.102"}, {}, {}, {}
        ) for _ in range(5)]
        assert all(r["metrics"]["auto_count"] == results[0]["metrics"]["auto_count"] for r in results)


class TestConfidenceEdgeCases:
    """Edge cases for calibration."""

    def test_empty_candidates(self):
        r = calibrate_all([], [], {}, {}, {}, {})
        assert r["metrics"]["total_codes"] == 0

    def test_negative_raw_score_clamped(self):
        r = calibrate_confidence("X", "y", -1.0, [], [], "", {}, {}, {})
        assert 0.0 <= r["calibrated_score"] <= 1.0

    def test_super_high_raw_score_clamped(self):
        r = calibrate_confidence("X", "y", 5.0, [], [], "", {}, {}, {})
        assert r["calibrated_score"] <= 1.0

    def test_unknown_code_type(self):
        conf = {"code": "X99", "code_type": "unknown_type", "calibrated_score": 0.5}
        route = route_code(conf, [], [], "", {}, {})
        assert route["tier"] in ("auto", "review", "escalate")

    def test_clamp_function(self):
        assert _clamp(-10) == 0.0
        assert _clamp(100) == 1.0
        assert _clamp(0.5) == 0.5


class TestConfidenceRouting:
    """Routing decisions are correct for all tiers."""

    def test_auto_routing_with_high_score(self):
        conf = {"code": "E11.401", "code_type": "secondary_diagnosis", "calibrated_score": 0.88}
        route = route_code(conf, [{"code": "E11.401", "name": "糖尿病"}], [], "Z51.102", {}, {})
        assert route["tier"] == "auto"

    def test_primary_never_auto(self):
        conf = {"code": "Z51.102", "code_type": "primary_diagnosis", "calibrated_score": 0.99}
        route = route_code(conf, [{"code": "Z51.102", "name": "化疗"}], [], "Z51.102", {}, {})
        assert route["tier"] != "auto"

    def test_escalate_low_score(self):
        conf = {"code": "X", "code_type": "secondary_diagnosis", "calibrated_score": 0.25}
        route = route_code(conf, [], [], "", {}, {})
        assert route["tier"] == "escalate"

    def test_unspecified_code_review(self):
        conf = {"code": "M80.900", "code_type": "unspecified_code", "calibrated_score": 0.88}
        route = route_code(conf, [{"code": "M80.900", "name": "未特指"}], [], "", {}, {})
        assert route["tier"] in ("review", "escalate")


class TestConfidenceDegraded:
    """Degraded input scenarios."""

    def test_all_missing_context(self):
        r = calibrate_confidence("X", "y", 0.5, [], [], "", {}, {}, {})
        assert 0.0 <= r["calibrated_score"] <= 1.0

    def test_primary_missing_from_candidates(self):
        conf = {"code": "Z51.102", "code_type": "primary_diagnosis", "calibrated_score": 0.9}
        route = route_code(conf, [], [], "Z51.102", {}, {})
        assert route["tier"] != "auto"
