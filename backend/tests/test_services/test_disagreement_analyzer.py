# Disagreement Analyzer — unit tests
import pytest
from app.services.disagreement_analyzer import (
    analyze_disagreements,
    _classify_disagreement_type,
    _is_specificity_diff,
    _check_drg_sensitivity,
    DisagreementType,
)
from app.schemas.disagreement_reasoning import (
    CorrectionRecord,
    DisagreementSummary,
    DisagreementAnalysisResult,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _diag(code, name, evidence_text=""):
    return {"code": code, "name": name, "score": 0.8, "evidence_text": evidence_text}

def _proc(code, name, evidence_text=""):
    return {"code": code, "name": name, "score": 0.8, "evidence_text": evidence_text}


# ── Specificity Diff ─────────────────────────────────────────────────────────

class TestSpecificityDiff:
    def test_same_category_diff_specificity(self):
        assert _is_specificity_diff("M80.900", "M80.000") is True

    def test_same_specific_code(self):
        assert _is_specificity_diff("M80.000", "M80.000") is False

    def test_different_category(self):
        assert _is_specificity_diff("M80.900", "Z51.102") is False

    def test_empty_codes(self):
        assert _is_specificity_diff("", "Z51") is False


# ── Disagreement Classification ──────────────────────────────────────────────

class TestDisagreementClassification:
    def test_specificity_type(self):
        d_type, _ = _classify_disagreement_type(
            "M80.900", "骨质疏松", "M80.000", "骨质疏松伴病理性骨折",
            {"unsupported_codes": [], "conflicts": []}, "M80.900", "", {}
        )
        assert d_type == DisagreementType.CODE_SPECIFICITY

    def test_unsupported_triggers_documentation_gap(self):
        d_type, _ = _classify_disagreement_type(
            "C20.x00", "直肠癌", "Z51.102", "化疗",
            {"unsupported_codes": [{"code": "C20.x00"}], "conflicts": []}, "C20.x00", "", {}
        )
        assert d_type == DisagreementType.DOCUMENTATION_GAP

    def test_primary_vs_secondary(self):
        d_type, _ = _classify_disagreement_type(
            "Z51.102", "化疗", "C20.x00", "直肠癌",
            {"unsupported_codes": [], "conflicts": []}, "Z51.102", "", {}
        )
        assert d_type == DisagreementType.PRIMARY_VS_SECONDARY

    def test_code_selection_fallback(self):
        d_type, _ = _classify_disagreement_type(
            "J15.200", "肺炎", "R91.x02", "肺部阴影",
            {"unsupported_codes": [], "conflicts": []}, "M80.900", "", {}
        )
        assert d_type == DisagreementType.CODE_SELECTION

    def test_rule_violation_ai_has_rules(self):
        d_type, _ = _classify_disagreement_type(
            "Z51.102", "化疗", "C20.x00", "直肠癌",
            {"unsupported_codes": [], "conflicts": []}, "Z51.102", "",
            {"Z51.102": ["R013", "R001"], "C20.x00": []}
        )
        assert d_type == DisagreementType.RULE_VIOLATION


# ── DRG Sensitivity ──────────────────────────────────────────────────────────

class TestDRGSensitivity:
    def test_no_drg_data(self):
        sensitive, _, _, _ = _check_drg_sensitivity("Z51.102", "C20.x00", {})
        assert sensitive is False

    def test_different_chapter_is_sensitive(self):
        sensitive, _, _, _ = _check_drg_sensitivity("Z51.102", "C20.x00", {"drg_risks": []})
        assert sensitive is True

    def test_same_chapter_not_sensitive(self):
        sensitive, _, _, _ = _check_drg_sensitivity("M80.900", "M80.000", {"drg_risks": []})
        assert sensitive is False


# ── Full Analysis ────────────────────────────────────────────────────────────

class TestAnalyzeDisagreements:
    def test_all_agree_no_corrections(self):
        result = analyze_disagreements(
            diagnosis_candidates=[_diag("Z51.102", "化疗")],
            procedure_candidates=[],
            primary_diagnosis={"code": "Z51.102", "name": "化疗"},
            evidence_ranking={"unsupported_codes": [], "conflicts": []},
            gold_diagnosis_codes=["Z51.102"],
            gold_procedure_codes=[],
            existing_diagnosis_codes=[],
            existing_procedure_codes=[],
            admission_reason="术后化疗",
            drg_impact={},
            rule_matches={"Z51.102": ["R013"]},
        )
        assert result["summary"]["disagreements"] == 0

    def test_disagreement_detected(self):
        result = analyze_disagreements(
            diagnosis_candidates=[_diag("C20.x00", "直肠癌")],
            procedure_candidates=[],
            primary_diagnosis={"code": "C20.x00", "name": "直肠癌"},
            evidence_ranking={"unsupported_codes": [], "conflicts": []},
            gold_diagnosis_codes=["Z51.102"],
            gold_procedure_codes=[],
            existing_diagnosis_codes=[],
            existing_procedure_codes=[],
            admission_reason="术后化疗",
            drg_impact={},
            rule_matches={},
        )
        assert result["summary"]["disagreements"] >= 1

    def test_missing_gold_code_detected(self):
        result = analyze_disagreements(
            diagnosis_candidates=[_diag("Z51.102", "化疗")],
            procedure_candidates=[],
            primary_diagnosis={"code": "Z51.102", "name": "化疗"},
            evidence_ranking={"unsupported_codes": [], "conflicts": []},
            gold_diagnosis_codes=["Z51.102", "C50.900"],
            gold_procedure_codes=[],
            existing_diagnosis_codes=[],
            existing_procedure_codes=[],
            admission_reason="术后化疗",
            drg_impact={},
            rule_matches={},
        )
        # One missing code should be detected
        assert result["summary"]["disagreements"] >= 1

    def test_returns_expected_structure(self):
        result = analyze_disagreements([], [], {}, {}, [], [], [], [], "", {}, {})
        assert "corrections" in result
        assert "summary" in result
        s = result["summary"]
        for key in ("total_codes", "agreements", "disagreements", "disagreement_rate",
                     "drg_impacted_count", "type_distribution", "learnable_corrections"):
            assert key in s, f"Missing key: {key}"

    def test_type_distribution_populated(self):
        result = analyze_disagreements(
            diagnosis_candidates=[_diag("M80.900", "骨质疏松")],
            procedure_candidates=[],
            primary_diagnosis={"code": "M80.900"},
            evidence_ranking={"unsupported_codes": [], "conflicts": []},
            gold_diagnosis_codes=["M80.000"],
            gold_procedure_codes=[],
            existing_diagnosis_codes=[],
            existing_procedure_codes=[],
            admission_reason="",
            drg_impact={},
            rule_matches={},
        )
        td = result["summary"]["type_distribution"]
        assert len(td) >= 1


# ── Schema Roundtrip ─────────────────────────────────────────────────────────

class TestDisagreementSchemas:
    def test_correction_record_roundtrip(self):
        cr = CorrectionRecord(
            case_id="DEMO-001",
            code_ai="M80.900",
            code_ai_name="未特指骨质疏松",
            code_correct="M80.000",
            code_correct_name="绝经后骨质疏松伴病理性骨折",
            disagreement_type=DisagreementType.CODE_SPECIFICITY,
            type_rationale="编码特异性差异",
            drg_impacted=False,
            rule_reference=["R003"],
            evidence_support="骨密度检查确认",
        )
        data = cr.model_dump_json()
        rehydrated = CorrectionRecord.model_validate_json(data)
        assert rehydrated.code_ai == "M80.900"
        assert rehydrated.disagreement_type == DisagreementType.CODE_SPECIFICITY

    def test_disagreement_result_roundtrip(self):
        result = DisagreementAnalysisResult(
            corrections=[
                CorrectionRecord(
                    case_id="T",
                    code_ai="M80.900",
                    code_correct="M80.000",
                    disagreement_type=DisagreementType.CODE_SPECIFICITY,
                )
            ],
            summary=DisagreementSummary(total_codes=1, disagreements=1, disagreement_rate=1.0),
        )
        data = result.model_dump_json()
        rehydrated = DisagreementAnalysisResult.model_validate_json(data)
        assert rehydrated.summary.disagreements == 1


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM response varies between runs")
async def test_pipeline_includes_disagreement_analysis(auth_client):
    """Full pipeline response should include disagreement_analysis."""
    resp = await auth_client.post("/api/reviews", json={
        "encounter_id": "DEMO-001",
        "async_mode": False,
    })
    if resp.status_code == 404:
        pytest.skip("DEMO-001 not seeded — run 'python -m app.seed' first")
    assert resp.status_code == 200
    data = resp.json()
    assert "disagreement_analysis" in data, f"Missing disagreement_analysis. Keys: {list(data.keys())}"
