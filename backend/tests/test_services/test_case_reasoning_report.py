# Case Reasoning Report — unit tests
import pytest
from app.services.reasoning_report_builder import build_case_reasoning_report
from app.schemas.case_reasoning import CaseReasoningReport


# ── helpers ──────────────────────────────────────────────────────────────────

def _base_context():
    return {
        "encounter_id": "DEMO-001",
        "admission_reason": "直肠癌术后化疗",
        "encounter": {"department": "肿瘤内科"},
        "documents": [{"doc_type": "主诉", "content": "test"}],
        "timeline": {
            "timeline_summary": "直肠癌术后化疗入院",
            "anchor_points": {"admission_date": "2025-03-01"},
            "events": [{"description": "直肠前切除术"}, {"description": "第1周期化疗"}],
            "event_count": 2,
            "unresolved_count": 0,
        },
        "evidence_ranking": {
            "top_supporting_evidence": [{"strength_score": 0.85}],
            "weak_evidence": [],
            "conflicting_evidence": [],
            "unsupported_codes": [],
            "evidence_strength_avg": 0.75,
            "conflicts": [],
        },
        "primary_diagnosis": {"code": "Z51.102", "name": "恶性肿瘤化学治疗"},
        "primary_diagnosis_reasoning": {
            "why_selected": "本次入院目的为化疗，R013规则适用。",
            "why_not_selected": [{"code": "C20.x00", "reason": "入院目的非肿瘤根治手术"}],
            "rule_basis": ["R013", "R001"],
            "confidence_level": "high",
            "timeline_evidence": "入院日期: 2025-03-01",
        },
        "disagreement_analysis": {
            "corrections": [],
            "summary": {"disagreements": 0, "drg_impacted_count": 0, "type_distribution": {}},
        },
        "confidence_calibration": {
            "routing_decisions": [{"tier": "review", "code": "Z51.102"}],
            "metrics": {"auto_count": 0, "review_count": 1, "escalate_count": 0, "auto_accept_rate": 0.0, "override_count": 1},
        },
        "errors": [],
    }


# ── Tests ────────────────────────────────────────────────────────────────────

class TestCaseReasoningReport:
    def test_all_sections_present(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        for key in ("case_overview", "clinical_timeline", "evidence_assessment",
                     "principal_diagnosis", "disagreement_analysis", "confidence_routing",
                     "audit_summary", "human_readable_summary"):
            assert key in report, f"Missing section: {key}"

    def test_case_overview_filled(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        co = report["case_overview"]
        assert co["encounter_id"] == "DEMO-001"
        assert co["department"] == "肿瘤内科"
        assert co["admission_reason"] == "直肠癌术后化疗"
        assert co["doc_count"] == 1

    def test_timeline_section(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        tl = report["clinical_timeline"]
        assert tl["event_count"] == 2
        assert len(tl["key_events"]) >= 1
        assert tl["summary"] != ""

    def test_evidence_section(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        ev = report["evidence_assessment"]
        assert ev["top_count"] == 1
        assert ev["strength_avg"] == 0.75

    def test_principal_diagnosis_section(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        pd = report["principal_diagnosis"]
        assert pd["code"] == "Z51.102"
        assert pd["confidence_level"] == "high"
        assert "R013" in pd["rule_basis"]

    def test_disagreement_section(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        da = report["disagreement_analysis"]
        assert da["has_disagreement"] is False

    def test_confidence_section(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        cr = report["confidence_routing"]
        assert cr["review_count"] == 1
        assert cr["auto_count"] == 0

    def test_human_readable_summary(self):
        ctx = _base_context()
        report = build_case_reasoning_report(ctx)
        summary = report["human_readable_summary"]
        assert "肿瘤内科" in summary
        assert "Z51.102" in summary
        assert len(summary) > 50

    def test_empty_context_does_not_crash(self):
        report = build_case_reasoning_report({})
        assert report["case_overview"]["encounter_id"] == ""

    def test_with_disagreement(self):
        ctx = _base_context()
        ctx["disagreement_analysis"] = {
            "corrections": [
                {"code_ai": "C20.x00", "code_correct": "Z51.102", "disagreement_type": "code_selection", "drg_impacted": True}
            ],
            "summary": {"disagreements": 1, "drg_impacted_count": 1, "type_distribution": {"code_selection": 1}},
        }
        report = build_case_reasoning_report(ctx)
        da = report["disagreement_analysis"]
        assert da["has_disagreement"] is True
        assert da["drg_impacted_count"] == 1

    def test_with_unsupported_codes(self):
        ctx = _base_context()
        ctx["evidence_ranking"]["unsupported_codes"] = [{"code": "X99", "name": "test"}]
        report = build_case_reasoning_report(ctx)
        assert report["evidence_assessment"]["unsupported_code_count"] == 1


class TestSchemaRoundtrip:
    def test_full_report_roundtrip(self):
        from app.schemas.case_reasoning import CaseOverview, CaseReasoningReport
        report = CaseReasoningReport(
            case_overview=CaseOverview(encounter_id="DEMO-001", department="肿瘤内科"),
            human_readable_summary="测试摘要。",
        )
        data = report.model_dump_json()
        rehydrated = CaseReasoningReport.model_validate_json(data)
        assert rehydrated.case_overview.encounter_id == "DEMO-001"
        assert rehydrated.human_readable_summary == "测试摘要。"


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM response varies between runs")
async def test_pipeline_includes_case_reasoning_report(auth_client):
    resp = await auth_client.post("/api/reviews", json={
        "encounter_id": "DEMO-001",
        "async_mode": False,
    })
    if resp.status_code == 404:
        pytest.skip("DEMO-001 not seeded")
    assert resp.status_code == 200
    data = resp.json()
    assert "case_reasoning_report" in data, f"Missing. Keys: {list(data.keys())}"
    report = data["case_reasoning_report"]
    assert "case_overview" in report
    assert "human_readable_summary" in report
