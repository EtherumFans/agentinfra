"""Report tools — format_report, generate_cdi_query.

Tier 2 LLM-powered tools. Use LLM for natural language generation,
operating on data already verified by Tier 1 tools.
"""

from app.services.tool_registry import ToolDefinition, ToolTier
from app.services.llm_service import llm_service
from app.agents.experts.report_expert import ReportExpert

_report_expert = ReportExpert()


async def format_report(
    context: dict,
    format_type: str = "markdown",
) -> dict:
    """Generate a complete coding review report in the specified format.

    Uses ReportExpert which compiles all verified data into a structured report.
    """
    report_context = {
        "diagnosis_candidates": context.get("diagnosis_candidates", []),
        "procedure_candidates": context.get("procedure_candidates", []),
        "evidence_ranking": context.get("evidence_ranking", {}),
        "verification": context.get("verification", {}),
        "drg_impact": context.get("drg_impact", {}),
        "documentation_gaps": context.get("documentation_gaps", []),
        "confidence_calibration": context.get("confidence_calibration", {}),
        "human_checklist": context.get("human_checklist", []),
        "uncodable_items": context.get("uncodable_items", []),
    }

    result = await _report_expert.run(report_context)

    content = result.get(
        f"report_{format_type}",
        result.get("report_markdown", str(result)),
    )

    return {
        "report": content,
        "format": format_type,
        "human_checklist": result.get("human_checklist", []),
        "uncodable_items": result.get("uncodable_items", []),
    }


async def generate_cdi_query(gap: dict) -> dict:
    """Generate a compliant physician query for a specific documentation gap."""
    prompt = f"""Generate a compliant physician query for this documentation gap.

GAP: {gap.get('description', 'Unknown')}
SEVERITY: {gap.get('severity', 'medium')}
TYPE: {gap.get('type', 'specificity')}
IMPACT: {gap.get('impact', '')}

The query must:
1. Be non-leading (don't suggest the answer)
2. Cite the specific documentation deficiency
3. Explain the clinical/regulatory impact
4. Use standard CDI query format

Respond with JSON:
{{"query": "the actual query text",
 "rationale": "why this query is needed",
 "drg_impact": "low|medium|high"}}"""

    result = await llm_service.extract_json(prompt=prompt, text="", schema_hint="cdi query")
    return {
        "query": result.get("query", ""),
        "rationale": result.get("rationale", ""),
        "drg_impact": result.get("drg_impact", "low"),
    }


REPORT_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        id="format_report",
        name="报告生成",
        description=(
            "生成完整的编码审核报告（Markdown/HTML）。"
            "汇总所有已验证的编码、证据排名、DRG分析、文档缺口。"
        ),
        tier=ToolTier.LLM_REASONING,
        category="report",
        icon="FileText",
        requires=[
            "state.has('diagnosis_candidates') and state.has('evidence_ranking')",
        ],
        guarantees={
            "output.report": "non-empty string (min 50 chars)",
            "output.human_checklist": "list of human review tasks",
        },
        executor=format_report,
        accuracy_tags=[],
        is_injectable=False,
    ),
    ToolDefinition(
        id="generate_cdi_query",
        name="CDI查询生成",
        description="为特定文档缺口生成符合规范的医师查询。",
        tier=ToolTier.LLM_REASONING,
        category="report",
        icon="MessageSquare",
        requires=["state.has('documentation_gaps')"],
        guarantees={
            "output.query": "non-empty string",
            "output.drg_impact": "low|medium|high",
        },
        executor=generate_cdi_query,
        accuracy_tags=["cdi"],
        is_injectable=False,
    ),
]
