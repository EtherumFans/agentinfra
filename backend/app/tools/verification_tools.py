"""Verification tools — rank_evidence, calibrate_confidence, verify_evidence, analyze_disagreements.

Tier 1 deterministic: rank_evidence, calibrate_confidence (pure algorithms, zero LLM)
Tier 2 LLM-powered: verify_evidence (LLM verification with deterministic cross-check)
"""

from app.services.tool_registry import ToolDefinition, ToolTier
from app.services.evidence_ranker import rank_all_evidence
from app.services.confidence_calibrator import calibrate_all
from app.services.disagreement_analyzer import analyze_disagreements
from app.agents.experts.drg_expert import EvidenceVerificationExpert

_evidence_verify_expert = EvidenceVerificationExpert()


async def rank_evidence_tool(
    diagnosis_candidates: list[dict] = None,
    procedure_candidates: list[dict] = None,
    evidence_facts: list[dict] = None,
    procedure_facts: list[dict] = None,
    admission_reason: str = "",
    timeline: dict = None,
    primary_diagnosis: dict = None,
    existing_diagnosis_codes: list[str] = None,
) -> dict:
    """Deterministic evidence strength ranking with conflict detection. Zero LLM.

    Scores each code candidate against available evidence and detects conflicts.
    """
    diagnosis_candidates = diagnosis_candidates or []
    procedure_candidates = procedure_candidates or []
    evidence_facts = evidence_facts or []
    procedure_facts = procedure_facts or []

    result = rank_all_evidence(
        diagnosis_candidates=diagnosis_candidates,
        procedure_candidates=procedure_candidates,
        evidence_facts=evidence_facts,
        procedure_facts=procedure_facts,
        admission_reason=admission_reason,
        timeline=timeline or {},
        primary_diagnosis=primary_diagnosis or {},
        existing_diagnosis_codes=existing_diagnosis_codes or [],
    )

    return {
        "ranked_candidates": [
            {
                "code": r.get("code", ""),
                "name": r.get("name", ""),
                "strength_score": r.get("strength_score", 0),
                "evidence_category": r.get("evidence_category", "unsupported"),
            }
            for r in result.get("top_supporting_evidence", [])
        ],
        "unsupported_codes": result.get("unsupported_codes", []),
        "conflicts": result.get("conflicts", []),
        "total_ranked": len(result.get("top_supporting_evidence", [])),
    }


async def calibrate_confidence_tool(
    candidates: list[dict] = None,
    evidence_ranking: dict = None,
    routing_policy: dict = None,
) -> dict:
    """Deterministic confidence calibration. Zero LLM.

    Assigns each code to AUTO/REVIEW/ESCALATE tier based on evidence strength,
    coding rules compliance, and risk tier policy.
    """
    candidates = candidates or []

    result = calibrate_all(
        diagnosis_candidates=[
            c for c in candidates if c.get("code_type") != "procedure"
        ],
        procedure_candidates=[
            c for c in candidates if c.get("code_type") == "procedure"
        ],
    )

    return {
        "routing_decisions": [
            {
                "code": r.get("code", ""),
                "tier": r.get("tier", "review"),
                "confidence": r.get("confidence", 0.5),
                "reason": r.get("reason", ""),
            }
            for r in result.get("routing_decisions", [])
        ],
    }


async def verify_evidence_tool(context: dict) -> dict:
    """Verify each code candidate has supporting evidence in the medical record.

    Uses LLM for verification with deterministic cross-check.
    """
    result = await _evidence_verify_expert.run(context)
    verifications = result.get("verifications", [])
    summary = result.get("summary", {})

    return {
        "verifications": [
            {
                "code": v.get("code", ""),
                "name": v.get("name", ""),
                "status": v.get("status", "needs_review"),
                "evidence_quality": v.get("evidence_quality", "none"),
                "confidence": v.get("confidence", 0),
                "reason": v.get("reason", ""),
            }
            for v in verifications
        ],
        "summary": {
            "total_codes": summary.get("total_codes", 0),
            "supported": summary.get("supported", 0),
            "unsupported": summary.get("unsupported", 0),
            "needs_review": summary.get("needs_review", 0),
            "evidence_binding_rate": summary.get("evidence_binding_rate", 0),
        },
    }


async def analyze_disagreements_tool(
    candidates: list[dict] = None,
    gold_diagnosis_codes: list[str] = None,
    gold_procedure_codes: list[str] = None,
) -> dict:
    """Analyze disagreements between AI output and gold standard codes. Zero LLM."""
    result = analyze_disagreements(
        candidates=candidates or [],
        gold_diagnosis_codes=gold_diagnosis_codes or [],
        gold_procedure_codes=gold_procedure_codes or [],
    )

    return {
        "disagreements": result.get("disagreements", []),
        "agreement_rate": result.get("agreement_rate", 0),
        "total_comparisons": result.get("total_comparisons", 0),
    }


VERIFICATION_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        id="rank_evidence",
        name="证据排名与冲突检测",
        description=(
            "对所有编码候选的证据强度进行排名，检测证据冲突。"
            "纯确定性算法——零LLM参与。"
        ),
        tier=ToolTier.DETERMINISTIC,
        category="verification",
        icon="BarChart3",
        requires=[
            "state.has('diagnosis_candidates') or state.has('procedure_candidates')",
        ],
        guarantees={
            "output.ranked_candidates": "non-empty: list with strength_score",
            "output.unsupported_codes": "non-empty: list of codes with zero evidence",
            "output.conflicts": "non-empty: list of conflicting evidence pairs",
        },
        executor=rank_evidence_tool,
        accuracy_tags=["evidence_binding", "conflict_detection"],
        is_injectable=True,
    ),
    ToolDefinition(
        id="calibrate_confidence",
        name="置信度校准",
        description=(
            "根据证据排名结果，将每个编码分配到 AUTO/REVIEW/ESCALATE 三级。"
            "纯确定性算法——零LLM参与。"
        ),
        tier=ToolTier.DETERMINISTIC,
        category="verification",
        icon="Target",
        requires=["state.has('evidence_ranking')"],
        guarantees={
            "output.routing_decisions": "non-empty: each with tier and confidence",
        },
        executor=calibrate_confidence_tool,
        accuracy_tags=["calibration"],
        is_injectable=True,
    ),
    ToolDefinition(
        id="verify_evidence",
        name="证据验证",
        description="验证每个编码候选是否有病历中的支持证据，评估证据质量。",
        tier=ToolTier.LLM_REASONING,
        category="verification",
        icon="CheckCircle",
        requires=["state.has('diagnosis_candidates') or state.has('procedure_candidates')"],
        guarantees={
            "output.verifications": "non-empty: list with status and evidence_quality",
            "output.summary": "non-empty: dict with evidence_binding_rate",
        },
        executor=verify_evidence_tool,
        accuracy_tags=["evidence_binding"],
        is_injectable=False,
    ),
    ToolDefinition(
        id="analyze_disagreements",
        name="分歧分析",
        description="将AI编码结果与金标准编码对比，计算一致率和分歧类型。零LLM。",
        tier=ToolTier.DETERMINISTIC,
        category="verification",
        icon="GitCompare",
        requires=["state.has('diagnosis_candidates')"],
        guarantees={
            "output.agreement_rate": "float between 0 and 1",
        },
        executor=analyze_disagreements_tool,
        accuracy_tags=["calibration"],
        is_injectable=True,
    ),
]
