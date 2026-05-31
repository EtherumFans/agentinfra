# Principal Diagnosis Reasoning — unit tests
import pytest
from app.agents.experts.homepage_expert import (
    MedicalRecordHomepageExpert,
    _has_chemotherapy_context,
    _has_dialysis_context,
    _has_spine_fracture_candidates,
    _match_rules_to_candidates,
    _compute_adjusted_score,
    _generate_why_selected,
    _generate_why_not_selected,
    _analyze_disagreement,
    _assess_confidence,
    _build_timeline_evidence,
)
from app.schemas.principal_diagnosis_reasoning import (
    PrincipalDiagnosisReasoning,
    WhyNotSelected,
    DisagreementAnalysis,
    ConfidenceEscalation,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_candidate(code, name, score=0.8, finding="", etiology="", certainty="confirmed", negation=False):
    return {"code": code, "name": name, "score": score,
            "finding": finding, "etiology": etiology,
            "certainty": certainty, "negation": negation, "evidence_text": f"Evidence for {code}"}


def _make_timeline(events=None, admission_date="2025-03-01", admission_reason="化疗"):
    return {
        "encounter_id": "T-001",
        "anchor_points": {"admission_date": admission_date},
        "events": events or [],
        "timeline_summary": "",
    }


# ── Rule matching tests ──────────────────────────────────────────────────────

class TestRuleMatching:
    def test_chemotherapy_context_detected(self):
        assert _has_chemotherapy_context("直肠癌术后化疗", [{"content": "为行辅助化疗入院"}])

    def test_chemotherapy_context_not_detected(self):
        assert not _has_chemotherapy_context("腰痛", [{"content": "腰椎间盘突出"}])

    def test_dialysis_context_detected(self):
        assert _has_dialysis_context([{"content": "患者需行血液透析治疗"}])

    def test_dialysis_context_not_detected(self):
        assert not _has_dialysis_context([{"content": "常规检查"}])

    def test_spine_fracture_candidates(self):
        assert _has_spine_fracture_candidates([
            _make_candidate("M80.900", "骨质疏松伴病理性骨折"),
        ])

    def test_spine_fracture_not_detected(self):
        assert not _has_spine_fracture_candidates([
            _make_candidate("Z51.102", "恶性肿瘤化疗"),
        ])

    def test_r013_matches_z51_in_chemo_context(self):
        candidates = [_make_candidate("Z51.102", "恶性肿瘤化疗"), _make_candidate("C20.x00", "直肠恶性肿瘤")]
        matches = _match_rules_to_candidates(candidates, "术后化疗", [], {})
        assert "R013" in matches.get("Z51.102", [])

    def test_r001_applies_to_all(self):
        candidates = [_make_candidate("C20.x00", "直肠恶性肿瘤")]
        matches = _match_rules_to_candidates(candidates, "", [], {})
        assert "R001" in matches.get("C20.x00", [])

    def test_r014_matches_n18_in_dialysis_context(self):
        candidates = [_make_candidate("N18.900x013", "慢性肾脏病5期")]
        matches = _match_rules_to_candidates(candidates, "", [{"content": "行血液透析"}], {})
        assert "R014" in matches.get("N18.900x013", [])

    def test_r002_for_etiology_candidates(self):
        candidates = [_make_candidate("M80.900", "骨质疏松伴病理性骨折", etiology="骨质疏松")]
        matches = _match_rules_to_candidates(candidates, "", [], {})
        assert "R002" in matches.get("M80.900", [])


# ── Adjusted score tests ─────────────────────────────────────────────────────

class TestAdjustedScore:
    def test_r013_bonus(self):
        base = _compute_adjusted_score(_make_candidate("Z51.102", "化疗", 0.7), ["R013", "R001"], {}, "")
        assert base > 0.7  # R013 adds 0.12

    def test_no_rules_baseline(self):
        score = _compute_adjusted_score(_make_candidate("X99.999", "test", 0.5), ["R001"], {}, "")
        assert score == 0.52  # R001 adds 0.02

    def test_suspected_penalty(self):
        c = _make_candidate("Z51.102", "化疗", 0.7, certainty="suspected")
        score = _compute_adjusted_score(c, ["R013"], {}, "")
        assert score < 0.82  # R013(+0.12) + suspected(-0.05) = 0.77

    def test_negation_penalty(self):
        c = _make_candidate("Z51.102", "化疗", 0.7, negation=True)
        score = _compute_adjusted_score(c, ["R013"], {}, "")
        assert score < 0.7  # R013(+0.12) + negation(-0.15) = 0.67

    def test_ruled_out_zeroed(self):
        c = _make_candidate("Z51.102", "化疗", 0.7, certainty="ruled_out")
        score = _compute_adjusted_score(c, ["R013"], {}, "")
        assert score == 0.0

    def test_capped_at_one(self):
        score = _compute_adjusted_score(_make_candidate("Z51.102", "化疗", 0.95), ["R013", "R001", "R002"], {}, "")
        assert score == 1.0


# ── Why-selected generation ──────────────────────────────────────────────────

class TestWhySelected:
    def test_r013_reasoning(self):
        c = _make_candidate("Z51.102", "恶性肿瘤化学治疗")
        text = _generate_why_selected(c, ["R013", "R001"], "", 0.82)
        assert "R013" in text
        assert "Z51" in text

    def test_r001_only_reasoning(self):
        c = _make_candidate("M80.900", "骨质疏松伴病理性骨折", finding="骨质疏松伴椎体骨折")
        text = _generate_why_selected(c, ["R001"], "", 0.75)
        assert "综合评分最高" in text

    def test_includes_finding(self):
        c = _make_candidate("C20.x00", "直肠恶性肿瘤", finding="直肠癌术后")
        text = _generate_why_selected(c, ["R001"], "", 0.6)
        assert "直肠癌术后" in text


# ── Why-not-selected generation ──────────────────────────────────────────────

class TestWhyNotSelected:
    def test_returns_reasons_for_others(self):
        selected = "Z51.102"
        others = [_make_candidate("C20.x00", "直肠恶性肿瘤", 0.75), _make_candidate("E11.900", "糖尿病", 0.6)]
        rule_matches = {}
        reasons = _generate_why_not_selected(selected, others, rule_matches)
        assert len(reasons) >= 1
        assert reasons[0]["code"] == "C20.x00"

    def test_unspecific_code_flag(self):
        selected = "M80.000"
        others = [_make_candidate("M80.900", "未特指骨质疏松伴病理性骨折", 0.7)]
        reasons = _generate_why_not_selected(selected, others, {})
        assert any(".9" in r["reason"] for r in reasons)

    def test_caps_at_three(self):
        selected = "A"
        others = [_make_candidate(f"X{i}", f"test{i}", 0.5) for i in range(5)]
        reasons = _generate_why_not_selected(selected, others, {})
        assert len(reasons) <= 3


# ── Disagreement analysis ────────────────────────────────────────────────────

class TestDisagreementAnalysis:
    def test_no_disagreement_same_code(self):
        primary = _make_candidate("Z51.102", "化疗")
        existing = [{"code": "Z51.102", "name": "化疗"}]
        result = _analyze_disagreement(primary, existing, [primary], {"Z51.102": ["R013"]})
        assert result["has_disagreement"] is False

    def test_no_disagreement_empty_existing(self):
        primary = _make_candidate("Z51.102", "化疗")
        result = _analyze_disagreement(primary, [], [primary], {})
        assert result["has_disagreement"] is False

    def test_disagreement_detected(self):
        primary = _make_candidate("Z51.102", "化疗")
        existing = [{"code": "C20.x00", "name": "直肠癌"}]
        result = _analyze_disagreement(primary, existing, [primary], {"Z51.102": ["R013", "R001"]})
        assert result["has_disagreement"] is True
        assert result["ai_code"] == "Z51.102"
        assert result["existing_code"] == "C20.x00"
        assert "R013" in str(result["rule_basis"])


# ── Confidence assessment ────────────────────────────────────────────────────

class TestConfidenceAssessment:
    def test_high_confidence_clear_margin(self):
        primary = _make_candidate("Z51.102", "化疗", 0.9)
        sorted_cands = [primary, _make_candidate("C20.x00", "直肠癌", 0.6)]
        level, rationale, escalation = _assess_confidence(primary, sorted_cands, {"has_disagreement": False})
        assert level == "high"

    def test_low_confidence_low_score(self):
        primary = _make_candidate("Z51.102", "化疗", 0.35)
        level, rationale, escalation = _assess_confidence(primary, [primary], {"has_disagreement": False})
        assert level == "low"
        assert escalation["escalated"] is True
        assert escalation["trigger"] == "evidence_conflict"

    def test_low_confidence_close_scores(self):
        primary = _make_candidate("Z51.102", "化疗", 0.75)
        sorted_cands = [primary, _make_candidate("C20.x00", "直肠癌", 0.72)]
        level, _, escalation = _assess_confidence(primary, sorted_cands, {"has_disagreement": False})
        assert level == "low"
        assert escalation["trigger"] == "score_gap"

    def test_low_confidence_disagreement(self):
        primary = _make_candidate("Z51.102", "化疗", 0.8)
        level, _, escalation = _assess_confidence(primary, [primary], {"has_disagreement": True})
        assert level == "low"
        assert escalation["trigger"] == "evidence_conflict"

    def test_medium_default(self):
        primary = _make_candidate("Z51.102", "化疗", 0.7)
        sorted_cands = [primary, _make_candidate("C20.x00", "直肠癌", 0.55)]
        level, _, _ = _assess_confidence(primary, sorted_cands, {"has_disagreement": False})
        assert level == "medium"


# ── Timeline evidence ────────────────────────────────────────────────────────

class TestTimelineEvidence:
    def test_available(self):
        tl = _make_timeline(admission_date="2025-03-01")
        text = _build_timeline_evidence(tl, "术后化疗")
        assert "2025-03-01" in text
        assert "术后化疗" in text

    def test_unavailable(self):
        text = _build_timeline_evidence({}, "")
        assert "不可用" in text

    def test_with_events(self):
        tl = {
            "events": [
                {"event_type": "surgery", "relative_time": "2月前", "description": "直肠前切除术"},
                {"event_type": "chemotherapy", "relative_time": "1月前", "description": "第1周期化疗"},
            ],
            "anchor_points": {},
        }
        text = _build_timeline_evidence(tl, "")
        assert "直肠前切除术" in text
        assert "化疗" in text


# ── Schema roundtrip ─────────────────────────────────────────────────────────

class TestReasoningSchema:
    def test_full_roundtrip(self):
        reasoning = PrincipalDiagnosisReasoning(
            why_selected="选择Z51.102为主要诊断。本次入院目的为化疗，R013规则适用。",
            why_not_selected=[WhyNotSelected(code="C20.x00", name="直肠恶性肿瘤", reason="入院目的非肿瘤根治手术", rule_reference="R013")],
            rule_basis=["R013", "R001"],
            timeline_evidence="入院日期: 2025-03-01\n入院原因: 术后化疗",
            confidence_level="high",
            confidence_rationale="与第二名分差大",
            disagreement_analysis=DisagreementAnalysis(has_disagreement=False),
            confidence_escalation=ConfidenceEscalation(escalated=False),
        )
        json_str = reasoning.model_dump_json()
        rehydrated = PrincipalDiagnosisReasoning.model_validate_json(json_str)
        assert rehydrated.why_selected == reasoning.why_selected
        assert rehydrated.confidence_level == "high"
        assert len(rehydrated.why_not_selected) == 1

    def test_disagreement_schema(self):
        da = DisagreementAnalysis(
            has_disagreement=True,
            existing_code="C20.x00",
            existing_name="直肠恶性肿瘤",
            ai_code="Z51.102",
            ai_name="恶性肿瘤化学治疗",
            analysis="AI推荐Z51.102，与现有C20.x00不一致。",
            recommendation="accept_ai",
            rule_basis=["R013"],
        )
        assert da.has_disagreement is True
        assert da.recommendation == "accept_ai"


# ── Full expert run ──────────────────────────────────────────────────────────

class TestHomepageExpertFullRun:
    @pytest.mark.asyncio
    async def test_chemo_case_produces_reasoning(self):
        """R013 should trigger for chemo admission."""
        expert = MedicalRecordHomepageExpert()
        context = {
            "encounter_id": "TEST-001",
            "admission_reason": "直肠癌术后化疗",
            "documents": [{"doc_type": "主诉", "content": "为行术后辅助化疗入院。", "title": "主诉"}],
            "diagnosis_candidates": [
                _make_candidate("Z51.102", "恶性肿瘤化学治疗", 0.88, finding="术后化疗"),
                _make_candidate("C20.x00", "直肠恶性肿瘤", 0.60, finding="直肠癌"),
            ],
            "procedure_candidates": [],
            "existing_diagnosis_codes": [],
            "existing_procedure_codes": [],
            "timeline": _make_timeline(admission_reason="术后化疗"),
        }
        result = await expert.run(context)
        assert result["primary_diagnosis"]["code"] == "Z51.102"
        reasoning = result["primary_diagnosis_reasoning"]
        assert reasoning is not None
        assert "R013" in reasoning["rule_basis"]
        assert reasoning["confidence_level"] in ("high", "medium")

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="LLM response varies between runs — DeepSeek may not always emit R001")
    async def test_no_chemo_context_r001_only(self):
        """Without chemo context, score-based ranking with R001 only."""
        expert = MedicalRecordHomepageExpert()
        context = {
            "encounter_id": "TEST-002",
            "admission_reason": "腰痛",
            "documents": [{"doc_type": "主诉", "content": "腰痛4月余。", "title": "主诉"}],
            "diagnosis_candidates": [
                _make_candidate("M80.900", "骨质疏松伴病理性骨折", 0.85, finding="骨质疏松伴骨折"),
                _make_candidate("S32.000", "腰椎压缩骨折", 0.70, finding="椎体骨折"),
            ],
            "procedure_candidates": [],
            "existing_diagnosis_codes": [],
            "existing_procedure_codes": [],
            "timeline": _make_timeline(),
        }
        result = await expert.run(context)
        assert result["primary_diagnosis"]["code"] == "M80.900"
        reasoning = result["primary_diagnosis_reasoning"]
        assert reasoning is not None
        assert reasoning.get("rule_basis") is not None
        assert len(str(reasoning["rule_basis"])) > 0

    @pytest.mark.asyncio
    async def test_produces_why_not_selected(self):
        expert = MedicalRecordHomepageExpert()
        context = {
            "encounter_id": "TEST-003",
            "admission_reason": "术后化疗",
            "documents": [],
            "diagnosis_candidates": [
                _make_candidate("Z51.102", "恶性肿瘤化学治疗", 0.85, finding="化疗"),
                _make_candidate("C20.x00", "直肠恶性肿瘤", 0.75, finding="直肠癌"),
                _make_candidate("M80.900", "骨质疏松", 0.30, finding="骨质疏松"),
            ],
            "procedure_candidates": [],
            "existing_diagnosis_codes": [],
            "existing_procedure_codes": [],
            "timeline": {},
        }
        result = await expert.run(context)
        reasoning = result["primary_diagnosis_reasoning"]
        assert len(reasoning["why_not_selected"]) >= 1

    @pytest.mark.asyncio
    async def test_disagreement_produces_escalation(self):
        expert = MedicalRecordHomepageExpert()
        context = {
            "encounter_id": "TEST-004",
            "admission_reason": "术后化疗",
            "documents": [],
            "diagnosis_candidates": [
                _make_candidate("Z51.102", "恶性肿瘤化学治疗", 0.85, finding="化疗"),
                _make_candidate("C20.x00", "直肠恶性肿瘤", 0.75, finding="直肠癌"),
            ],
            "procedure_candidates": [],
            "existing_diagnosis_codes": [{"code": "C20.x00", "name": "直肠恶性肿瘤"}],
            "existing_procedure_codes": [],
            "timeline": {},
        }
        result = await expert.run(context)
        reasoning = result["primary_diagnosis_reasoning"]
        assert reasoning["disagreement_analysis"]["has_disagreement"] is True
        assert reasoning["confidence_level"] == "low"
        assert reasoning["confidence_escalation"]["escalated"] is True

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_none(self):
        expert = MedicalRecordHomepageExpert()
        context = {
            "encounter_id": "EMPTY",
            "admission_reason": "",
            "documents": [],
            "diagnosis_candidates": [],
            "procedure_candidates": [],
            "existing_diagnosis_codes": [],
            "existing_procedure_codes": [],
            "timeline": {},
        }
        result = await expert.run(context)
        assert result["primary_diagnosis"] is None
        assert result["primary_diagnosis_reasoning"] is None


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM response varies between runs")
async def test_pipeline_includes_reasoning(auth_client):
    """Full pipeline response should include primary_diagnosis_reasoning."""
    resp = await auth_client.post("/api/reviews", json={
        "encounter_id": "DEMO-001",
        "async_mode": False,
    })
    if resp.status_code == 404:
        pytest.skip("DEMO-001 not seeded — run 'python -m app.seed' first")
    assert resp.status_code == 200
    data = resp.json()
    # Primary diagnosis should have reasoning
    pd = data.get("primary_diagnosis", {})
    assert "reasoning" in pd, f"Reasoning key missing from primary_diagnosis. Keys: {list(pd.keys())}"
    if pd.get("reasoning"):
        reasoning = pd["reasoning"]
        assert "why_selected" in reasoning
        assert "rule_basis" in reasoning
        assert "confidence_level" in reasoning
