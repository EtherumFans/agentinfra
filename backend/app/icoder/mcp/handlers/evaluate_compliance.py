"""``evaluate_compliance`` MCP handler — Compliance Guardrail Agent wrapper.

Wraps ``official_agents.compliance_guardrail.agent.run()`` (the SSOT —
RuleEngine + guardrail heuristics CG-001..CG-004) as an MCP tool.

required_scopes: ``["compliance:evaluate"]`` (declared in TOOL_REGISTRY).
"""

from __future__ import annotations

import json as _json
from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    """Run the Compliance Guardrail Agent.

    Args (validated against EvaluateComplianceInput in TOOL_REGISTRY):
      - coding_set: dict — the coding set to evaluate. Required.
      - encounter_text: str — optional EMR text.

    Returns the ComplianceGuardrailOutputSchema dict:
      - review_conclusion: "PASS" | "WARNING" | "FAIL"
      - issues_found: list[dict]
      - manual_review_required: bool
      - drg_suggestion: str
      - reviewed_codes: list[dict]
      - compliance_checks: dict[str, bool]
      - rule_set: str
      - fired_rules: list[str]
      - trace_refs: dict
    """
    from official_agents.compliance_guardrail.agent import run as _run

    coding_set = arguments.get("coding_set") or {}
    encounter_text = arguments.get("encounter_text") or ""

    if isinstance(coding_set, dict):
        input_text = _json.dumps(coding_set, ensure_ascii=False)
    else:
        input_text = str(coding_set)
    if encounter_text:
        input_text = input_text + "\n" + str(encounter_text)

    run_id = getattr(request.state, "run_id", "") or ""
    result = await _run(input_text, run_id=run_id)
    return result


__all__ = ["handle"]
