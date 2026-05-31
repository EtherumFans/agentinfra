# Confidence Calibrator — multi-source calibration + selective automation routing
from enum import Enum
from typing import Optional


class RoutingTier(str, Enum):
    AUTO = "auto"
    REVIEW = "review"
    ESCALATE = "escalate"


# ── risk-tier policy ────────────────────────────────────────────────────────

RISK_TIER_POLICY: dict[str, RoutingTier] = {
    "primary_diagnosis": RoutingTier.REVIEW,     # Never auto-accept primary
    "secondary_diagnosis": RoutingTier.AUTO,     # Can auto-accept if score high
    "procedure_code": RoutingTier.AUTO,          # Can auto-accept if score high
    "drg_sensitive_code": RoutingTier.ESCALATE,  # Always escalate DRG codes
    "mcc_cc_code": RoutingTier.REVIEW,           # Review MCC/CC
    "unspecified_code": RoutingTier.REVIEW,      # .9 codes need review
}

# ── calibration weights ─────────────────────────────────────────────────────

INPUT_WEIGHTS = {
    "raw_score": 0.35,
    "evidence_strength": 0.25,
    "rule_match_count": 0.15,
    "disagreement_penalty": -0.15,
    "negation_penalty": -0.10,
    "specificity_bonus": 0.05,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ── input extractors ────────────────────────────────────────────────────────

def _is_unspecified(code: str) -> bool:
    return ".9" in code if code else False


def _get_evidence_strength(code: str, evidence_ranking: dict) -> float:
    """Get best evidence strength for a code from Sprint 9C results."""
    if not evidence_ranking:
        return 0.0
    for ev in evidence_ranking.get("top_supporting_evidence", []):
        if ev.get("related_code") == code:
            return ev.get("strength_score", 0.0)
    # Check unsupported list
    for uc in evidence_ranking.get("unsupported_codes", []):
        if uc.get("code") == code:
            return uc.get("strength_best", 0.0)
    return 0.3  # default: unknown


def _get_rule_match_count(code: str, primary_diag_reasoning: dict) -> int:
    """Count rules matched for this code."""
    if not primary_diag_reasoning:
        return 0
    # Primary diagnosis gets the full rule_basis
    rule_basis = primary_diag_reasoning.get("rule_basis", [])
    return len(rule_basis) if rule_basis else 0


def _is_in_disagreement(code: str, disagreement_analysis: dict) -> bool:
    """Check if this code has a disagreement."""
    if not disagreement_analysis:
        return False
    for corr in disagreement_analysis.get("corrections", []):
        if corr.get("code_ai") == code and corr.get("code_correct"):
            return True
    return False


def _is_drg_sensitive_disagreement(code: str, disagreement_analysis: dict) -> bool:
    """Check if this code's disagreement is DRG-sensitive."""
    if not disagreement_analysis:
        return False
    for corr in disagreement_analysis.get("corrections", []):
        if corr.get("code_ai") == code and corr.get("drg_impacted", False):
            return True
    return False


def _determine_code_type(code: str, diagnosis_candidates: list[dict], procedure_candidates: list[dict], primary_diag_code: str) -> str:
    """Classify code risk type."""
    diag_codes = {c.get("code", "") for c in diagnosis_candidates}
    proc_codes = {c.get("code", "") for c in procedure_candidates}

    if code == primary_diag_code:
        return "primary_diagnosis"
    if code in diag_codes:
        if _is_unspecified(code):
            return "unspecified_code"
        return "secondary_diagnosis"
    if code in proc_codes:
        return "procedure_code"
    return "secondary_diagnosis"


# ── calibration ─────────────────────────────────────────────────────────────

def calibrate_confidence(
    code: str,
    code_name: str,
    raw_score: float,
    diagnosis_candidates: list[dict],
    procedure_candidates: list[dict],
    primary_diag_code: str,
    evidence_ranking: dict,
    disagreement_analysis: dict,
    primary_diag_reasoning: dict,
    negation: bool = False,
) -> dict:
    """Calibrate confidence for a single code.

    Returns CodingConfidence dict.
    """
    evidence_strength = _get_evidence_strength(code, evidence_ranking)
    rule_count = _get_rule_match_count(code, primary_diag_reasoning)
    in_disagreement = _is_in_disagreement(code, disagreement_analysis)
    is_unspecified = _is_unspecified(code)

    # Compute calibrated score
    inputs = {
        "raw_score": raw_score,
        "evidence_strength": evidence_strength,
        "rule_match_count": min(rule_count, 3),  # cap at 3
        "disagreement_penalty": 1.0 if in_disagreement else 0.0,
        "negation_penalty": 1.0 if negation else 0.0,
        "specificity_bonus": 0.0 if is_unspecified else 1.0,
    }

    calibrated = (
        INPUT_WEIGHTS["raw_score"] * inputs["raw_score"]
        + INPUT_WEIGHTS["evidence_strength"] * inputs["evidence_strength"]
        + INPUT_WEIGHTS["rule_match_count"] * (inputs["rule_match_count"] / 3.0)
        + INPUT_WEIGHTS["disagreement_penalty"] * inputs["disagreement_penalty"]
        + INPUT_WEIGHTS["negation_penalty"] * inputs["negation_penalty"]
        + INPUT_WEIGHTS["specificity_bonus"] * inputs["specificity_bonus"]
    )
    calibrated = _clamp(calibrated)

    code_type = _determine_code_type(code, diagnosis_candidates, procedure_candidates, primary_diag_code)

    parts = []
    if evidence_strength >= 0.6:
        parts.append("证据质量高")
    elif evidence_strength < 0.3:
        parts.append("证据质量不足")
    if rule_count >= 2:
        parts.append(f"匹配{rule_count}条规则")
    if in_disagreement:
        parts.append("存在分歧")
    if negation:
        parts.append("证据含否定描述")
    if is_unspecified:
        parts.append("编码特异性不足(.9)")

    return {
        "code": code,
        "code_type": code_type,
        "raw_score": raw_score,
        "calibrated_score": round(calibrated, 4),
        "inputs": {k: round(v, 4) if isinstance(v, float) else v for k, v in inputs.items()},
        "calibration_rationale": "; ".join(parts) if parts else "各输入因子处于正常范围",
    }


# ── routing ─────────────────────────────────────────────────────────────────

def route_code(
    confidence: dict,
    diagnosis_candidates: list[dict],
    procedure_candidates: list[dict],
    primary_diag_code: str,
    evidence_ranking: dict,
    disagreement_analysis: dict,
) -> dict:
    """Determine automation routing for a calibrated code.

    Returns RoutingDecision dict.
    """
    code = confidence["code"]
    cal_score = confidence["calibrated_score"]
    code_type = confidence["code_type"]
    risk_factors = []
    override_reason = ""

    # Base tier from calibrated score
    if cal_score >= 0.80:
        base_tier = RoutingTier.AUTO
    elif cal_score >= 0.50:
        base_tier = RoutingTier.REVIEW
    else:
        base_tier = RoutingTier.ESCALATE

    auto_eligible = base_tier == RoutingTier.AUTO

    # Policy overrides
    policy_min = RISK_TIER_POLICY.get(code_type, RoutingTier.REVIEW)

    # Unsupported code → escalate
    unsupported = {uc.get("code", "") for uc in evidence_ranking.get("unsupported_codes", [])}
    if code in unsupported:
        policy_min = RoutingTier.ESCALATE
        risk_factors.append("unsupported_evidence")

    # DRG-sensitive disagreement → escalate
    if _is_drg_sensitive_disagreement(code, disagreement_analysis):
        policy_min = RoutingTier.ESCALATE
        risk_factors.append("drg_sensitive")

    # .9 code → review minimum
    if _is_unspecified(code):
        policy_min = RoutingTier.REVIEW
        risk_factors.append("unspecified_code")

    # Primary diagnosis → review minimum
    if code == primary_diag_code:
        policy_min = RoutingTier.REVIEW
        risk_factors.append("primary_diagnosis")

    # Apply policy override
    tier_priority = {RoutingTier.ESCALATE: 3, RoutingTier.REVIEW: 2, RoutingTier.AUTO: 1}
    if tier_priority[policy_min] > tier_priority[base_tier]:
        override_reason = f"基础分层为{base_tier.value}，但风险评估要求最低{policy_min.value}（因素：{', '.join(risk_factors)}）"
        final_tier = policy_min
    else:
        final_tier = base_tier

    return {
        "code": code,
        "code_name": confidence.get("code", ""),
        "calibrated_score": cal_score,
        "tier": final_tier.value,
        "risk_factors": risk_factors,
        "override_reason": override_reason,
        "auto_eligible": auto_eligible and final_tier != RoutingTier.AUTO,
    }


# ── main entry point ────────────────────────────────────────────────────────

def calibrate_all(
    diagnosis_candidates: list[dict],
    procedure_candidates: list[dict],
    primary_diagnosis: dict,
    evidence_ranking: dict,
    disagreement_analysis: dict,
    primary_diag_reasoning: dict,
    gold_diagnosis_codes: Optional[list[str]] = None,
    gold_procedure_codes: Optional[list[str]] = None,
) -> dict:
    """Calibrate confidence and route all codes.

    Returns dict compatible with ConfidenceCalibrationResult.
    """
    primary_diag_code = primary_diagnosis.get("code", "") if primary_diagnosis else ""
    gold_diag_set = set(gold_diagnosis_codes or [])
    gold_proc_set = set(gold_procedure_codes or [])

    confidences = []
    routing_decisions = []

    # Calibrate diagnosis codes
    for c in diagnosis_candidates:
        code = c.get("code", "")
        if not code:
            continue
        conf = calibrate_confidence(
            code=code,
            code_name=c.get("name", ""),
            raw_score=c.get("score", 0.5),
            diagnosis_candidates=diagnosis_candidates,
            procedure_candidates=procedure_candidates,
            primary_diag_code=primary_diag_code,
            evidence_ranking=evidence_ranking,
            disagreement_analysis=disagreement_analysis,
            primary_diag_reasoning=primary_diag_reasoning,
            negation=c.get("negation", False),
        )
        confidences.append(conf)
        route = route_code(
            conf, diagnosis_candidates, procedure_candidates,
            primary_diag_code, evidence_ranking, disagreement_analysis,
        )
        route["code_name"] = c.get("name", "")
        routing_decisions.append(route)

    # Calibrate procedure codes
    for c in procedure_candidates:
        code = c.get("code", "")
        if not code:
            continue
        conf = calibrate_confidence(
            code=code,
            code_name=c.get("name", ""),
            raw_score=c.get("score", 0.5),
            diagnosis_candidates=diagnosis_candidates,
            procedure_candidates=procedure_candidates,
            primary_diag_code=primary_diag_code,
            evidence_ranking=evidence_ranking,
            disagreement_analysis=disagreement_analysis,
            primary_diag_reasoning=primary_diag_reasoning,
            negation=c.get("negation", False),
        )
        confidences.append(conf)
        route = route_code(
            conf, diagnosis_candidates, procedure_candidates,
            primary_diag_code, evidence_ranking, disagreement_analysis,
        )
        route["code_name"] = c.get("name", "")
        routing_decisions.append(route)

    # Metrics
    total = len(confidences)
    auto_count = sum(1 for r in routing_decisions if r["tier"] == "auto")
    review_count = sum(1 for r in routing_decisions if r["tier"] == "review")
    escalate_count = sum(1 for r in routing_decisions if r["tier"] == "escalate")
    override_count = sum(1 for r in routing_decisions if r.get("auto_eligible"))

    # Calibration error: if gold codes available, check correctness
    calibration_errors = []
    for conf in confidences:
        code = conf["code"]
        is_correct = code in gold_diag_set or code in gold_proc_set
        if gold_diag_set or gold_proc_set:
            error = abs(conf["calibrated_score"] - (1.0 if is_correct else 0.0))
            calibration_errors.append(error)

    false_confidence = 0.0
    if gold_diag_set or gold_proc_set:
        high_conf_wrong = sum(
            1 for conf in confidences
            if conf["calibrated_score"] >= 0.75
            and conf["code"] not in gold_diag_set
            and conf["code"] not in gold_proc_set
        )
        false_confidence = round(high_conf_wrong / total, 4) if total > 0 else 0.0

    metrics = {
        "total_codes": total,
        "auto_count": auto_count,
        "review_count": review_count,
        "escalate_count": escalate_count,
        "auto_accept_rate": round(auto_count / total, 4) if total > 0 else 0.0,
        "override_count": override_count,
        "calibration_error_avg": round(sum(calibration_errors) / len(calibration_errors), 4) if calibration_errors else 0.0,
        "false_confidence_rate": false_confidence,
    }

    return {
        "coding_confidences": confidences,
        "routing_decisions": routing_decisions,
        "metrics": metrics,
    }
