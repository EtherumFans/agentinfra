# Evidence Ranker — unit tests
import pytest
from app.services.evidence_ranker import (
    rank_evidence_for_code,
    rank_all_evidence,
    detect_conflicts,
    detect_unsupported_codes,
    _score_source_document,
    _score_admission_consistency,
    _score_negation_uncertainty,
    _check_history_background,
    _assign_category,
    EvidenceCategory,
    ConflictType,
)
from app.schemas.evidence_ranking import (
    EvidenceRank,
    EvidenceRankingResult,
    ConflictResult,
    UnsupportedCodeResult,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_evidence(text, doc_type="现病史", certainty="confirmed", negation=False, code=""):
    return {
        "evidence_text": text, "text": text,
        "source_document": doc_type, "doc_type": doc_type,
        "certainty": certainty, "negation": negation,
        "related_code": code,
    }

def _make_candidate(code, name, score=0.8, evidence_text="", negation=False, certainty="confirmed"):
    return {"code": code, "name": name, "score": score, "evidence_text": evidence_text,
            "negation": negation, "certainty": certainty}

def _make_proc_candidate(code, name, score=0.8, evidence_text="", body_site=""):
    return {"code": code, "name": name, "score": score, "evidence_text": evidence_text, "body_site": body_site}


# ── Source document scoring ──────────────────────────────────────────────────

class TestSourceDocumentScoring:
    def test_discharge_highest(self):
        score, reason = _score_source_document("出院小结")
        assert score == 0.15

    def test_surgery_high(self):
        score, _ = _score_source_document("手术记录")
        assert score == 0.12

    def test_progress_note_medium(self):
        score, _ = _score_source_document("病程记录")
        assert score == 0.08

    def test_lab_report(self):
        score, _ = _score_source_document("检查报告")
        assert score == 0.06

    def test_history_penalty(self):
        score, _ = _score_source_document("既往史")
        assert score == -0.10

    def test_chief_complaint(self):
        score, _ = _score_source_document("主诉")
        assert score == 0.03

    def test_unknown(self):
        score, _ = _score_source_document("unknown_type")
        assert score == 0.0


# ── History/background detection ─────────────────────────────────────────────

class TestHistoryDetection:
    def test_n_years_ago(self):
        score, _ = _check_history_background("患者5年前因腰椎间盘突出行治疗", "")
        assert score == -0.10

    def test_n_months_ago(self):
        score, _ = _check_history_background("患者3月前无明显诱因出现症状", "")
        assert score == -0.10

    def test_current_complaint_no_penalty(self):
        score, _ = _check_history_background("患者本次因腹痛入院", "")
        assert score == 0.0


# ── Admission consistency ────────────────────────────────────────────────────

class TestAdmissionConsistency:
    def test_high_match(self):
        score, _ = _score_admission_consistency("为行术后辅助化疗入院", "术后化疗")
        assert score > 0

    def test_no_match(self):
        score, _ = _score_admission_consistency("腰痛4月余", "术后化疗")
        assert score == 0.0

    def test_empty_reason(self):
        score, _ = _score_admission_consistency("任意文本", "")
        assert score == 0.0


# ── Negation/uncertainty ─────────────────────────────────────────────────────

class TestNegationUncertainty:
    def test_negation_penalty(self):
        score, _ = _score_negation_uncertainty(True, "confirmed")
        assert score == -0.20

    def test_suspected_penalty(self):
        score, _ = _score_negation_uncertainty(False, "suspected")
        assert score == -0.05

    def test_ruled_out_severe(self):
        score, _ = _score_negation_uncertainty(False, "ruled_out")
        assert score == -0.30

    def test_confirmed_no_penalty(self):
        score, _ = _score_negation_uncertainty(False, "confirmed")
        assert score == 0.0


# ── Category assignment ──────────────────────────────────────────────────────

class TestCategoryAssignment:
    def test_high_score_direct(self):
        cat = _assign_category(0.7, False, False, "出院小结")
        assert cat == EvidenceCategory.DIRECT

    def test_negated_conflicting(self):
        cat = _assign_category(0.5, True, False, "现病史")
        assert cat == EvidenceCategory.CONFLICTING

    def test_mid_score_inferred(self):
        cat = _assign_category(0.4, False, False, "现病史")
        assert cat == EvidenceCategory.INFERRED

    def test_low_score_weak(self):
        cat = _assign_category(0.2, False, False, "既往史")
        assert cat == EvidenceCategory.WEAK

    def test_suspected_low_weak(self):
        cat = _assign_category(0.2, False, True, "既往史")
        assert cat == EvidenceCategory.WEAK


# ── Evidence ranking for a single code ───────────────────────────────────────

class TestRankEvidenceForCode:
    def test_ranks_and_returns_sorted(self):
        evidence_items = [
            _make_evidence("直肠癌术后化疗", "出院小结"),
            _make_evidence("腰痛4月余", "主诉"),
        ]
        result = rank_evidence_for_code(
            "Z51.102", "恶性肿瘤化学治疗", evidence_items,
            [], [], "术后化疗", {}, {"code": "Z51.102", "name": "化疗"},
        )
        assert len(result) == 2
        assert result[0]["strength_score"] > result[1]["strength_score"]

    def test_negated_evidence_penalized(self):
        evidence_items = [
            _make_evidence("排除感染", "现病史", negation=True),
        ]
        result = rank_evidence_for_code(
            "J98.414", "肺部感染", evidence_items, [], [], "", {}, {},
        )
        assert result[0]["strength_score"] < 0.5
        assert result[0]["conflict_flag"] is True

    def test_empty_text_skipped(self):
        evidence_items = [
            {"evidence_text": "", "text": "", "doc_type": "现病史", "certainty": "confirmed", "negation": False},
        ]
        result = rank_evidence_for_code("X", "Y", evidence_items, [], [], "", {}, {})
        assert len(result) == 0

    def test_returns_all_fields(self):
        evidence_items = [_make_evidence("直肠癌术后2月余，为行辅助化疗入院", "现病史")]
        result = rank_evidence_for_code(
            "Z51.102", "恶性肿瘤化学治疗", evidence_items, [], [], "术后化疗", {}, {},
        )
        r = result[0]
        for key in ("evidence_id", "text", "source_document", "strength_score", "category",
                     "certainty", "temporal_relevance", "coding_relevance", "conflict_flag", "rationale"):
            assert key in r, f"Missing key: {key}"


# ── Unsupported code detection ──────────────────────────────────────────────

class TestUnsupportedCodeDetection:
    def test_no_evidence_unsupported(self):
        candidates = [_make_candidate("Z51.102", "化疗")]
        ranked = []  # no evidence at all
        result = detect_unsupported_codes(candidates, [], ranked)
        assert len(result) == 1
        assert result[0]["unsupported_flag"] is True
        assert result[0]["code"] == "Z51.102"

    def test_has_evidence_not_unsupported(self):
        candidates = [_make_candidate("Z51.102", "化疗")]
        ranked = [{"related_code": "Z51.102", "strength_score": 0.7}]
        result = detect_unsupported_codes(candidates, [], ranked)
        assert len(result) == 0


# ── Conflict detection ───────────────────────────────────────────────────────

class TestConflictDetection:
    def test_negated_candidate_conflict(self):
        diag_cands = [_make_candidate("M80.900", "骨质疏松", negation=True)]
        conflicts = detect_conflicts(diag_cands, [], {}, "", [], [])
        assert len(conflicts) >= 1
        assert conflicts[0]["conflict_type"] == ConflictType.DISCHARGE_PROGRESS_CONTRADICTION.value

    def test_chemo_diag_surgery_admission_conflict(self):
        primary = {"code": "Z51.102", "name": "恶性肿瘤化学治疗"}
        conflicts = detect_conflicts([], [], primary, "腰椎手术术前", [], [])
        assert any(c["conflict_type"] == ConflictType.PRIMARY_DIAG_ADMISSION_MISMATCH.value for c in conflicts)

    def test_no_conflict_when_chemo_admission(self):
        primary = {"code": "Z51.102", "name": "恶性肿瘤化学治疗"}
        conflicts = detect_conflicts([], [], primary, "术后化疗", [], [])
        assert not any(c["conflict_type"] == ConflictType.PRIMARY_DIAG_ADMISSION_MISMATCH.value for c in conflicts)

    def test_no_conflicts_default(self):
        conflicts = detect_conflicts([], [], {}, "", [], [])
        assert len(conflicts) == 0


# ── Full rank_all_evidence ──────────────────────────────────────────────────

class TestRankAllEvidence:
    def test_returns_expected_structure(self):
        diag_cands = [_make_candidate("Z51.102", "恶性肿瘤化学治疗", evidence_text="为行辅助化疗入院")]
        proc_cands = [_make_proc_candidate("99.2503", "静脉输注化疗药物", evidence_text="行奥沙利铂化疗")]
        result = rank_all_evidence(
            diagnosis_candidates=diag_cands,
            procedure_candidates=proc_cands,
            evidence_facts=[],
            procedure_facts=[],
            admission_reason="术后化疗",
            timeline={},
            primary_diagnosis={"code": "Z51.102", "name": "恶性肿瘤化学治疗"},
            existing_diagnosis_codes=[],
        )
        assert "top_supporting_evidence" in result
        assert "weak_evidence" in result
        assert "conflicting_evidence" in result
        assert "unsupported_codes" in result
        assert "conflicts" in result
        assert "evidence_strength_avg" in result
        assert "unsupported_code_rate" in result

    def test_scores_within_range(self):
        diag_cands = [_make_candidate("Z51.102", "恶性肿瘤化学治疗", evidence_text="为行辅助化疗入院")]
        result = rank_all_evidence([diag_cands[0]], [], [], [], "术后化疗", {}, {}, [])
        for ev in result["top_supporting_evidence"]:
            assert 0.0 <= ev["strength_score"] <= 1.0


# ── Schema roundtrip ─────────────────────────────────────────────────────────

class TestEvidenceRankingSchema:
    def test_evidence_rank_roundtrip(self):
        er = EvidenceRank(
            evidence_id="EV-001",
            text="直肠癌术后化疗",
            source_document="出院小结",
            source_section="discharge",
            related_code="Z51.102",
            strength_score=0.85,
            category=EvidenceCategory.DIRECT,
            certainty="confirmed",
            temporal_relevance=0.9,
            coding_relevance=0.8,
            conflict_flag=False,
            unsupported_flag=False,
            rationale="出院诊断直接支持",
        )
        data = er.model_dump_json()
        rehydrated = EvidenceRank.model_validate_json(data)
        assert rehydrated.strength_score == 0.85

    def test_ranking_result_roundtrip(self):
        rr = EvidenceRankingResult(
            top_supporting_evidence=[EvidenceRank(source_document="出院小结", text="test", strength_score=0.9, category=EvidenceCategory.DIRECT)],
            unsupported_codes=[UnsupportedCodeResult(code="X99", name="test", reason="no evidence")],
            evidence_strength_avg=0.75,
        )
        data = rr.model_dump_json()
        rehydrated = EvidenceRankingResult.model_validate_json(data)
        assert rehydrated.evidence_strength_avg == 0.75
        assert len(rehydrated.unsupported_codes) == 1


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM response varies between runs")
async def test_pipeline_includes_evidence_ranking(auth_client):
    """Full pipeline response should include evidence_ranking."""
    resp = await auth_client.post("/api/reviews", json={
        "encounter_id": "DEMO-001",
        "async_mode": False,
    })
    if resp.status_code == 404:
        pytest.skip("DEMO-001 not seeded — run 'python -m app.seed' first")
    assert resp.status_code == 200
    data = resp.json()
    assert "evidence_ranking" in data, f"Missing evidence_ranking. Keys: {list(data.keys())}"
