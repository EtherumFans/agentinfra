# Pilot Report Builder — unit tests
import pytest
from app.services.pilot_report_builder import (
    build_hospital_summary, build_unsupported_evidence_report,
    build_drg_sensitive_report, build_pilot_conclusion,
)


def _case(case_id, primary_diag_match=False, primary_diag_soft_match=False, main_proc_match=False,
          drg_match=False, unsupported_code_count=0, disagreement_count=0, drg_impacted=False,
          escalation_count=0, unsupported_codes=None, drg_sensitive_codes=None,
          evidence_strength_avg=0.5, routing=None):
    return {
        "case_id": case_id, "primary_diag_match": primary_diag_match,
        "primary_diag_soft_match": primary_diag_soft_match, "main_proc_match": main_proc_match,
        "drg_match": drg_match, "unsupported_code_count": unsupported_code_count,
        "disagreement_count": disagreement_count, "drg_impacted": drg_impacted,
        "escalation_count": escalation_count,
        "unsupported_codes": unsupported_codes or [],
        "drg_sensitive_codes": drg_sensitive_codes or [],
        "evidence_strength_avg": evidence_strength_avg,
        "routing": routing or [],
    }


class TestHospitalSummary:
    def test_empty(self):
        text = build_hospital_summary([])
        assert "暂不可用" in text or "暂无" in text

    def test_basic_summary(self):
        results = [_case("T001", True, True, True)]
        text = build_hospital_summary(results)
        assert "T001" not in text  # Should be summary, not per-case
        assert "总体结果" in text or "一、" in text

    def test_with_unsupported(self):
        results = [_case("T001", unsupported_code_count=3, unsupported_codes=["C20"]),
                   _case("T002", True)]
        text = build_hospital_summary(results)
        assert "文书支撑不足" in text or "三、" in text

    def test_with_disagreement(self):
        results = [_case("T001", disagreement_count=2, drg_impacted=True)]
        text = build_hospital_summary(results)
        assert "不一致" in text or "四、" in text

    def test_management_language(self):
        results = [_case("T001", True, True, True)]
        text = build_hospital_summary(results)
        assert "AI" in text
        assert "试点" in text


class TestUnsupportedEvidenceReport:
    def test_returns_sorted_list(self):
        results = [_case("T001", unsupported_code_count=2, unsupported_codes=["A", "B"]),
                   _case("T002", unsupported_code_count=5, unsupported_codes=["C"])]
        report = build_unsupported_evidence_report(results)
        assert len(report) == 2
        assert report[0]["unsupported_count"] >= report[1]["unsupported_count"]

    def test_empty(self):
        report = build_unsupported_evidence_report([])
        assert report == []


class TestDRGSensitiveReport:
    def test_filters_drg_impacted(self):
        results = [_case("T001", drg_impacted=True, disagreement_count=1),
                   _case("T002", drg_impacted=False)]
        report = build_drg_sensitive_report(results)
        assert len(report) == 1
        assert report[0]["case_id"] == "T001"

    def test_empty(self):
        report = build_drg_sensitive_report([])
        assert report == []


class TestPilotConclusion:
    def test_basic(self):
        text = build_pilot_conclusion([_case("T001", True)])
        assert "评估" in text or "试点" in text

    def test_empty(self):
        text = build_pilot_conclusion([])
        assert "暂无" in text
