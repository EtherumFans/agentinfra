"""``validate_codes`` MCP handler — Code Validation Agent wrapper (v1).

Wraps ``official_agents.code_validation.agent_legacy.run_legacy()``
(the deterministic RuleEngine — R001-R010 + MC-R-M80-001) as an MCP
tool that returns the v1 output shape (``fired_rules`` +
``code_assignment_summary`` + ``trace_refs``).

Phase 4-C: the main ``code_validation/agent.py`` was migrated to
LLMWithToolsProvider + 4 MCP tools and now produces v2 shape
(``validated_codes`` + ``cross_code_issues`` + ``markdown``). To
preserve the v1 contract for existing ``validate_codes`` MCP
consumers (other agents that depend on the v1 schema), this handler
delegates to ``agent_legacy.run_legacy()`` instead of the new
``agent.run()``.

required_scopes: ``["coding:validate"]`` (declared in TOOL_REGISTRY).
"""

from __future__ import annotations

import json as _json
from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    """Run the Code Validation Agent (v1 shape — RuleEngine, no LLM).

    Args (validated against ValidateCodesInput in TOOL_REGISTRY):
      - coding_set: dict — the coding set to validate (primary_diagnosis /
        secondary_diagnoses / procedures). Required.
      - encounter_text: str — optional EMR text for context-aware rules.

    Returns the CodeValidationOutputSchema v1 dict:
      - review_conclusion: "PASS" | "WARNING" | "FAIL"
      - issues_found: list[dict]
      - manual_review_required: bool
      - rule_set: "medical_coding"
      - fired_rules: list[str]
      - code_assignment_summary: dict
      - trace_refs: dict
    """
    from official_agents.code_validation.agent_legacy import run_legacy as _run

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
