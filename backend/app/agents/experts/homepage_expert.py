# iCoDer — Medical Record Homepage Expert (v3: LLM-based primary diagnosis selection)
import time
import re
import json
import logging
from typing import Optional

from app.agents.base import BaseExpert
from app.services.rule_engine import rule_engine_service


# ── rule-trigger patterns (deterministic, keyword-based) ─────────────────────

def _has_chemotherapy_context(admission_reason: str, documents: list[dict]) -> bool:
    """Check if the encounter is for chemotherapy/radiotherapy/immunotherapy."""
    keywords = ["化疗", "放疗", "放射治疗", "免疫治疗", "靶向治疗", "化学治疗"]
    text = admission_reason
    for d in documents:
        text += " " + d.get("content", "")
    return any(kw in text for kw in keywords)


def _has_dialysis_context(documents: list[dict]) -> bool:
    """Check if dialysis-related treatment was performed."""
    keywords = ["透析", "血液透析", "腹膜透析", "血滤", "CRRT"]
    text = " ".join(d.get("content", "") for d in documents)
    return any(kw in text for kw in keywords)


def _has_spine_fracture_candidates(candidates: list[dict]) -> bool:
    """Check if candidates include spine fracture codes (M80 or S32)."""
    codes = {c.get("code", "") for c in candidates}
    return any(c.startswith("M80") or c.startswith("S32") for c in codes)


def _has_etiology_code(candidates: list[dict]) -> list[dict]:
    """Find candidates with explicit etiology (etiology field non-empty)."""
    return [c for c in candidates if c.get("etiology") or c.get("finding", "").startswith(("骨质疏松", "糖尿病", "高血压"))]


def _has_combination_code_opportunity(candidates: list[dict]) -> list[dict]:
    """Detect candidates that could be combined (e.g. E11.2 vs E11.9+N18.9)."""
    combination_hints = []
    codes = {c.get("code", "") for c in candidates}
    # Diabetes + nephropathy → E11.2
    if any(c.startswith("E11") for c in codes) and any(c.startswith("N18") for c in codes):
        for c in candidates:
            if c.get("code", "").startswith("E11") and "肾病" in c.get("finding", ""):
                combination_hints.append(c)
    return combination_hints


# ── ranking helpers ──────────────────────────────────────────────────────────

def _build_timeline_evidence(timeline: dict, admission_reason: str) -> str:
    """Extract human-readable timeline evidence for principal diagnosis reasoning."""
    if not timeline:
        return "时间线数据不可用"
    events = timeline.get("events", [])
    if not events and not timeline.get("anchor_points"):
        return "时间线数据不可用"

    events = timeline.get("events", [])
    anchors = timeline.get("anchor_points", {})
    parts = []

    admission_date = anchors.get("admission_date", "")
    if admission_date:
        parts.append(f"入院日期: {admission_date}")

    surgery_date = anchors.get("surgery_date", "")
    if surgery_date:
        parts.append(f"最近手术日期: {surgery_date}")

    if admission_reason:
        parts.append(f"入院原因: {admission_reason}")

    # Summarize key pre-admission events
    pre_admission = [e for e in events if e.get("event_type") in ("surgery", "chemotherapy", "diagnosis", "symptom_onset")]
    if pre_admission:
        event_descs = [f"{e.get('relative_time', '')}: {e.get('description', '')}" for e in pre_admission[:5]]
        parts.append("关键历史事件: " + "; ".join(event_descs))

    # Check for chemotherapy events
    chemo_events = [e for e in events if e.get("event_type") == "chemotherapy"]
    if chemo_events:
        parts.append(f"化疗事件: {len(chemo_events)} 次")

    return "\n".join(parts)


def _match_rules_to_candidates(
    candidates: list[dict],
    admission_reason: str,
    documents: list[dict],
    timeline: dict,
) -> dict[str, list[str]]:
    """Match each candidate to applicable main_diag rules.

    Returns: dict[code] = [rule_id, ...]
    """
    rule_matches: dict[str, list[str]] = {}
    chem_ctx = _has_chemotherapy_context(admission_reason, documents)
    dialysis_ctx = _has_dialysis_context(documents)
    spine_ctx = _has_spine_fracture_candidates(candidates)
    etiology_cands = _has_etiology_code(candidates)
    combo_cands = _has_combination_code_opportunity(candidates)

    etiology_codes = {c.get("code") for c in etiology_cands}
    combo_codes = {c.get("code") for c in combo_cands}

    for c in candidates:
        code = c.get("code", "")
        matches = []

        # R001: applies to all — the "总会" (always applicable)
        matches.append("R001")

        # R002: etiology diagnosis priority — candidate has explicit etiology
        if code in etiology_codes:
            matches.append("R002")

        # R013: chemo/radio/immuno therapy → Z51.x
        if chem_ctx and code.startswith("Z51"):
            matches.append("R013")

        # R014: CKD + dialysis → N18 priority
        if dialysis_ctx and code.startswith("N18"):
            matches.append("R014")

        # R012: multiple spine fractures
        if spine_ctx and (code.startswith("M80") or code.startswith("S32")):
            matches.append("R012")

        # R015: combination code
        if code in combo_codes:
            matches.append("R015")

        rule_matches[code] = matches

    return rule_matches


def _compute_adjusted_score(candidate: dict, rule_matches: list[str], timeline: dict, admission_reason: str) -> float:
    """Adjust candidate score based on rule matches and timeline evidence.

    Base score from LLM/dictionary. Bonus for rule matches.
    """
    score = candidate.get("score", 0.5)
    adjusted = score

    # Rule-based bonuses (each rule adds 0.05–0.12 depending on strength)
    rule_bonuses = {
        "R013": 0.12,  # Strongest: chemo context demands Z51.x
        "R014": 0.10,  # Strong: dialysis context demands N18
        "R002": 0.08,  # Medium: etiology priority
        "R012": 0.06,  # Medium: spine fracture classification
        "R015": 0.07,  # Medium: combination code opportunity
        "R001": 0.02,  # Weak: always applies, small tiebreaker
    }

    for rule_id in rule_matches:
        adjusted += rule_bonuses.get(rule_id, 0.0)

    # Certainty adjustment: ruled_out gets zeroed (should already be filtered)
    certainty = candidate.get("certainty", "")
    if certainty == "ruled_out":
        return 0.0
    if certainty == "suspected":
        adjusted -= 0.05

    # Negation penalty
    if candidate.get("negation", False):
        adjusted -= 0.15

    return min(adjusted, 1.0)


def _generate_why_selected(
    candidate: dict,
    rule_matches: list[str],
    timeline_evidence: str,
    adjusted_score: float,
) -> str:
    """Generate human-readable reasoning for the selected principal diagnosis."""
    code = candidate.get("code", "")
    name = candidate.get("name", "")
    finding = candidate.get("finding", "")

    parts = [f"选择 {code}（{name}）为主要诊断。"]

    # Rule-based reasoning
    if "R013" in rule_matches:
        parts.append("本次入院目的为恶性肿瘤化学治疗，根据R013规则，应选择Z51.x编码为主要诊断。")
    elif "R014" in rule_matches:
        parts.append("住院期间主要资源消耗在肾病相关治疗，根据R014规则，应选择慢性肾病为主要诊断。")
    elif "R002" in rule_matches and candidate.get("etiology"):
        parts.append(f"存在明确病因（{candidate.get('etiology')}），根据R002病因诊断优先原则，选择病因编码。")
    elif "R001" in rule_matches and len(rule_matches) == 1:
        parts.append(f"该诊断在编码候选中综合评分最高（{adjusted_score:.2f}），对患者健康危害最大、消耗医疗资源最多。")

    # Finding-level detail
    if finding:
        parts.append(f"对应临床发现：{finding}。")

    return " ".join(parts)


def _generate_why_not_selected(
    selected_code: str,
    other_candidates: list[dict],
    rule_matches: dict[str, list[str]],
) -> list[dict]:
    """Generate exclusion reasons for top contenders not selected."""
    reasons = []
    for c in other_candidates[:3]:  # top 3 only
        code = c.get("code", "")
        name = c.get("name", "")
        matches = rule_matches.get(code, [])
        reason_parts = []

        if code.startswith("Z51") and "R013" not in matches:
            reason_parts.append("虽然包含Z51编码，但入院目的并非以化疗/放疗为主，R013不适用")
        elif code.endswith(".9") or ".9" in code:
            reason_parts.append("编码特异性不足（.9未特指编码），应优先选择更特异的编码")
        elif matches:
            reason_parts.append(f"匹配规则{','.join(matches)}，但综合评分低于主要诊断")
        else:
            reason_parts.append(f"综合评分低于主要诊断，且未匹配到优先级更高的编码规则")

        # Add score comparison
        score_diff = c.get("score", 0) - (other_candidates[0].get("score", 0) if other_candidates else 0)
        if abs(score_diff) < 0.1:
            reason_parts.append("分数接近主要诊断，建议人工复核确认")

        reasons.append({
            "code": code,
            "name": name,
            "reason": " ".join(reason_parts),
            "rule_reference": matches[0] if matches else None,
        })

    return reasons


def _analyze_disagreement(
    primary_diag: dict,
    existing_codes: list[dict],
    candidates: list[dict],
    rule_matches: dict[str, list[str]],
) -> dict:
    """Analyze disagreement between AI selection and existing principal diagnosis."""
    if not existing_codes:
        return {"has_disagreement": False}

    existing_primary = existing_codes[0] if existing_codes else None
    if isinstance(existing_primary, dict):
        existing_code = existing_primary.get("code", "")
    else:
        existing_code = str(existing_primary) if existing_primary else ""

    if not existing_code or existing_code == primary_diag.get("code", ""):
        return {"has_disagreement": False}

    # Disagreement found
    ai_code = primary_diag.get("code", "")
    ai_rules = rule_matches.get(ai_code, [])
    existing_rules = rule_matches.get(existing_code, [])

    analysis = f"AI推荐 {ai_code} 为主要诊断，与现有编码 {existing_code} 不一致。"
    if ai_rules and not existing_rules:
        analysis += f" AI选择有编码规则支撑（{','.join(ai_rules)}），现有编码未匹配到明确规则。"
    elif existing_rules and not ai_rules:
        analysis += f" 现有编码有规则支撑（{','.join(existing_rules)}），AI可能遗漏了编码上下文。"
    else:
        analysis += " 两者均有规则支撑，需编码员根据完整病历判断。"

    recommendation = "needs_senior_review"
    if len(ai_rules) > len(existing_rules):
        recommendation = "accept_ai"

    return {
        "has_disagreement": True,
        "existing_code": existing_code,
        "existing_name": existing_primary.get("name", "") if isinstance(existing_primary, dict) else "",
        "ai_code": ai_code,
        "ai_name": primary_diag.get("name", ""),
        "analysis": analysis,
        "recommendation": recommendation,
        "rule_basis": ai_rules,
    }


def _assess_confidence(
    primary_diag: dict,
    sorted_candidates: list[dict],
    disagreement: dict,
) -> tuple[str, str, dict]:
    """Assess confidence level and determine if escalation is needed.

    Returns: (confidence_level, confidence_rationale, escalation_dict)
    """
    score = primary_diag.get("confidence", primary_diag.get("score", 0.5))
    escalation = {"escalated": False, "reason": "", "trigger": "", "candidates_in_contention": []}

    # High: strong score + clear margin + no disagreement
    if score >= 0.85 and not disagreement.get("has_disagreement", False):
        if len(sorted_candidates) <= 1:
            return "high", "单一候选编码，置信度高。", escalation
        top_score = sorted_candidates[0].get("score", sorted_candidates[0].get("confidence", 0))
        second_score = sorted_candidates[1].get("score", sorted_candidates[1].get("confidence", 0))
        gap = top_score - second_score
        if gap > 0.15:
            return "high", f"与第二名候选分差较大（{gap:.2f}），选择明确。", escalation

    # Low: close scores, disagreement, or low confidence
    if score < 0.5:
        escalation = {
            "escalated": True,
            "reason": f"主要诊断置信度低（{score:.2f}），建议编码员人工复核确认。",
            "trigger": "score_gap" if len(sorted_candidates) > 1 else "evidence_conflict",
            "candidates_in_contention": [c.get("code", "") for c in sorted_candidates[:3]],
        }
        return "low", f"置信度 {score:.2f}，低于基线阈值。", escalation

    if disagreement.get("has_disagreement", False):
        escalation = {
            "escalated": True,
            "reason": f"AI选择（{primary_diag.get('code', '')}）与现有编码（{disagreement.get('existing_code', '')}）不一致，需编码员裁决。",
            "trigger": "evidence_conflict",
            "candidates_in_contention": [
                primary_diag.get("code", ""),
                disagreement.get("existing_code", ""),
            ],
        }
        return "low", "与现有编码存在分歧。", escalation

    if len(sorted_candidates) >= 2:
        top_score = sorted_candidates[0].get("score", sorted_candidates[0].get("confidence", 0))
        second_score = sorted_candidates[1].get("score", sorted_candidates[1].get("confidence", 0))
        gap = top_score - second_score
        if gap <= 0.10:
            escalation = {
                "escalated": True,
                "reason": f"前两名候选编码分数接近（差距仅{gap:.2f}），选择不确定性高。",
                "trigger": "score_gap",
                "candidates_in_contention": [c.get("code", "") for c in sorted_candidates[:2]],
            }
            return "low", f"与第二名候选分差仅{gap:.2f}，难以自动判定。", escalation

    # Medium: reasonable but needs human review
    return "medium", "编码选择合理，建议编码员复核确认。", escalation


# ── Expert class ─────────────────────────────────────────────────────────────

class MedicalRecordHomepageExpert(BaseExpert):
    name = "Medical Record Homepage Expert"
    description = "Validates and reasons about primary diagnosis selection using coding rules, timeline evidence, clinical priority, and LLM judgment"

    def _build_llm_primary_dx_prompt(
        self,
        admission_reason: str,
        candidates: list[dict],
        documents: list[dict],
    ) -> str:
        """Build a iCoDer-style prompt asking LLM to select the primary diagnosis."""
        lines = [
            "你是资深医学编码审核专家。你的任务是根据临床推理为本次住院病历选择主要诊断。",
            "",
            "## Encounter Context",
        ]
        if admission_reason:
            lines.append(f"Admission reason: {admission_reason}")
        # Document summaries (first 200 chars each)
        for i, doc in enumerate(documents[:3]):
            content = doc.get("content", "")[:200]
            if content:
                lines.append(f"Document {i+1} ({doc.get('doc_type', 'note')}): {content}")
        lines.append("")
        lines.append("## Diagnosis Candidates")
        lines.append("Consider these candidates identified from the medical record:")
        lines.append("")
        for i, c in enumerate(candidates[:8]):
            code = c.get("code", "")
            name = c.get("name", "")
            score = c.get("score", c.get("confidence", 0))
            finding = c.get("finding", "")
            evidence = c.get("evidence_text", "")[:150]
            lines.append(f"{i+1}. {code} — {name}")
            lines.append(f"   Score: {score:.2f} | Finding: {finding}")
            if evidence:
                lines.append(f"   Evidence: {evidence}")
            lines.append("")
        lines.append("## Task")
        lines.append(
            "Select the SINGLE best primary diagnosis. Follow these principles:"
        )
        lines.append(
            "1. The primary diagnosis should be the MAIN REASON for this admission "
            "(the condition that brought the patient to hospital)."
        )
        lines.append(
            "2. Chronic conditions (hypertension, diabetes, etc.) should ONLY be primary "
            "if the admission was specifically for managing that condition."
        )
        lines.append(
            "3. Acute conditions that match the admission reason take priority over "
            "stable chronic conditions, even if the chronic condition score is higher."
        )
        lines.append(
            "4. Prefer specific codes over .9 (unspecified) codes when evidence supports it."
        )
        lines.append("")
        lines.append("Return ONLY valid JSON, no other text:")
        lines.append('{')
        lines.append('  "primary_code": "X00.0",')
        lines.append('  "primary_name": "Full code description",')
        lines.append(
            '  "rationale": "Why this is the primary (cite admission reason, clinical urgency, resource use)",'
        )
        lines.append(
            '  "why_not_others": [{"code": "X00.0", "reason": "Why this is secondary"}],'
        )
        lines.append('  "confidence": 0.85')
        lines.append('}')
        return "\n".join(lines)

    async def _llm_select_primary(
        self,
        admission_reason: str,
        ranked_candidates: list[dict],
        documents: list[dict],
    ) -> dict | None:
        """Use LLM to select the primary diagnosis from ranked candidates."""
        prompt = self._build_llm_primary_dx_prompt(
            admission_reason, ranked_candidates, documents
        )
        schema_hint = """{
  "primary_code": "X00.0",
  "primary_name": "Full code description",
  "rationale": "Why this is the primary diagnosis",
  "why_not_others": [{"code": "X00.0", "reason": "Why this is secondary"}],
  "confidence": 0.85
}"""
        try:
            result = await self.llm.extract_json(
                prompt="Select the single best primary diagnosis from the clinical context below.",
                text=prompt,
                schema_hint=schema_hint,
            )
            if isinstance(result, dict) and result.get("primary_code"):
                return result
            else:
                logging.getLogger(__name__).warning(
                    f"LLM returned unexpected result type: {type(result).__name__}"
                )
        except Exception as e:
            logging.getLogger(__name__).warning(f"LLM primary dx selection failed: {e}")
        return None

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("reasoning about principal diagnosis", context)

        diagnosis_candidates = context.get("diagnosis_candidates", [])
        procedure_candidates = context.get("procedure_candidates", [])
        existing_diag = context.get("existing_diagnosis_codes", [])
        existing_proc = context.get("existing_procedure_codes", [])
        documents = context.get("documents", [])
        timeline = context.get("timeline", {})
        admission_reason = context.get("admission_reason", "")

        # ── Filter out negated / ruled-out candidates ──
        # Guard: skip non-dict items (defensive against malformed pipeline data)
        active_candidates = [
            c for c in diagnosis_candidates
            if isinstance(c, dict) and not c.get("negation") and c.get("certainty") != "ruled_out"
        ]

        # ── Match rules to candidates ──
        rule_matches = _match_rules_to_candidates(
            active_candidates, admission_reason, documents, timeline
        )

        # ── Build timeline evidence ──
        timeline_evidence = _build_timeline_evidence(timeline, admission_reason)

        # ── Compute adjusted scores ──
        for c in active_candidates:
            code = c.get("code", "")
            c["_rule_matches"] = rule_matches.get(code, [])
            c["_adjusted_score"] = _compute_adjusted_score(
                c, c["_rule_matches"], timeline, admission_reason
            )

        # ── Sort by adjusted score ──
        ranked_diag = sorted(
            active_candidates,
            key=lambda c: (c.get("_adjusted_score", 0), c.get("score", 0)),
            reverse=True,
        )

        ranked_proc = sorted(
            [c for c in procedure_candidates if isinstance(c, dict)],
            key=lambda c: c.get("score", 0),
            reverse=True,
        )

        # ── LLM-based primary diagnosis selection (iCoDer-style) ──
        primary_diag = None
        reasoning = None

        if ranked_diag:
            # First, ask LLM to select primary based on admission context
            llm_selection = await self._llm_select_primary(
                admission_reason, ranked_diag[:8], documents
            )

            # Resolve the LLM's choice to an actual candidate
            selected_code = llm_selection.get("primary_code", "") if llm_selection else ""
            top = next(
                (c for c in ranked_diag if c.get("code") == selected_code),
                ranked_diag[0],  # fallback to rule-based top if LLM choice not found
            )
            top_rules = top.get("_rule_matches", [])
            adj_score = top.get("_adjusted_score", top.get("score", 0))

            # Use LLM's rationale if available, otherwise generate deterministic one
            if llm_selection and llm_selection.get("primary_code") == top.get("code"):
                why_selected = llm_selection.get("rationale", "")
                why_not_selected = [
                    {"code": n.get("code", ""), "reason": n.get("reason", "")}
                    for n in llm_selection.get("why_not_others", [])
                ]
                llm_confidence = llm_selection.get("confidence", 0)
            else:
                why_selected = _generate_why_selected(top, top_rules, timeline_evidence, adj_score)
                why_not_selected = _generate_why_not_selected(
                    top.get("code", ""), ranked_diag[1:], rule_matches
                )
                llm_confidence = 0

            # Build primary diagnosis dict
            primary_diag = {
                "code": top["code"],
                "name": top["name"],
                "confidence": top["score"],
                "adjusted_confidence": adj_score,
                "evidence_text": top.get("evidence_text", ""),
                "rationale": why_selected,
                "llm_selected": bool(llm_selection),
                "llm_confidence": llm_confidence,
            }

            # Disagreement analysis
            disagreement = _analyze_disagreement(
                primary_diag, existing_diag, ranked_diag, rule_matches
            )

            # Confidence assessment
            confidence_level, confidence_rationale, escalation = _assess_confidence(
                primary_diag, ranked_diag, disagreement
            )

            reasoning = {
                "why_selected": why_selected,
                "why_not_selected": why_not_selected,
                "rule_basis": top_rules,
                "timeline_evidence": timeline_evidence,
                "confidence_level": confidence_level,
                "confidence_rationale": confidence_rationale,
                "disagreement_analysis": disagreement,
                "confidence_escalation": escalation,
                "llm_selection": llm_selection,
            }

        # ── Fallback when LLM selection fails: use rule-based top candidate ──
        if primary_diag is None and ranked_diag:
            top = ranked_diag[0]
            primary_diag = {
                "code": top.get("code", ""),
                "name": top.get("name", ""),
                "confidence": top.get("score", top.get("_adjusted_score", 0)),
                "adjusted_confidence": top.get("_adjusted_score", top.get("score", 0)),
                "evidence_text": top.get("evidence_text", ""),
                "rationale": _generate_why_selected(top, top.get("_rule_matches", []), _build_timeline_evidence(timeline, admission_reason), top.get("_adjusted_score", top.get("score", 0))),
                "llm_selected": False,
                "llm_confidence": 0,
            }
            reasoning = {
                "why_selected": primary_diag.get("rationale", ""),
                "why_not_selected": [],
                "rule_basis": top.get("_rule_matches", []),
                "timeline_evidence": _build_timeline_evidence(timeline, admission_reason),
                "confidence_level": "medium" if top.get("score", 0) > 0.7 else "low",
                "confidence_rationale": "Rule-based selection (LLM unavailable)",
                "disagreement_analysis": _analyze_disagreement(primary_diag, existing_diag, ranked_diag, rule_matches),
                "confidence_escalation": "needs_review",
                "llm_selection": None,
            }

        # ── Determine main procedure ──
        main_proc = None
        if ranked_proc:
            top = ranked_proc[0]
            main_proc = {
                "code": top["code"],
                "name": top["name"],
                "confidence": top["score"],
                "evidence_text": top.get("evidence_text", ""),
                "rationale": f"Ranked 1st: procedure={top.get('procedure_name', '-')}, score={top['score']:.2f}",
            }

        # ── Check existing codes ──
        # Normalize: existing codes can be strings or dicts
        def _n(item):
            if isinstance(item, dict):
                return item.get("code", ""), item.get("name", "")
            return str(item) if item else "", ""
        existing_diag_check = []
        for ed in existing_diag:
            code, name = _n(ed)
            if not code: continue
            matched = next((c for c in diagnosis_candidates if c.get("code") == code), None)
            rule_checks = await rule_engine_service.check_code_against_rules(
                code, name, context
            )
            existing_diag_check.append({
                "existing_code": code,
                "claimed_name": name,
                "matched_candidate": matched is not None,
                "agent_judgment": "supported" if matched else "needs_review",
                "evidence_found": matched.get("evidence_text", "") if matched else "",
                "rule_checks": rule_checks,
            })

        existing_proc_check = []
        for ep in existing_proc:
            code, name = _n(ep)
            if not code: continue
            matched = next((c for c in procedure_candidates if c.get("code") == code), None)
            rule_checks = await rule_engine_service.check_code_against_rules(
                code, name, context
            )
            existing_proc_check.append({
                "existing_code": code,
                "claimed_name": name,
                "matched_candidate": matched is not None,
                "agent_judgment": "supported" if matched else "needs_review",
                "evidence_found": matched.get("evidence_text", "") if matched else "",
                "rule_checks": rule_checks,
            })

        return self._timed_result(start, {
            "expert": self.name,
            "primary_diagnosis": primary_diag,
            "primary_diagnosis_reasoning": reasoning,
            "main_procedure": main_proc,
            "secondary_diagnoses": ranked_diag[1:] if len(ranked_diag) > 1 else [],
            "other_procedures": ranked_proc[1:] if len(ranked_proc) > 1 else [],
            "existing_diagnosis_review": existing_diag_check,
            "existing_procedure_review": existing_proc_check,
        })
