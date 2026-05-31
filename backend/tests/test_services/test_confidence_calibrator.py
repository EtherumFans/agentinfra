# Confidence Calibrator — unit tests
import pytest
from app.services.confidence_calibrator import (
    calibrate_confidence,
    calibrate_all,
    route_code,
    _is_unspecified,
    _clamp,
    RoutingTier,
    RISK_TIER_POLICY,
    INPUT_WEIGHTS,
)
from app.schemas.confidence import (
    CodingConfidence,
    RoutingDecision,
    CalibrationMetrics,
    ConfidenceCalibrationResult,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _diag(code, name, score=0.8, negation=False):
    return {"code": code, "name": name, "score": score, "negation": negation}

def _proc(code, name, score=0.8):
    return {"code": code, "name": name, "score": score}


# ── Clamp ────────────────────────────────────────────────────────────────────

class TestClamp:
    def test_within_range(self):
        assert _clamp(0.5) == 0.5

    def test_below_zero(self):
        assert _clamp(-0.3) == 0.0

    def test_above_one(self):
        assert _clamp(1.5) == 1.0


# ── Unspecified detection ────────────────────────────────────────────────────

class TestUnspecified:
    def test_unspecified_dot9(self):
        assert _is_unspecified("M80.900") is True

    def test_specific_code(self):
        assert _is_unspecified("M80.000") is False

    def test_empty(self):
        assert _is_unspecified("") is False


# ── Calibration ──────────────────────────────────────────────────────────────

class TestCalibrateConfidence:
    def test_returns_expected_structure(self):
        result = calibrate_confidence(
            "Z51.102", "恶性肿瘤化学治疗", 0.85,
            [_diag("Z51.102", "化疗")], [],
            "Z51.102", {}, {}, {},
        )
        for key in ("code", "code_type", "raw_score", "calibrated_score", "inputs", "calibration_rationale"):
            assert key in result, f"Missing {key}"

    def test_high_evidence_boosts_score(self):
        good_ev = {"top_supporting_evidence": [{"related_code": "Z51.102", "strength_score": 0.9}]}
        result = calibrate_confidence("Z51.102", "test", 0.75, [_diag("Z51.102", "test")], [], "Z51.102", good_ev, {}, {})
        # With high evidence (0.9*0.25=0.225) and specificity bonus (+0.05), base raw * 0.35
        # expected: 0.35*0.75 + 0.25*0.9 + 0.05 = 0.5375
        assert result["calibrated_score"] > 0.50

    def test_negation_penalizes(self):
        result = calibrate_confidence("X99", "test", 0.8, [_diag("X99", "test")], [], "", {}, {}, {}, negation=True)
        assert result["calibrated_score"] < 0.8

    def test_unspecified_flag(self):
        result = calibrate_confidence("M80.900", "未特指", 0.75, [_diag("M80.900", "未特指")], [], "", {}, {}, {})
        assert result["code_type"] == "unspecified_code"

    def test_score_in_0_1_range(self):
        result = calibrate_confidence("Z51.102", "test", 0.95, [_diag("Z51.102", "test")], [], "Z51.102", {}, {}, {})
        assert 0.0 <= result["calibrated_score"] <= 1.0

    def test_disagreement_penalty(self):
        da = {"corrections": [{"code_ai": "Z51.102", "code_correct": "C20.x00"}]}
        result = calibrate_confidence("Z51.102", "test", 0.85, [_diag("Z51.102", "test")], [], "Z51.102", {}, da, {})
        assert result["calibrated_score"] < 0.85


# ── Routing ──────────────────────────────────────────────────────────────────

class TestRouting:
    def test_high_score_auto(self):
        conf = {"code": "E11.401", "code_type": "secondary_diagnosis", "calibrated_score": 0.88}
        route = route_code(conf, [_diag("E11.401", "糖尿病肾病")], [], "Z51.102", {}, {})
        assert route["tier"] == "auto"

    def test_primary_diagnosis_review_minimum(self):
        conf = {"code": "Z51.102", "code_type": "primary_diagnosis", "calibrated_score": 0.92}
        route = route_code(conf, [_diag("Z51.102", "化疗")], [], "Z51.102", {}, {})
        assert route["tier"] in ("review", "escalate")

    def test_low_score_escalate(self):
        conf = {"code": "E11", "code_type": "secondary_diagnosis", "calibrated_score": 0.35}
        route = route_code(conf, [_diag("E11", "test")], [], "", {}, {})
        assert route["tier"] == "escalate"

    def test_unsupported_code_escalate(self):
        conf = {"code": "C20.x00", "code_type": "secondary_diagnosis", "calibrated_score": 0.65}
        ev = {"unsupported_codes": [{"code": "C20.x00"}]}
        route = route_code(conf, [_diag("C20.x00", "test")], [], "", ev, {})
        assert route["tier"] == "escalate"

    def test_override_reason_populated(self):
        conf = {"code": "Z51.102", "code_type": "primary_diagnosis", "calibrated_score": 0.92}
        route = route_code(conf, [_diag("Z51.102", "化疗")], [], "Z51.102", {}, {})
        if route["tier"] != "auto":
            assert route["override_reason"] != ""


# ── Full calibrate_all ───────────────────────────────────────────────────────

class TestCalibrateAll:
    def test_returns_expected_structure(self):
        result = calibrate_all(
            diagnosis_candidates=[_diag("Z51.102", "化疗", 0.88)],
            procedure_candidates=[_proc("99.2503", "静脉输注化疗", 0.82)],
            primary_diagnosis={"code": "Z51.102"},
            evidence_ranking={},
            disagreement_analysis={},
            primary_diag_reasoning={},
        )
        assert "coding_confidences" in result
        assert "routing_decisions" in result
        assert "metrics" in result

    def test_primary_never_auto(self):
        result = calibrate_all(
            diagnosis_candidates=[_diag("Z51.102", "化疗", 0.95)],
            procedure_candidates=[],
            primary_diagnosis={"code": "Z51.102"},
            evidence_ranking={},
            disagreement_analysis={},
            primary_diag_reasoning={},
        )
        for rd in result["routing_decisions"]:
            if rd["code"] == "Z51.102":
                assert rd["tier"] != "auto"

    def test_metrics_sum_to_total(self):
        result = calibrate_all(
            diagnosis_candidates=[_diag("Z51.102", "化疗", 0.9), _diag("C20.x00", "直肠癌", 0.4)],
            procedure_candidates=[],
            primary_diagnosis={"code": "Z51.102"},
            evidence_ranking={},
            disagreement_analysis={},
            primary_diag_reasoning={},
        )
        m = result["metrics"]
        assert m["auto_count"] + m["review_count"] + m["escalate_count"] == m["total_codes"]

    def test_empty_candidates(self):
        result = calibrate_all([], [], {}, {}, {}, {})
        assert result["metrics"]["total_codes"] == 0

    def test_with_gold_codes(self):
        result = calibrate_all(
            diagnosis_candidates=[_diag("Z51.102", "化疗", 0.9)],
            procedure_candidates=[],
            primary_diagnosis={},
            evidence_ranking={},
            disagreement_analysis={},
            primary_diag_reasoning={},
            gold_diagnosis_codes=["Z51.102"],
        )
        assert result["metrics"]["calibration_error_avg"] >= 0.0  # calibration error computed when gold available


# ── Schema roundtrip ─────────────────────────────────────────────────────────

class TestConfidenceSchemas:
    def test_routing_decision_roundtrip(self):
        rd = RoutingDecision(code="Z51.102", code_name="化疗", calibrated_score=0.85, tier=RoutingTier.REVIEW,
                             risk_factors=["primary_diagnosis"], override_reason="policy override", auto_eligible=True)
        data = rd.model_dump_json()
        rehydrated = RoutingDecision.model_validate_json(data)
        assert rehydrated.tier == RoutingTier.REVIEW
        assert rehydrated.auto_eligible is True

    def test_calibration_result_roundtrip(self):
        cr = ConfidenceCalibrationResult(
            coding_confidences=[CodingConfidence(code="Z51.102", calibrated_score=0.85)],
            routing_decisions=[RoutingDecision(code="Z51.102", calibrated_score=0.85, tier=RoutingTier.REVIEW)],
            metrics=CalibrationMetrics(total_codes=1, review_count=1),
        )
        data = cr.model_dump_json()
        rehydrated = ConfidenceCalibrationResult.model_validate_json(data)
        assert rehydrated.metrics.total_codes == 1


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM response varies between runs")
async def test_pipeline_includes_confidence_calibration(auth_client):
    """Full pipeline response should include confidence_calibration."""
    resp = await auth_client.post("/api/reviews", json={
        "encounter_id": "DEMO-001",
        "async_mode": False,
    })
    if resp.status_code == 404:
        pytest.skip("DEMO-001 not seeded")
    assert resp.status_code == 200
    data = resp.json()
    assert "confidence_calibration" in data, f"Missing confidence_calibration. Keys: {list(data.keys())}"
