"""Safety tools — guard_input, guard_output.

Tier 1 deterministic tools. Zero LLM involvement.
These are always auto-injected by the harness.
"""

from app.services.tool_registry import ToolDefinition, ToolTier
from app.services.guardrails import guardrails


async def guard_input(text: str) -> dict:
    """Validate user input against safety rules (PHI, blocked terms, length)."""
    result = await guardrails.validate_input(text)
    return {
        "valid": result["valid"],
        "violations": [
            {"rule": v["rule"], "severity": v["severity"], "message": v["message"]}
            for v in result.get("violations", [])
        ],
    }


async def guard_output(text: str) -> dict:
    """Validate agent output against safety rules (no prescriptions, no triage)."""
    result = await guardrails.validate_output(text)
    return {
        "valid": result["valid"],
        "requires_disclaimer": result.get("requires_disclaimer", False),
        "violations": [
            {"rule": v["rule"], "severity": v["severity"], "message": v["message"]}
            for v in result.get("violations", [])
        ],
    }


SAFETY_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        id="guard_input",
        name="输入安全验证",
        description="检测输入中的PHI、敏感词、长度异常。阻断危险输入。",
        tier=ToolTier.DETERMINISTIC,
        category="safety",
        icon="Shield",
        requires=[],
        guarantees={
            "output.valid": "bool",
            "output.violations": "list of violation dicts",
        },
        executor=guard_input,
        accuracy_tags=["safety"],
        is_injectable=True,
    ),
    ToolDefinition(
        id="guard_output",
        name="输出安全验证",
        description="检测输出中的处方建议、用药推荐、手术方案等阻断词。",
        tier=ToolTier.DETERMINISTIC,
        category="safety",
        icon="Shield",
        requires=["guard_input"],  # Must have passed input guard first
        guarantees={
            "output.valid": "bool",
        },
        executor=guard_output,
        accuracy_tags=["safety"],
        is_injectable=True,
    ),
]
