# Case Reasoning Report Builder — unifies 9A-9E clinical cognition outputs
from datetime import datetime, UTC

from app.schemas.case_reasoning import (
    CaseReasoningReport, CaseOverview, TimelineSection, EvidenceSection,
    PrincipalDiagnosisSection, DisagreementSection, ConfidenceSection, AuditSection,
)


def build_case_reasoning_report(context: dict) -> dict:
    """Assemble the unified case reasoning report from pipeline context.

    Reads all cognitive chain outputs (9A timeline, 9B principal reasoning,
    9C evidence ranking, 9D disagreement, 9E confidence) and builds a single
    structured report.
    """
    now = datetime.now(UTC).isoformat()

    # ── 1. Case Overview ──
    case = CaseOverview(
        encounter_id=context.get("encounter_id", ""),
        department=context.get("encounter", {}).get("department", ""),
        admission_reason=context.get("admission_reason", ""),
        doc_count=len(context.get("documents", [])),
        generated_at=now,
    )

    # ── 2. Clinical Timeline (9A) ──
    timeline = context.get("timeline", {})
    timeline_section = TimelineSection(
        summary=timeline.get("timeline_summary", ""),
        anchor_count=len(timeline.get("anchor_points", {})),
        event_count=timeline.get("event_count", len(timeline.get("events", []))),
        unresolved_count=timeline.get("unresolved_count", 0),
        key_events=[
            e.get("description", "")[:120]
            for e in timeline.get("events", [])[:5]
        ],
    )

    # ── 3. Evidence Assessment (9C) ──
    evidence_ranking = context.get("evidence_ranking", {})
    evidence_section = EvidenceSection(
        top_count=len(evidence_ranking.get("top_supporting_evidence", [])),
        weak_count=len(evidence_ranking.get("weak_evidence", [])),
        conflicting_count=len(evidence_ranking.get("conflicting_evidence", [])),
        unsupported_code_count=len(evidence_ranking.get("unsupported_codes", [])),
        strength_avg=evidence_ranking.get("evidence_strength_avg", 0.0),
        unsupported_codes=[uc.get("code", "") for uc in evidence_ranking.get("unsupported_codes", [])[:5]],
        conflicts=[c.get("conflict_summary", "") for c in evidence_ranking.get("conflicts", [])[:3]],
    )

    # ── 4. Principal Diagnosis (9B) ──
    primary_diag = context.get("primary_diagnosis", {}) or {}
    reasoning = context.get("primary_diagnosis_reasoning", {}) or {}
    pd_section = PrincipalDiagnosisSection(
        code=primary_diag.get("code", ""),
        name=primary_diag.get("name", ""),
        why_selected=reasoning.get("why_selected", primary_diag.get("rationale", "")),
        why_not_selected=[wns.get("reason", "") for wns in reasoning.get("why_not_selected", [])],
        rule_basis=reasoning.get("rule_basis", []),
        confidence_level=reasoning.get("confidence_level", "medium"),
        timeline_evidence=reasoning.get("timeline_evidence", ""),
    )

    # ── 5. Disagreement Analysis (9D) ──
    disagreement = context.get("disagreement_analysis", {})
    d_summary = disagreement.get("summary", {})
    disagreement_section = DisagreementSection(
        has_disagreement=d_summary.get("disagreements", 0) > 0,
        correction_count=d_summary.get("disagreements", 0),
        drg_impacted_count=d_summary.get("drg_impacted_count", 0),
        type_distribution=d_summary.get("type_distribution", {}),
        top_corrections=[
            f"{c.get('code_ai', '')} → {c.get('code_correct', '')} ({c.get('disagreement_type', '')})"
            for c in disagreement.get("corrections", [])[:5]
        ],
    )

    # ── 6. Confidence Routing (9E) ──
    calibration = context.get("confidence_calibration", {})
    c_metrics = calibration.get("metrics", {})
    confidence_section = ConfidenceSection(
        auto_count=c_metrics.get("auto_count", 0),
        review_count=c_metrics.get("review_count", 0),
        escalate_count=c_metrics.get("escalate_count", 0),
        auto_accept_rate=c_metrics.get("auto_accept_rate", 0.0),
        override_count=c_metrics.get("override_count", 0),
    )

    # ── 7. Audit Summary ──
    audit_summary = AuditSection(
        total_events=0,  # Filled by runtime if available
        state_path=[],
        gate_outcomes={},
        warnings=context.get("errors", [])[:3] if isinstance(context.get("errors"), list) else [],
    )

    # ── 8. Human-Readable Summary ──
    summary_parts = []

    # Case intro
    dept = case.department or "未知科室"
    reason = case.admission_reason or "未知"
    summary_parts.append(f"患者就诊于{dept}，入院原因：{reason}。")

    # Timeline
    if timeline_section.summary:
        summary_parts.append(f"临床经过：{timeline_section.summary[:200]}。")

    # Principal diagnosis
    if pd_section.code:
        confidence_text = {"high": "高置信", "medium": "中置信", "low": "低置信（需复核）"}.get(pd_section.confidence_level, "中置信")
        summary_parts.append(
            f"主要诊断选择为{pd_section.code}（{pd_section.name}），{confidence_text}。"
            f"{pd_section.why_selected[:200]}"
        )

    # Evidence
    if evidence_section.top_count > 0:
        summary_parts.append(
            f"证据评估：{evidence_section.top_count}条强证据支持，"
            f"{evidence_section.unsupported_code_count}个编码证据不足。"
            f"证据平均强度{evidence_section.strength_avg:.2f}。"
        )

    # Disagreement
    if disagreement_section.has_disagreement:
        summary_parts.append(
            f"分歧分析：发现{disagreement_section.correction_count}处分歧，"
            f"其中{disagreement_section.drg_impacted_count}处影响DRG分组。"
        )

    # Confidence routing
    summary_parts.append(
        f"自动化分流：AUTO={confidence_section.auto_count}, "
        f"REVIEW={confidence_section.review_count}, ESCALATE={confidence_section.escalate_count}。"
    )

    human_readable = "\n\n".join(summary_parts)

    # ── Clinical Narrative ──
    clinical_narrative = _build_clinical_narrative(context, case, timeline_section, pd_section)

    # ── Evidence Story ──
    evidence_story = _build_evidence_story(evidence_ranking, pd_section, context)

    # ── Final Recommendation ──
    final_recommendation = _build_final_recommendation(pd_section, evidence_section, disagreement_section, confidence_section, reasoning or {})

    report = CaseReasoningReport(
        case_overview=case,
        clinical_timeline=timeline_section,
        evidence_assessment=evidence_section,
        principal_diagnosis=pd_section,
        disagreement_analysis=disagreement_section,
        confidence_routing=confidence_section,
        audit_summary=audit_summary,
        clinical_narrative=clinical_narrative,
        evidence_story=evidence_story,
        final_recommendation=final_recommendation,
        human_readable_summary=human_readable,
    )

    return report.model_dump()


# ── Narrative builders (deterministic, no LLM) ──────────────────────────────

def _build_clinical_narrative(context: dict, case, timeline_section, pd_section) -> str:
    """Build a clinical narrative like a senior coder's review note."""
    parts = []

    dept = case.department or "未知科室"
    reason = case.admission_reason or "未知"
    parts.append(f"患者因「{reason}」就诊于{dept}。")

    # Timeline-driven disease evolution
    timeline = context.get("timeline", {})
    events = timeline.get("events", [])
    if events:
        key_events = [
            e for e in events
            if e.get("event_type") in ("surgery", "chemotherapy", "diagnosis", "symptom_onset", "admission", "discharge")
        ][:6]
        if key_events:
            event_descs = []
            for e in key_events:
                time_str = e.get("relative_time") or e.get("timestamp") or ""
                desc = e.get("description", "")
                event_descs.append(f"{time_str} {desc}".strip())
            parts.append("临床经过：" + "；".join(event_descs) + "。")

    # Diagnosis evolution
    if pd_section.code:
        parts.append(
            f"综合入院目的、治疗过程与出院诊断，当前主要诊断确定为{pd_section.code}（{pd_section.name}）。"
        )
        if pd_section.why_selected:
            parts.append(pd_section.why_selected[:300])

    # Rule basis
    if pd_section.rule_basis:
        parts.append(f"本次选择依据编码规则：{'、'.join(pd_section.rule_basis)}。")

    return "\n\n".join(parts)


def _build_evidence_story(evidence_ranking: dict, pd_section, context: dict) -> str:
    """Build an evidence story — grouped by source, telling why the coding is supported."""
    if not evidence_ranking:
        return "当前无可用的证据评估数据。"

    parts = []

    top = evidence_ranking.get("top_supporting_evidence", [])
    weak = evidence_ranking.get("weak_evidence", [])
    conflicting = evidence_ranking.get("conflicting_evidence", [])
    unsupported = evidence_ranking.get("unsupported_codes", [])

    # Strong evidence
    if top:
        sources = sorted(set(ev.get("source_document", "") for ev in top))
        parts.append(f"当前编码建议主要基于以下{len(sources)}类证据来源：{'、'.join(sources)}。")

        # Group by source
        by_source: dict[str, list] = {}
        for ev in top[:8]:
            src = ev.get("source_document", "未知")
            by_source.setdefault(src, []).append(ev)
        for src, items in by_source.items():
            snippets = [it.get("text", "")[:60] for it in items[:3]]
            parts.append(f"  · {src}：{'；'.join(snippets)}")
    else:
        parts.append("未发现强证据来源。")

    # Weak evidence flag
    if weak:
        parts.append(f"注意：存在{len(weak)}条弱证据，证据质量不足以独立支撑编码建议。")

    # Conflicting evidence
    if conflicting:
        parts.append(f"⚠ 发现{len(conflicting)}条冲突证据，需要编码员特别关注。")
        for cf in conflicting[:3]:
            parts.append(f"  · {cf.get('source_document', '')}：{cf.get('text', '')[:80]}")

    # Unsupported codes
    if unsupported:
        codes = [uc.get("code", "") for uc in unsupported[:5]]
        parts.append(f"以下编码证据不足，建议人工复核或补充病历资料：{'、'.join(codes)}。")

    return "\n\n".join(parts)


def _build_final_recommendation(pd_section, evidence_section, disagreement_section, confidence_section, reasoning: dict) -> str:
    """Build a clinical final recommendation — risk-prioritized, actionable."""
    parts = []

    confidence_level = pd_section.confidence_level or reasoning.get("confidence_level", "medium")
    has_disagreement = disagreement_section.has_disagreement
    auto_count = confidence_section.auto_count
    escalate_count = confidence_section.escalate_count
    unsupported_count = evidence_section.unsupported_code_count
    conflicting_count = evidence_section.conflicting_count

    # Top-line recommendation
    if confidence_level == "high" and not has_disagreement and unsupported_count == 0:
        parts.append("【建议确认】当前主诊断选择明确，证据充分，建议编码员确认。")
    elif confidence_level == "low" or has_disagreement or escalate_count > 0:
        parts.append("【建议高级审核】存在以下需要高级编码员关注的风险因素：")
    else:
        parts.append("【建议人工复核】当前主诊断选择合理，建议编码员复核以下要点：")

    # Risk factors (priority-ordered)
    risks = []
    if has_disagreement:
        risks.append(f"与现有编码存在{disagreement_section.correction_count}处分歧，其中{disagreement_section.drg_impacted_count}处影响DRG分组。")
    if escalate_count > 0:
        risks.append(f"{escalate_count}个编码被标记为需升级审核（ESCALATE），需高级编码员裁决。")
    if unsupported_count > 0:
        risks.append(f"{unsupported_count}个编码证据不足，可能需要补充病历资料。")
    if conflicting_count > 0:
        risks.append(f"发现{conflicting_count}条冲突证据，需确认病历描述一致性。")
    if auto_count == 0 and pd_section.code:
        risks.append("主要诊断为人工复核级别，不建议自动确认。")

    for r in risks:
        parts.append(f"  · {r}")

    # DRG note
    if disagreement_section.drg_impacted_count > 0:
        parts.append("DRG提醒：编码变更可能影响DRG入组，请确认分组结果后再提交。")

    # Evidence quality note
    if evidence_section.strength_avg > 0:
        if evidence_section.strength_avg >= 0.6:
            parts.append(f"证据整体质量良好（平均强度{evidence_section.strength_avg:.2f}）。")
        else:
            parts.append(f"证据整体质量偏低（平均强度{evidence_section.strength_avg:.2f}），建议补充关键病历文书。")

    return "\n\n".join(parts)

