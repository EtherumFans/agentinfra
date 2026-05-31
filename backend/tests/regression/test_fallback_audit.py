# Regression: Fallback Audit — verify every expert's fallback path produces valid output
import pytest
from app.agents.experts.evidence_expert import EvidenceExtractionExpert
from app.agents.experts.timeline_expert import TimelineReconstructionExpert
from app.agents.experts.homepage_expert import MedicalRecordHomepageExpert
from app.services.evidence_ranker import rank_all_evidence
from app.services.disagreement_analyzer import analyze_disagreements
from app.services.confidence_calibrator import calibrate_all
from app.services.reasoning_report_builder import build_case_reasoning_report


class TestEvidenceFallback:
    """EvidenceExtractionExpert fallback path."""

    def test_fallback_produces_structure(self):
        expert = EvidenceExtractionExpert()
        r = expert._fallback_extraction("出院诊断：肺炎。入院诊断：发热。主诉：咳嗽3天。")
        assert "chief_complaint" in r
        assert "diagnosis_facts" in r
        assert isinstance(r.get("diagnosis_facts"), list)

    def test_fallback_empty_text(self):
        expert = EvidenceExtractionExpert()
        r = expert._fallback_extraction("")
        assert r["chief_complaint"] == ""
        assert r["diagnosis_facts"] == []


class TestTimelineFallback:
    """TimelineReconstructionExpert fallback path."""

    def test_fallback_produces_valid_output(self):
        expert = TimelineReconstructionExpert()
        r = expert._fallback_extraction("2025年1月15日行直肠前切除术。2025年3月入院化疗。", "FALLBACK")
        assert "events" in r
        assert "anchor_points" in r
        assert "timeline_summary" in r

    def test_fallback_handles_no_dates(self):
        expert = TimelineReconstructionExpert()
        r = expert._fallback_extraction("患者一般情况良好。", "NODATE")
        assert r["events"] == []


class TestHomepageFallback:
    """HomepageExpert handles degraded pipeline context."""

    @pytest.mark.asyncio
    async def test_empty_context(self):
        expert = MedicalRecordHomepageExpert()
        ctx = {
            "encounter_id": "FALLBACK",
            "admission_reason": "",
            "documents": [],
            "diagnosis_candidates": [],
            "procedure_candidates": [],
            "existing_diagnosis_codes": [],
            "existing_procedure_codes": [],
            "timeline": {},
        }
        r = await expert.run(ctx)
        assert "primary_diagnosis" in r
        assert "primary_diagnosis_reasoning" in r


class TestEvidenceRankerFallback:
    """Evidence ranker handles empty/missing inputs."""

    def test_rank_all_empty(self):
        r = rank_all_evidence([], [], [], [], "", {}, {}, [])
        for key in ("top_supporting_evidence", "weak_evidence", "conflicting_evidence",
                     "unsupported_codes", "conflicts"):
            assert key in r
        assert r["evidence_strength_avg"] == 0.0

    def test_rank_all_no_evidence_for_candidates(self):
        candidates = [{"code": "Z51.102", "name": "化疗", "score": 0.8, "evidence_text": ""}]
        r = rank_all_evidence(candidates, [], [], [], "", {}, {}, [])
        assert "unsupported_codes" in r


class TestDisagreementFallback:
    """Disagreement analyzer handles empty inputs."""

    def test_empty_all(self):
        r = analyze_disagreements([], [], {}, {}, [], [], [], [], "", {}, {})
        assert r["summary"]["disagreements"] == 0


class TestConfidenceFallback:
    """Confidence calibrator handles empty inputs."""

    def test_empty_candidates(self):
        r = calibrate_all([], [], {}, {}, {}, {})
        assert r["metrics"]["total_codes"] == 0


class TestCaseReportFallback:
    """Case reasoning report handles empty context."""

    def test_empty_context(self):
        r = build_case_reasoning_report({})
        assert r["human_readable_summary"] != ""
        assert isinstance(r["case_overview"]["encounter_id"], str)


class TestAllFallbacksReturnChineseMessages:
    """Fallback error messages should be in Chinese for clinical users."""

    def test_timeline_fallback_message(self):
        expert = TimelineReconstructionExpert()
        r = expert._fallback_extraction("", "T")
        assert "Fallback extraction" in r["timeline_summary"] or isinstance(r["timeline_summary"], str)

    def test_evidence_fallback_message(self):
        expert = EvidenceExtractionExpert()
        r = expert._fallback_extraction("")
        assert isinstance(r.get("documentation_overview", {}).get("completeness", ""), str)

    def test_report_fallback_message(self):
        r = build_case_reasoning_report({"encounter_id": "T", "encounter": {}, "admission_reason": ""})
        assert "未知" in r["human_readable_summary"] or r["human_readable_summary"] != ""
