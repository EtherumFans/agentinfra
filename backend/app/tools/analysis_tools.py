"""Analysis tools — analyze_drg_impact, check_documentation_gaps, cdi_review.

Tier 2 LLM-powered tools. Use LLM for analysis but operate on verified data.
"""

from app.services.tool_registry import ToolDefinition, ToolTier
from app.agents.experts.drg_expert import DRGDIPExpert, DocumentationGapExpert
from app.agents.experts.cdi_expert import CDIExpert

_drg_expert = DRGDIPExpert()
_doc_gap_expert = DocumentationGapExpert()
_cdi_expert = CDIExpert()


async def analyze_drg_impact(
    diagnosis_codes: list[dict] = None,
    procedure_codes: list[dict] = None,
    primary_diagnosis: dict = None,
    evidence_ranking: dict = None,
) -> dict:
    """Analyze DRG/DIP payment impact of the assigned codes."""
    context = {
        "diagnosis_candidates": diagnosis_codes or [],
        "procedure_candidates": procedure_codes or [],
        "primary_diagnosis": primary_diagnosis or {},
        "evidence_ranking": evidence_ranking or {},
    }
    result = await _drg_expert.run(context)
    return {
        "drg_impact": result.get("drg_impact", {}),
        "mcc_cc_analysis": result.get("mcc_cc_analysis", []),
        "grouping_risk": result.get("grouping_risk", "low"),
        "recommendations": result.get("recommendations", []),
    }


async def check_documentation_gaps(
    documents: list[dict] = None,
    evidence_ranking: dict = None,
    verification: dict = None,
) -> dict:
    """Identify missing or incomplete documentation that affects coding accuracy."""
    context = {
        "documents": documents or [],
        "evidence_ranking": evidence_ranking or {},
        "verification": verification or {},
    }
    result = await _doc_gap_expert.run(context)
    return {
        "documentation_gaps": result.get("documentation_gaps", []),
        "suggestions_for_clinicians": result.get("suggestions_for_clinicians", []),
    }


async def cdi_review(
    evidence: dict = None,
    diagnosis_candidates: list[dict] = None,
    documentation_gaps: list[dict] = None,
) -> dict:
    """Clinical Documentation Improvement review — identify and query documentation gaps."""
    context = {
        "evidence": evidence or {},
        "diagnosis_candidates": diagnosis_candidates or [],
        "documentation_gaps": documentation_gaps or [],
    }
    result = await _cdi_expert.run(context)
    return {
        "recommendations": result.get("recommendations", []),
        "impact_summary": result.get("impact_summary", ""),
    }


ANALYSIS_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        id="analyze_drg_impact",
        name="DRG/DIP影响分析",
        description=(
            "分析编码方案对DRG分组和医保支付的影响。"
            "检测分组风险、MCC/CC遗漏、诊断-手术不匹配。"
        ),
        tier=ToolTier.LLM_REASONING,
        category="analysis",
        icon="PieChart",
        requires=["state.has('diagnosis_candidates')"],
        guarantees={
            "output.drg_impact": "dict with expected_drg, weight, payment_impact",
            "output.recommendations": "list of DRG-related recommendations",
        },
        executor=analyze_drg_impact,
        accuracy_tags=["drg_validation"],
        is_injectable=False,
    ),
    ToolDefinition(
        id="check_documentation_gaps",
        name="文档缺口检查",
        description="识别缺失或不完整的文档，生成给临床医生的补充建议。",
        tier=ToolTier.LLM_REASONING,
        category="analysis",
        icon="FileWarning",
        requires=[],
        guarantees={
            "output.documentation_gaps": "list with severity, type, description",
        },
        executor=check_documentation_gaps,
        accuracy_tags=["cdi"],
        is_injectable=False,
    ),
    ToolDefinition(
        id="cdi_review",
        name="临床文档改进审查",
        description="审查临床文档质量，识别编码特异性和文档完整性改进机会。",
        tier=ToolTier.LLM_REASONING,
        category="analysis",
        icon="ClipboardList",
        requires=[],
        guarantees={
            "output.recommendations": "list with target, gap, impact, query",
        },
        executor=cdi_review,
        accuracy_tags=["cdi"],
        is_injectable=False,
    ),
]
