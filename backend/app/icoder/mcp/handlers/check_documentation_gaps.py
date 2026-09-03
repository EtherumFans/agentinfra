"""``check_documentation_gaps`` MCP handler — Note Completeness Agent wrapper.

Wraps ``official_agents.note_completeness.agent.run()`` (the SSOT —
regex-based EMR section detection) as an MCP tool.

required_scopes: ``["documentation:check"]`` (declared in TOOL_REGISTRY).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    """Run the Note Completeness Agent.

    Args (validated against CheckDocumentationGapsInput in TOOL_REGISTRY):
      - encounter_text: str — the EMR text to check. Required.

    Returns the NoteCompletenessOutputSchema dict:
      - completeness_score: float
      - missing_sections: list[str]
      - present_sections: list[str]
      - supplement_suggestions: list[dict]
      - coding_drg_dip_impact: dict
      - trace_refs: dict
    """
    from official_agents.note_completeness.agent import run as _run

    encounter_text = arguments.get("encounter_text") or ""
    input_text = str(encounter_text)

    run_id = getattr(request.state, "run_id", "") or ""
    result = await _run(input_text, run_id=run_id)
    return result


__all__ = ["handle"]
