# Evidence Ranker Service — deterministic evidence strength scoring + conflict detection
import re
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class EvidenceCategory(str, Enum):
    DIRECT = "direct"
    INFERRED = "inferred"
    WEAK = "weak"
    CONFLICTING = "conflicting"
    UNSUPPORTED = "unsupported"


class ConflictType(str, Enum):
    DIAG_TREATMENT_MISMATCH = "diagnosis_treatment_mismatch"
    DISCHARGE_PROGRESS_CONTRADICTION = "discharge_progress_contradiction"
    PROCEDURE_RECORD_MISMATCH = "procedure_record_mismatch"
    PRIMARY_DIAG_ADMISSION_MISMATCH = "primary_diag_admission_mismatch"
    DIAG_OUTCOME_MISMATCH = "diagnosis_outcome_mismatch"


# ── source document scoring ──────────────────────────────────────────────────

def _score_source_document(doc_type: str) -> tuple[float, str]:
    """Score evidence based on source document type authority."""
    dt = doc_type or ""
    if any(kw in dt for kw in ["出院诊断", "出院小结", "出院记录"]):
        return 0.15, "来自出院诊断/出院小结"
    if "手术记录" in dt:
        return 0.12, "来自手术记录"
    if "病程记录" in dt:
        return 0.08, "来自病程记录"
    if any(kw in dt for kw in ["检查", "检验", "报告", "病理", "MRI", "CT", "影像", "超声"]):
        return 0.06, "来自检查/检验报告"
    if any(kw in dt for kw in ["既往史", "过去史", "个人史"]):
        return -0.10, "来自既往史(背景病史)"
    if "主诉" in dt:
        return 0.03, "来自主诉"
    if "现病史" in dt:
        return 0.05, "来自现病史"
    return 0.0, "来源类型未知"


def _detect_source_section(doc_type: str, text: str) -> str:
    """Classify which section of clinical narrative the evidence belongs to."""
    dt = doc_type or ""
    if any(kw in dt for kw in ["既往史", "过去史"]):
        return "history"
    if any(kw in dt for kw in ["出院诊断", "出院小结", "出院记录"]):
        return "discharge"
    if "手术记录" in dt:
        return "treatment"
    if any(kw in dt for kw in ["检查", "检验", "报告", "病理", "MRI", "CT"]):
        return "diagnostic_test"
    if any(kw in dt for kw in ["主诉", "入院", "现病史"]):
        return "admission_reason"
    return "other"


def _check_history_background(text: str, doc_type: str) -> tuple[float, str]:
    """Penalize evidence that is clearly historical/background rather than current."""
    history_markers = [
        r"\d+年前", r"\d+月前", r"\d+年前", r"既往有", r"曾患", r"已愈",
        r"无高血压|无糖尿病|无冠心病", r"个人史", r"婚育史",
    ]
    for pattern in history_markers:
        if re.search(pattern, text):
            return -0.10, f"证据来自既往史/背景描述 (匹配模式: {pattern})"
    return 0.0, ""


# ── consistency scoring ─────────────────────────────────────────────────────

def _score_admission_consistency(text: str, admission_reason: str) -> tuple[float, str]:
    """Check if evidence aligns with admission reason."""
    if not admission_reason:
        return 0.0, "无入院原因可比较"
    # Extract 2-char tokens from admission reason for fuzzy matching
    reason_no_punct = re.sub(r"[，。、,]", "", admission_reason)
    tokens = set()
    for i in range(len(reason_no_punct) - 1):
        tokens.add(reason_no_punct[i:i+2])
    if not tokens:
        return 0.0, "入院原因无有效关键词"
    matches = sum(1 for tok in tokens if tok in text)
    if matches >= 4:
        return 0.05, f"证据与入院原因高度一致 (匹配{matches}个分词)"
    if matches >= 2:
        return 0.03, f"证据与入院原因部分一致 (匹配{matches}个分词)"
    return 0.0, "证据与入院原因无明显关联"


def _score_treatment_consistency(
    evidence_text: str, procedure_candidates: list[dict], procedure_facts: list[dict]
) -> tuple[float, str]:
    """Check if evidence aligns with performed procedures."""
    if not procedure_candidates and not procedure_facts:
        return 0.0, "无手术/操作可比较"
    proc_names = set()
    for pc in procedure_candidates:
        proc_names.add(pc.get("name", ""))
    for pf in procedure_facts:
        proc_names.add(pf.get("procedure_name", ""))
    if not proc_names:
        return 0.0, "无手术名称可匹配"
    for pn in proc_names:
        if pn and len(pn) >= 2 and pn in evidence_text:
            return 0.05, f"证据与治疗过程一致 (匹配手术: {pn})"
    return 0.0, "证据与治疗过程无明显关联"


def _score_timeline_consistency(
    text: str, timeline: dict, admission_reason: str
) -> tuple[float, str]:
    """Check if evidence aligns with the clinical timeline."""
    if not timeline or not timeline.get("anchor_points"):
        return 0.0, "时间线数据不可用"
    events = timeline.get("events", [])
    if not events:
        return 0.0, "时间线事件为空"
    # Check if evidence mentions events near the admission timeframe
    event_descriptions = [e.get("description", "") for e in events]
    for desc in event_descriptions:
        if desc and len(desc) >= 3 and desc[:3] in text:
            return 0.05, f"证据与时间线事件一致 (匹配: {desc[:20]})"
    return 0.0, "证据与时间线无直接关联"


def _score_primary_diag_consistency(text: str, primary_diagnosis: dict) -> tuple[float, str]:
    """Check if evidence supports the selected primary diagnosis."""
    if not primary_diagnosis:
        return 0.0, "无主要诊断可比较"
    pd_code = primary_diagnosis.get("code", "")
    pd_name = primary_diagnosis.get("name", "")
    if pd_name and len(pd_name) >= 2 and pd_name[:2] in text:
        return 0.03, f"证据直接支持主要诊断 {pd_code}"
    if pd_code and pd_code in text:
        return 0.02, f"证据提及主要诊断编码 {pd_code}"
    return 0.0, "证据与主要诊断无明显关联"


# ── negation / uncertainty ──────────────────────────────────────────────────

def _score_negation_uncertainty(
    negation: bool, certainty: str
) -> tuple[float, str]:
    """Penalize negated or uncertain evidence."""
    if negation:
        return -0.20, "证据为否定/排除描述"
    if certainty in ("suspected", "probable"):
        return -0.05, f"证据确定性不足 (certainty={certainty})"
    if certainty == "ruled_out":
        return -0.30, "证据已被排除"
    return 0.0, ""


# ── category assignment ─────────────────────────────────────────────────────

def _assign_category(total_score: float, negated: bool, suspected: bool, source_doc: str) -> EvidenceCategory:
    """Assign evidence category based on total score and flags."""
    if negated:
        return EvidenceCategory.CONFLICTING
    if suspected and total_score < 0.3:
        return EvidenceCategory.WEAK
    if total_score >= 0.6:
        return EvidenceCategory.DIRECT
    if total_score >= 0.3:
        return EvidenceCategory.INFERRED
    return EvidenceCategory.WEAK


# ── main ranking function ───────────────────────────────────────────────────

def rank_evidence_for_code(
    code: str,
    code_name: str,
    evidence_items: list[dict],
    procedure_candidates: list[dict],
    procedure_facts: list[dict],
    admission_reason: str,
    timeline: dict,
    primary_diagnosis: dict,
) -> list[dict]:
    """Rank all evidence items for a single code.

    Returns list of EvidenceRank dicts sorted by strength_score descending.
    """
    results = []
    for i, ev in enumerate(evidence_items):
        text = ev.get("evidence_text", ev.get("text", ""))
        if not text:
            continue
        doc_type = ev.get("source_document", ev.get("doc_type", "unknown"))
        certainty = ev.get("certainty", "confirmed")
        negation = ev.get("negation", False)

        total_score = 0.5  # baseline
        rationale_parts = []

        # 1. Source document
        src_score, src_reason = _score_source_document(doc_type)
        total_score += src_score
        if src_score != 0:
            rationale_parts.append(src_reason)

        # 2. History/background check
        hist_score, hist_reason = _check_history_background(text, doc_type)
        total_score += hist_score
        if hist_score != 0:
            rationale_parts.append(hist_reason)

        # 3. Admission consistency
        adm_score, adm_reason = _score_admission_consistency(text, admission_reason)
        total_score += adm_score
        if adm_score != 0:
            rationale_parts.append(adm_reason)

        # 4. Treatment consistency
        trt_score, trt_reason = _score_treatment_consistency(text, procedure_candidates, procedure_facts)
        total_score += trt_score
        if trt_score != 0:
            rationale_parts.append(trt_reason)

        # 5. Timeline consistency
        tml_score, tml_reason = _score_timeline_consistency(text, timeline, admission_reason)
        total_score += tml_score
        if tml_score != 0:
            rationale_parts.append(tml_reason)

        # 6. Primary diagnosis consistency
        pdiag_score, pdiag_reason = _score_primary_diag_consistency(text, primary_diagnosis)
        total_score += pdiag_score
        if pdiag_score != 0:
            rationale_parts.append(pdiag_reason)

        # 7. Negation/uncertainty
        neg_score, neg_reason = _score_negation_uncertainty(negation, certainty)
        total_score += neg_score
        if neg_score != 0:
            rationale_parts.append(neg_reason)

        total_score = max(0.0, min(1.0, total_score))
        source_section = _detect_source_section(doc_type, text)

        # Temporal relevance: evidence from admission/discharge has high temporal relevance
        temporal_relevance = 0.8 if source_section in ("admission_reason", "discharge") else (
            0.5 if source_section == "treatment" else 0.3
        )

        # Coding relevance: check if code name appears in evidence text
        coding_relevance = 0.8 if (code_name and len(code_name) >= 2 and code_name[:2] in text) else (
            0.5 if (code and code in text) else 0.3
        )

        category = _assign_category(total_score, negation, certainty == "suspected", doc_type)

        results.append({
            "evidence_id": ev.get("evidence_id", f"EV-{i:03d}"),
            "text": text[:300],
            "source_document": doc_type,
            "source_section": source_section,
            "related_code": code,
            "strength_score": round(total_score, 4),
            "category": category.value,
            "certainty": certainty,
            "temporal_relevance": temporal_relevance,
            "coding_relevance": coding_relevance,
            "conflict_flag": category == EvidenceCategory.CONFLICTING,
            "unsupported_flag": total_score < 0.2,
            "rationale": "; ".join(rationale_parts) if rationale_parts else f"综合评分 {total_score:.2f}",
        })

    results.sort(key=lambda r: r["strength_score"], reverse=True)
    return results


# ── conflict detection ──────────────────────────────────────────────────────

def detect_conflicts(
    diagnosis_candidates: list[dict],
    procedure_candidates: list[dict],
    primary_diagnosis: dict,
    admission_reason: str,
    ranked_evidence: list[dict],
    existing_codes: list[dict],
) -> list[dict]:
    """Detect evidence conflicts across the case."""
    conflicts = []

    # Conflict 1: diagnosis-treatment mismatch — infection diag but no infection-related procedure
    diag_names = [c.get("name", "") for c in diagnosis_candidates]
    proc_names = [c.get("name", "") for c in procedure_candidates]
    all_text = " ".join(diag_names + proc_names)
    infection_keywords = ["感染", "肺炎", "脓毒", "败血症", "炎症"]
    infection_diag = any(kw in name for name in diag_names for kw in infection_keywords)
    infection_proc = any(kw in name for name in proc_names for kw in infection_keywords)
    anti_infective = any(kw in all_text for kw in ["抗生素", "抗感染", "抗菌", "万古", "头孢", "左氧"])

    if infection_diag and not (infection_proc or anti_infective):
        conflicts.append({
            "conflict_type": ConflictType.DIAG_TREATMENT_MISMATCH.value,
            "conflict_summary": "存在感染相关诊断，但未发现抗感染治疗或相关操作。",
            "affected_codes": [c.get("code", "") for c in diagnosis_candidates if any(kw in c.get("name", "") for kw in infection_keywords)],
            "review_required": True,
        })

    # Conflict 2: negated finding appears as a code candidate
    for c in diagnosis_candidates + procedure_candidates:
        if c.get("negation", False):
            conflicts.append({
                "conflict_type": ConflictType.DISCHARGE_PROGRESS_CONTRADICTION.value,
                "conflict_summary": f"编码 {c.get('code', '')} ({c.get('name', '')}) 对应的证据为否定/排除描述，编码与病程记录不一致。",
                "affected_codes": [c.get("code", "")],
                "review_required": True,
            })

    # Conflict 3: primary diagnosis contradicts admission reason (e.g. Z51 chemo but admission says surgery)
    if primary_diagnosis and admission_reason:
        pd_code = primary_diagnosis.get("code", "")
        pd_name = primary_diagnosis.get("name", "")
        chemo_diag = pd_code.startswith("Z51") or "化疗" in pd_name
        surgery_admission = any(kw in admission_reason for kw in ["手术", "术前"])
        chemo_admission = any(kw in admission_reason for kw in ["化疗", "放疗"])

        if chemo_diag and surgery_admission and not chemo_admission:
            conflicts.append({
                "conflict_type": ConflictType.PRIMARY_DIAG_ADMISSION_MISMATCH.value,
                "conflict_summary": f"主要诊断为化疗相关({pd_code})，但入院原因为手术相关({admission_reason})，请确认入院目的。",
                "affected_codes": [pd_code],
                "review_required": True,
            })

    # Conflict 4: procedure code body site mismatch with procedure facts
    proc_facts_from_context = [
        pf for pf in [{}]  # placeholder — body_site comes from evidence facts
    ]
    for pc in procedure_candidates:
        pc_body = pc.get("body_site", "")
        if not pc_body:
            continue
        ev_text = pc.get("evidence_text", "")
        if ev_text and pc_body and pc_body not in ev_text:
            conflicts.append({
                "conflict_type": ConflictType.PROCEDURE_RECORD_MISMATCH.value,
                "conflict_summary": f"手术编码 {pc.get('code', '')} 的部位({pc_body})与手术记录证据不一致。",
                "affected_codes": [pc.get("code", "")],
                "review_required": True,
            })

    return conflicts


# ── unsupported code detection ──────────────────────────────────────────────

def detect_unsupported_codes(
    diagnosis_candidates: list[dict],
    procedure_candidates: list[dict],
    ranked_evidence: list[dict],
) -> list[dict]:
    """Detect codes that lack adequate evidence support."""
    unsupported = []

    # Build evidence coverage map: code → best strength
    evidence_by_code: dict[str, float] = {}
    for ev in ranked_evidence:
        code = ev.get("related_code", "")
        if code:
            if code not in evidence_by_code or ev["strength_score"] > evidence_by_code[code]:
                evidence_by_code[code] = ev["strength_score"]

    for c in diagnosis_candidates + procedure_candidates:
        code = c.get("code", "")
        best_strength = evidence_by_code.get(code, 0.0)

        # Unsupported if: no evidence OR strength below threshold
        if best_strength == 0.0:
            unsupported.append({
                "code": code,
                "name": c.get("name", ""),
                "reason": "未找到任何证据支撑",
                "strength_best": 0.0,
                "unsupported_flag": True,
                "review_required": True,
            })
        elif best_strength < 0.2:
            unsupported.append({
                "code": code,
                "name": c.get("name", ""),
                "reason": f"证据强度过低 ({best_strength:.2f})，需人工确认",
                "strength_best": best_strength,
                "unsupported_flag": True,
                "review_required": True,
            })
        # Flag codes with only weak evidence
        elif best_strength < 0.35:
            # Not fully unsupported but borderline
            pass

    return unsupported


# ── main entry point ────────────────────────────────────────────────────────

def rank_all_evidence(
    diagnosis_candidates: list[dict],
    procedure_candidates: list[dict],
    evidence_facts: list[dict],
    procedure_facts: list[dict],
    admission_reason: str,
    timeline: dict,
    primary_diagnosis: dict,
    existing_diagnosis_codes: list[dict],
) -> dict:
    """Rank all evidence, detect unsupported codes and conflicts.

    Returns a dict compatible with EvidenceRankingResult.
    """
    all_ranked = []

    # Rank evidence for each diagnosis candidate
    for dc in diagnosis_candidates:
        code = dc.get("code", "")
        # Gather evidence: use diagnosis_facts + candidate's own evidence_text
        evidence_items = list(evidence_facts)
        if dc.get("evidence_text"):
            evidence_items.append({
                "evidence_text": dc["evidence_text"],
                "source_document": dc.get("source_document", "现病史"),
                "doc_type": dc.get("doc_type", "现病史"),
                "certainty": dc.get("certainty", "confirmed"),
                "negation": dc.get("negation", False),
            })
        ranked = rank_evidence_for_code(
            code, dc.get("name", ""), evidence_items,
            procedure_candidates, procedure_facts,
            admission_reason, timeline, primary_diagnosis,
        )
        all_ranked.extend(ranked)

    # Rank evidence for each procedure candidate
    for pc in procedure_candidates:
        code = pc.get("code", "")
        evidence_items = list(procedure_facts)
        if pc.get("evidence_text"):
            evidence_items.append({
                "evidence_text": pc["evidence_text"],
                "source_document": pc.get("source_document", "手术记录"),
                "doc_type": pc.get("doc_type", "手术记录"),
                "certainty": pc.get("certainty", "confirmed"),
                "negation": pc.get("negation", False),
            })
        ranked = rank_evidence_for_code(
            code, pc.get("name", ""), evidence_items,
            procedure_candidates, procedure_facts,
            admission_reason, timeline, primary_diagnosis,
        )
        all_ranked.extend(ranked)

    # Sort by strength descending
    all_ranked.sort(key=lambda r: r["strength_score"], reverse=True)

    # Partition by category
    top = [r for r in all_ranked if r["category"] in ("direct", "inferred") and not r["conflict_flag"]]
    weak = [r for r in all_ranked if r["category"] == "weak"]
    conflicting = [r for r in all_ranked if r["conflict_flag"]]

    # Detect unsupported codes
    unsupported_codes = detect_unsupported_codes(
        diagnosis_candidates, procedure_candidates, all_ranked
    )

    # Detect conflicts
    conflicts = detect_conflicts(
        diagnosis_candidates, procedure_candidates,
        primary_diagnosis, admission_reason,
        all_ranked, existing_diagnosis_codes,
    )

    # Metrics
    total_ranked = len(all_ranked)
    total_codes = len(diagnosis_candidates) + len(procedure_candidates)

    evidence_strength_avg = (
        round(sum(r["strength_score"] for r in all_ranked) / total_ranked, 4)
        if total_ranked > 0 else 0.0
    )
    unsupported_code_rate = round(len(unsupported_codes) / total_codes, 4) if total_codes > 0 else 0.0
    conflict_rate = round(len(conflicts) / total_codes, 4) if total_codes > 0 else 0.0

    return {
        "top_supporting_evidence": top,
        "weak_evidence": weak,
        "conflicting_evidence": conflicting,
        "unsupported_codes": unsupported_codes,
        "conflicts": conflicts,
        "evidence_strength_avg": evidence_strength_avg,
        "unsupported_code_rate": unsupported_code_rate,
        "conflict_rate": conflict_rate,
    }


# Singleton
evidence_ranker = None  # Instantiated by orchestrator — stateless function, no need for class instance
