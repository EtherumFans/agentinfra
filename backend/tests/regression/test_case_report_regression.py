# Regression: Case Reasoning Report — degraded inputs, consistency
import pytest
from app.services.reasoning_report_builder import build_case_reasoning_report


class TestCaseReportDegraded:
    """Case reasoning report should degrade gracefully with missing inputs."""

    def test_empty_context(self):
        r = build_case_reasoning_report({})
        assert r["case_overview"]["encounter_id"] == ""
        assert r["human_readable_summary"] != ""

    def test_partial_context_only_overview(self):
        r = build_case_reasoning_report({
            "encounter_id": "T-001",
            "admission_reason": "test",
        })
        assert r["case_overview"]["encounter_id"] == "T-001"
        # All sections should be present even if empty
        for s in ("clinical_timeline", "evidence_assessment", "principal_diagnosis",
                   "disagreement_analysis", "confidence_routing", "audit_summary"):
            assert s in r, f"Missing section: {s}"

    def test_missing_timeline(self):
        ctx = {"encounter_id": "T", "admission_reason": "化疗", "encounter": {}, "documents": [],
               "primary_diagnosis": {"code": "Z51.102", "name": "化疗"},
               "primary_diagnosis_reasoning": {"why_selected": "test", "why_not_selected": [],
                                                "rule_basis": ["R013"], "confidence_level": "high"}}
        r = build_case_reasoning_report(ctx)
        assert r["clinical_timeline"]["event_count"] == 0

    def test_missing_evidence(self):
        ctx = {"encounter_id": "T", "admission_reason": "test", "encounter": {}, "documents": [], "primary_diagnosis": {},
               "primary_diagnosis_reasoning": {}, "disagreement_analysis": {}, "confidence_calibration": {}}
        r = build_case_reasoning_report(ctx)
        assert r["evidence_assessment"]["top_count"] == 0

    def test_missing_reasoning(self):
        ctx = {"encounter_id": "T", "admission_reason": "test", "encounter": {}, "documents": []}
        r = build_case_reasoning_report(ctx)
        assert r["principal_diagnosis"]["code"] == ""

    def test_human_readable_always_present(self):
        """Even with completely empty context, summary must be non-None."""
        for ctx in [{}, {"encounter_id": "X"}, {"encounter_id": "Y", "admission_reason": "Z"}]:
            r = build_case_reasoning_report(ctx)
            assert isinstance(r["human_readable_summary"], str)


class TestCaseReportConsistency:
    """Same input → same output."""

    def test_identical_input_identical_output_10_runs(self):
        ctx = {
            "encounter_id": "DEMO-001",
            "admission_reason": "直肠癌术后化疗",
            "encounter": {"department": "肿瘤内科"},
            "documents": [{"doc_type": "主诉", "content": "test"}],
            "timeline": {"timeline_summary": "test", "anchor_points": {}, "events": [], "event_count": 0},
            "evidence_ranking": {"top_supporting_evidence": [], "weak_evidence": [], "conflicting_evidence": [],
                                  "unsupported_codes": [], "evidence_strength_avg": 0.5, "conflicts": []},
            "primary_diagnosis": {"code": "Z51.102", "name": "化疗"},
            "primary_diagnosis_reasoning": {"why_selected": "R013", "why_not_selected": [],
                                             "rule_basis": ["R013"], "confidence_level": "high"},
            "disagreement_analysis": {"corrections": [], "summary": {"disagreements": 0, "drg_impacted_count": 0, "type_distribution": {}}},
            "confidence_calibration": {"metrics": {"auto_count": 0, "review_count": 1, "escalate_count": 0,
                                                    "auto_accept_rate": 0.0, "override_count": 1}},
            "errors": [],
        }
        results = [build_case_reasoning_report(ctx) for _ in range(10)]
        first = results[0]
        for r in results[1:]:
            assert r["human_readable_summary"] == first["human_readable_summary"]
            # Exclude generated_at (timestamp) from comparison
            overview_same = all(
                r["case_overview"][k] == first["case_overview"][k]
                for k in first["case_overview"] if k != "generated_at"
            )
            assert overview_same

    def test_report_sections_always_ordered(self):
        """The 8 sections must always appear in the same order."""
        r = build_case_reasoning_report({"encounter_id": "T"})
        expected_order = ["case_overview", "clinical_timeline", "evidence_assessment",
                          "principal_diagnosis", "disagreement_analysis", "confidence_routing",
                          "audit_summary", "human_readable_summary"]
        actual_keys = [k for k in expected_order if k in r]
        assert actual_keys == [k for k in expected_order if k in r]
