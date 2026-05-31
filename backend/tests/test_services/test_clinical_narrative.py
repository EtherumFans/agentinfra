# Clinical Narrative — unit tests
import pytest
from app.services.reasoning_report_builder import (
    _build_clinical_narrative, _build_evidence_story,
    _build_final_recommendation, build_case_reasoning_report,
)
from app.schemas.case_reasoning import (
    CaseOverview, TimelineSection, PrincipalDiagnosisSection,
    EvidenceSection, DisagreementSection, ConfidenceSection,
)


class TestClinicalNarrative:
    def test_basic_structure(self):
        case = CaseOverview(encounter_id="T", department="肿瘤内科", admission_reason="术后化疗")
        tl = TimelineSection(summary="化疗入院")
        pd = PrincipalDiagnosisSection(code="Z51.102", name="恶性肿瘤化学治疗", why_selected="入院目的为化疗，R013适用。", rule_basis=["R013", "R001"])
        text = _build_clinical_narrative({"timeline": {"events": []}}, case, tl, pd)
        assert "术后化疗" in text
        assert "Z51.102" in text
        assert "R013" in text

    def test_with_timeline_events(self):
        case = CaseOverview(encounter_id="T", department="骨科", admission_reason="腰痛")
        tl = TimelineSection(summary="")
        pd = PrincipalDiagnosisSection(code="M80.900", name="骨质疏松伴病理性骨折")
        timeline = {"events": [
            {"event_type": "symptom_onset", "relative_time": "4月前", "description": "腰痛"},
            {"event_type": "surgery", "timestamp": "2025-01-15", "description": "椎体成形术"},
        ]}
        text = _build_clinical_narrative({"timeline": timeline}, case, tl, pd)
        assert "腰痛" in text
        assert "椎体成形术" in text

    def test_minimal_context(self):
        case = CaseOverview()
        tl = TimelineSection()
        pd = PrincipalDiagnosisSection()
        text = _build_clinical_narrative({}, case, tl, pd)
        assert "未知" in text


class TestEvidenceStory:
    def test_with_strong_evidence(self):
        ranking = {
            "top_supporting_evidence": [
                {"source_document": "出院小结", "text": "出院诊断：直肠恶性肿瘤化疗"},
                {"source_document": "现病史", "text": "为行术后辅助化疗入院"},
            ],
            "weak_evidence": [],
            "conflicting_evidence": [],
            "unsupported_codes": [],
        }
        pd = PrincipalDiagnosisSection()
        text = _build_evidence_story(ranking, pd, {})
        assert "出院小结" in text
        assert "现病史" in text

    def test_with_unsupported(self):
        ranking = {
            "top_supporting_evidence": [],
            "weak_evidence": [],
            "conflicting_evidence": [],
            "unsupported_codes": [{"code": "C20.x00", "name": "直肠癌"}],
        }
        text = _build_evidence_story(ranking, PrincipalDiagnosisSection(), {})
        assert "证据不足" in text
        assert "C20.x00" in text

    def test_empty(self):
        text = _build_evidence_story({}, PrincipalDiagnosisSection(), {})
        assert "不可用" in text or "证据评估" in text


class TestFinalRecommendation:
    def test_confirm_recommendation(self):
        pd = PrincipalDiagnosisSection(confidence_level="high")
        ev = EvidenceSection(unsupported_code_count=0, conflicting_count=0)
        da = DisagreementSection(has_disagreement=False)
        cf = ConfidenceSection(auto_count=0, escalate_count=0)
        text = _build_final_recommendation(pd, ev, da, cf, {})
        assert "建议确认" in text

    def test_escalate_recommendation(self):
        pd = PrincipalDiagnosisSection(confidence_level="low")
        ev = EvidenceSection(unsupported_code_count=3, conflicting_count=2)
        da = DisagreementSection(has_disagreement=True, correction_count=2, drg_impacted_count=1)
        cf = ConfidenceSection(escalate_count=2)
        text = _build_final_recommendation(pd, ev, da, cf, {})
        assert "建议高级审核" in text
        assert "DRG" in text

    def test_review_recommendation(self):
        pd = PrincipalDiagnosisSection(confidence_level="medium")
        ev = EvidenceSection()
        da = DisagreementSection()
        cf = ConfidenceSection()
        text = _build_final_recommendation(pd, ev, da, cf, {})
        assert "建议人工复核" in text


class TestFullReportWithNarratives:
    def test_report_includes_narrative_fields(self):
        ctx = {
            "encounter_id": "T",
            "admission_reason": "术后化疗",
            "encounter": {"department": "肿瘤内科"},
            "documents": [{"doc_type": "主诉", "content": "为行术后辅助化疗入院"}],
            "timeline": {"timeline_summary": "化疗入院", "events": [], "anchor_points": {}, "event_count": 0},
            "evidence_ranking": {"top_supporting_evidence": [], "weak_evidence": [], "conflicting_evidence": [], "unsupported_codes": [], "evidence_strength_avg": 0.5, "conflicts": []},
            "primary_diagnosis": {"code": "Z51.102", "name": "化疗"},
            "primary_diagnosis_reasoning": {"why_selected": "R013", "why_not_selected": [], "rule_basis": ["R013"], "confidence_level": "high", "timeline_evidence": ""},
            "disagreement_analysis": {"corrections": [], "summary": {"disagreements": 0, "drg_impacted_count": 0, "type_distribution": {}}},
            "confidence_calibration": {"metrics": {"auto_count": 0, "review_count": 1, "escalate_count": 0, "auto_accept_rate": 0.0, "override_count": 1}},
            "errors": [],
        }
        report = build_case_reasoning_report(ctx)
        assert "clinical_narrative" in report
        assert "evidence_story" in report
        assert "final_recommendation" in report
        assert "术后化疗" in report["clinical_narrative"]
        assert "建议" in report["final_recommendation"]
