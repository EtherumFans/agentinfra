# Disagreement Analyzer — classifies AI vs gold/existing disagreements with taxonomy + correction model
from datetime import datetime, UTC
from enum import Enum
from typing import Optional


class DisagreementType(str, Enum):
    CODE_SPECIFICITY = "code_specificity"
    CODE_SELECTION = "code_selection"
    DIAGNOSIS_INTERPRET = "diagnosis_interpret"
    PRIMARY_VS_SECONDARY = "primary_vs_secondary"
    RULE_VIOLATION = "rule_violation"
    EVIDENCE_CONTRADICTION = "evidence_contradiction"
    DRG_SENSITIVE = "drg_sensitive"
    DOCUMENTATION_GAP = "documentation_gap"


# ── classification logic ────────────────────────────────────────────────────

def _code_prefix(code: str, n: int = 3) -> str:
    return code[:n] if code else ""


def _is_specificity_diff(code1: str, code2: str) -> bool:
    """Check if two codes differ only in specificity (one is .9 or less specific)."""
    if not code1 or not code2:
        return False
    # Same top-level category but different extension
    p1 = _code_prefix(code1)
    p2 = _code_prefix(code2)
    if p1 == p2:
        # Check if one has .9 (unspecified) and the other doesn't
        return (".9" in code1) != (".9" in code2)
    return False


def _classify_disagreement_type(
    ai_code: str, ai_name: str,
    gold_code: str, gold_name: str,
    evidence_ranking: dict,
    primary_diag_code: str,
    admission_reason: str,
    rule_matches: dict,
) -> tuple[DisagreementType, str]:
    """Classify why AI and gold differ.

    Returns (type, rationale_string).
    """
    # 1. Specificity difference (.9 vs specific) — same concept, different granularity
    if _is_specificity_diff(ai_code, gold_code):
        return DisagreementType.CODE_SPECIFICITY, (
            f"编码特异性差异：AI选择{ai_code}，金标准为{gold_code}。"
            f"两者属于同一编码类别，但特异性层级不同。"
        )

    # 2. Documentation gap — AI code has unsupported/weak evidence
    unsupported_codes = {uc.get("code", "") for uc in evidence_ranking.get("unsupported_codes", [])}
    if ai_code in unsupported_codes:
        return DisagreementType.DOCUMENTATION_GAP, (
            f"AI编码{ai_code}缺乏充分证据支撑，金标准{gold_code}可能被遗漏。"
            f"需检查病历中是否有遗漏的诊断描述。"
        )

    # 3. Evidence contradiction — conflicting evidence detected
    conflicts = evidence_ranking.get("conflicts", [])
    for c in conflicts:
        if ai_code in c.get("affected_codes", []):
            return DisagreementType.EVIDENCE_CONTRADICTION, (
                f"AI编码{ai_code}与证据存在冲突：{c.get('conflict_summary', '')}"
                f"金标准{gold_code}与证据更为一致。"
            )

    # 4. Rule violation — check rule matches (before primary/secondary check)
    ai_rules = rule_matches.get(ai_code, [])
    gold_rules = rule_matches.get(gold_code, [])
    if ai_rules and not gold_rules:
        return DisagreementType.RULE_VIOLATION, (
            f"AI编码{ai_code}有规则支撑({','.join(ai_rules)})，金标准{gold_code}未匹配到明确规则。"
            f"建议编码员复核金标准是否正确。"
        )
    if gold_rules and not ai_rules:
        return DisagreementType.RULE_VIOLATION, (
            f"金标准{gold_code}有规则支撑({','.join(gold_rules)})，AI未识别到相关规则。"
            f"AI编码{ai_code}可能需要调整。"
        )

    # 5. Primary vs secondary — one side treats it as primary, the other as secondary
    if ai_code == primary_diag_code:
        return DisagreementType.PRIMARY_VS_SECONDARY, (
            f"主要诊断选择分歧：AI选择{ai_code}为主要诊断，金标准选择{gold_code}。"
            f"可能是入院目的判断不一致导致。"
        )

    # 6. Diagnosis interpretation — same clinical entity, different code choice
    if _code_prefix(ai_code) == _code_prefix(gold_code):
        return DisagreementType.DIAGNOSIS_INTERPRET, (
            f"诊断解读差异：AI和编码员对同一临床情况选择了不同编码"
            f"（AI: {ai_code}, 金标准: {gold_code}），但编码大类一致。"
        )

    # 7. Default: code selection — different codes, different clinical concepts
    return DisagreementType.CODE_SELECTION, (
        f"编码选择差异：AI选择{ai_code}（{ai_name}），金标准为{gold_code}（{gold_name}）。"
        f"两者属于不同编码类别，需编码员裁决。"
    )


# ── DRG sensitivity ─────────────────────────────────────────────────────────

def _check_drg_sensitivity(
    ai_code: str, gold_code: str,
    drg_impact: dict,
) -> tuple[bool, str, str, float]:
    """Check if code change affects DRG grouping.

    Uses existing DRG analysis result if available.
    Returns (is_sensitive, drg_before, drg_after, rw_delta).
    """
    if not drg_impact:
        return False, "", "", 0.0

    # Check if the code under disagreement is mentioned in DRG risks
    drg_risks = drg_impact.get("drg_risks", [])
    expected_drg = drg_impact.get("expected_drg", "")

    # If the AI code appears in DRG risks, it's sensitive
    for risk in drg_risks:
        affected = risk.get("affected_code", risk.get("code", ""))
        if ai_code in str(affected) or gold_code in str(affected):
            return True, expected_drg, risk.get("alternative_drg", ""), risk.get("rw_delta", 0.0)

    # Heuristic: codes in different ICD chapters may affect DRG
    if ai_code[:1] != gold_code[:1]:
        return True, expected_drg, "可能需要重新分组", 0.0

    return False, "", "", 0.0


# ── main analysis ───────────────────────────────────────────────────────────

def analyze_disagreements(
    diagnosis_candidates: list[dict],
    procedure_candidates: list[dict],
    primary_diagnosis: dict,
    evidence_ranking: dict,
    gold_diagnosis_codes: list[str],
    gold_procedure_codes: list[str],
    existing_diagnosis_codes: list[dict],
    existing_procedure_codes: list[dict],
    admission_reason: str,
    drg_impact: dict,
    rule_matches: dict,
    reviewer: str = "system",
) -> dict:
    """Analyze all disagreements between AI output and gold/existing codes.

    Returns dict of corrections + summary compatible with DisagreementAnalysisResult.
    """
    corrections = []

    # Build lookup maps
    ai_diag_codes = {c.get("code", ""): c for c in diagnosis_candidates}
    ai_proc_codes = {c.get("code", ""): c for c in procedure_candidates}
    gold_diag_set = set(gold_diagnosis_codes)
    gold_proc_set = set(gold_procedure_codes)

    # Phase 1: Compare AI diagnosis codes against gold
    for code, c in ai_diag_codes.items():
        if not code:
            continue
        if code in gold_diag_set:
            continue  # Agreement

        # Find best gold match for context
        gold_match = next((gc for gc in gold_diag_set if _code_prefix(gc) == _code_prefix(code)), None)
        gold_name = ""

        # Classify disagreement
        d_type, rationale = _classify_disagreement_type(
            code, c.get("name", ""),
            gold_match or next(iter(gold_diag_set), ""), gold_name,
            evidence_ranking, primary_diagnosis.get("code", ""),
            admission_reason, rule_matches,
        )

        # DRG sensitivity
        drg_sensitive, drg_before, drg_after, rw_delta = _check_drg_sensitivity(
            code, gold_match or "", drg_impact
        )

        correct_code = gold_match or next(iter(gold_diag_set), "") if gold_diag_set else ""
        corrections.append({
            "case_id": "",
            "code_ai": code,
            "code_ai_name": c.get("name", ""),
            "code_correct": correct_code,
            "code_correct_name": gold_name,
            "disagreement_type": d_type.value,
            "type_rationale": rationale,
            "drg_impacted": drg_sensitive,
            "drg_before": drg_before,
            "drg_after": drg_after,
            "rw_delta": rw_delta,
            "rule_reference": rule_matches.get(code, []),
            "evidence_support": c.get("evidence_text", ""),
            "reviewer": reviewer,
            "timestamp": datetime.now(UTC).isoformat(),
            "learnable": d_type not in (DisagreementType.DIAGNOSIS_INTERPRET,),
        })

    # Phase 2: Compare AI procedure codes against gold
    for code, c in ai_proc_codes.items():
        if not code:
            continue
        if code in gold_proc_set:
            continue

        gold_match = next((gc for gc in gold_proc_set if _code_prefix(gc) == _code_prefix(code)), None)
        d_type = DisagreementType.CODE_SELECTION if _code_prefix(code) != (gold_match or "")[:3] else DisagreementType.CODE_SPECIFICITY

        # Check DRG sensitivity for procedure changes
        drg_sensitive, drg_before, drg_after, rw_delta = _check_drg_sensitivity(
            code, gold_match or "", drg_impact
        )

        correct_code = gold_match or next(iter(gold_proc_set), "") if gold_proc_set else ""
        corrections.append({
            "case_id": "",
            "code_ai": code,
            "code_ai_name": c.get("name", ""),
            "code_correct": correct_code,
            "code_correct_name": "",
            "disagreement_type": d_type.value,
            "type_rationale": f"手术编码差异：AI选择{code}，金标准为{correct_code}。" if correct_code else f"AI编码{code}不在金标准中。",
            "drg_impacted": drg_sensitive,
            "drg_before": drg_before,
            "drg_after": drg_after,
            "rw_delta": rw_delta,
            "rule_reference": [],
            "evidence_support": c.get("evidence_text", ""),
            "reviewer": reviewer,
            "timestamp": datetime.now(UTC).isoformat(),
            "learnable": True,
        })

    # Phase 3: Detect missing codes (gold codes AI didn't suggest)
    for gc in gold_diag_set:
        if gc not in ai_diag_codes:
            corrections.append({
                "case_id": "",
                "code_ai": "",
                "code_ai_name": "",
                "code_correct": gc,
                "code_correct_name": "",
                "disagreement_type": DisagreementType.DOCUMENTATION_GAP.value,
                "type_rationale": f"AI遗漏了金标准编码{gc}，可能病历中相关描述未被识别。",
                "drg_impacted": False,
                "drg_before": "",
                "drg_after": "",
                "rw_delta": 0.0,
                "rule_reference": [],
                "evidence_support": "",
                "reviewer": reviewer,
                "timestamp": datetime.now(UTC).isoformat(),
                "learnable": True,
            })

    for gc in gold_proc_set:
        if gc not in ai_proc_codes:
            corrections.append({
                "case_id": "",
                "code_ai": "",
                "code_ai_name": "",
                "code_correct": gc,
                "code_correct_name": "",
                "disagreement_type": DisagreementType.DOCUMENTATION_GAP.value,
                "type_rationale": f"AI遗漏了金标准手术编码{gc}。",
                "drg_impacted": False,
                "drg_before": "",
                "drg_after": "",
                "rw_delta": 0.0,
                "rule_reference": [],
                "evidence_support": "",
                "reviewer": reviewer,
                "timestamp": datetime.now(UTC).isoformat(),
                "learnable": True,
            })

    # Summary
    total_ai = len(ai_diag_codes) + len(ai_proc_codes)
    agreements = max(0, total_ai - len(corrections))
    drg_impacted = sum(1 for corr in corrections if corr.get("drg_impacted", False))
    learnable = sum(1 for corr in corrections if corr.get("learnable", False))

    # Type distribution
    type_dist: dict[str, int] = {}
    for corr in corrections:
        t = corr.get("disagreement_type", "unknown")
        type_dist[t] = type_dist.get(t, 0) + 1

    summary = {
        "total_codes": total_ai,
        "agreements": agreements,
        "disagreements": len(corrections),
        "disagreement_rate": round(len(corrections) / total_ai, 4) if total_ai > 0 else 0.0,
        "drg_impacted_count": drg_impacted,
        "drg_impact_rate": round(drg_impacted / len(corrections), 4) if corrections else 0.0,
        "type_distribution": type_dist,
        "learnable_corrections": learnable,
    }

    return {
        "corrections": corrections,
        "summary": summary,
    }


# Singleton
disagreement_analyzer = None  # stateless function, no class needed
