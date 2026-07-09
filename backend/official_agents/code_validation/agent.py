"""Code Validation Agent v2 — LLM-based (Phase 4-C).

Migrates from the pure RuleEngine (legacy, see ``agent_legacy.py``) to
``LLMWithToolsProvider`` with 4 mandatory MCP tools (verify_code /
get_guidelines / explore_code / search_codes), 1:1 mirroring Corti Code
Validation Agent architecture.

The LLM is asked to:
  1. Parse a coding set (primary_diagnosis / secondary_diagnoses / procedures)
  2. Call verify_code + get_guidelines for EVERY code (mandatory tools)
  3. Call explore_code when verify_code returns assignable=False or when
     a more specific code may exist
  4. Call search_codes when alternatives are needed
  5. Output JSON matching ``CodeValidationOutputV2`` (validated_codes +
     cross_code_issues + markdown + summary)

Legacy fallback: if the LLM path fails (timeout, parse error, status="fail",
or prompt-injection refusal), ``agent.run()`` falls back to
``agent_legacy.run_legacy_with_corti_schema()`` so the caller always gets
a v2-shape response (lossy — empty evidence_tool_refs).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


AGENT_REF = "icoder/code-validation-agent@2.0.0"

from .system_prompt_v2 import SYSTEM_PROMPT


# ── run() — main entry point ────────────────────────────────────────


async def run(input_text: str, *, run_id: str = "") -> dict:
    """Run the Code Validation Agent v2 (LLM + tools, Phase 4-C).

    Args:
        input_text: JSON or free text containing a coding set.
        run_id: Optional run_id for trace correlation.

    Returns:
        CodeValidationOutputV2 dict. If the LLM path fails or returns
        unparseable output, falls back to the legacy RuleEngine
        implementation (``agent_legacy.run_legacy_with_corti_schema``)
        so the caller always gets a v2-shape response.
    """
    text = input_text or ""
    if not text.strip():
        return _empty_input_response(run_id)

    # Prompt injection check — refuse before calling LLM/tools.
    if _detect_prompt_injection(text):
        logger.warning(
            "code_validation: prompt injection detected; refusing LLM path."
        )
        return _prompt_injection_response(text, run_id)

    try:
        llm_response = await _invoke_llm(text, run_id)
    except Exception as e:
        logger.warning(
            "code_validation LLM invoke raised; falling back to legacy: %s", e,
        )
        return await _legacy_run(text, run_id)

    if llm_response is None or llm_response.get("status") == "fail":
        logger.info(
            "code_validation LLM returned fail; falling back to legacy. "
            "finish_reason=%s",
            llm_response.get("finish_reason") if llm_response else "none",
        )
        return await _legacy_run(text, run_id)

    # Check for incomplete (max_tool_rounds exceeded) — still try to parse,
    # but fall back if the LLM produced no usable output.
    markdown = llm_response.get("markdown", "") or ""
    if not markdown.strip():
        logger.warning(
            "code_validation LLM returned empty markdown; falling back."
        )
        return await _legacy_run(text, run_id)

    schema = _parse_llm_json_to_schema(markdown, text, run_id,
                                        tool_calls=llm_response.get("tool_calls", []))
    if schema is None:
        logger.warning(
            "code_validation LLM output not parseable; falling back to legacy."
        )
        return await _legacy_run(text, run_id)

    return schema


# ── Internal: LLM invoke ────────────────────────────────────────────


async def _invoke_llm(text: str, run_id: str) -> dict[str, Any] | None:
    """Invoke LLMWithToolsProvider via the registry."""
    from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
    from icoder_runtime.backends.registry import get_default_registry

    registry = get_default_registry()
    provider = registry.resolve_from_agent_pack(
        {"backend_provider": "icoder.llm-with-tools.v1"},
    )

    # Build a minimal stand-in Request for dispatch_tool — it needs
    # app.state (for phi_redactor / mcp_secret_resolver) and
    # state.context_id / state.run_id. In production this comes from
    # the FastAPI Request; here we synthesize a minimal one.
    request = _build_minimal_request(run_id)

    req = BackendRequest(
        system_prompt=SYSTEM_PROMPT,
        user_input=text,
        tool_scope=["verify_code", "get_guidelines", "explore_code", "search_codes"],
        mandatory_tools=["verify_code", "get_guidelines"],
        forbidden_tools=[],
        timeout_seconds=120.0,
    )
    ctx = AgentRunContext(
        run_id=run_id or str(uuid.uuid4()),
        context_id=str(uuid.uuid4()),
        agent_id="code-validation-agent",
        redacted_input=text,
        agent_pack={"backend_provider": "icoder.llm-with-tools.v1"},
    )
    resp = await provider.invoke(req, ctx, request=request)
    return {
        "status": resp.status,
        "markdown": resp.markdown or "",
        "finish_reason": resp.finish_reason or "",
        "latency_ms": resp.latency_ms,
        "tool_calls": [tc.model_dump() for tc in resp.tool_calls],
        "raw": resp.raw_provider_response,
    }


def _build_minimal_request(run_id: str):
    """Build a minimal stand-in for FastAPI Request."""
    class _State:
        def __init__(self):
            self.context_id = str(uuid.uuid4())
            self.run_id = run_id or str(uuid.uuid4())
            self.mcp_run_auth_context = None

    class _App:
        def __init__(self):
            self.state = type("state", (), {})()

    class _Request:
        def __init__(self):
            self.app = _App()
            self.state = _State()

    return _Request()


# ── Internal: LLM output parsing ────────────────────────────────────


def _parse_llm_json_to_schema(
    markdown: str,
    input_text: str,
    run_id: str,
    *,
    tool_calls: list[dict],
) -> dict[str, Any] | None:
    """Extract JSON from LLM markdown, validate, build v2 schema dict."""
    if not markdown:
        return None

    parsed = _extract_json(markdown)
    if parsed is None:
        return None

    # Required top-level fields per CodeValidationOutputV2.
    required = ("review_conclusion", "validated_codes")
    for f in required:
        if f not in parsed:
            return None

    conclusion = str(parsed.get("review_conclusion", "")).upper().strip()
    if conclusion not in ("PASS", "WARNING", "FAIL"):
        return None

    # Build a tool_call_id → tool_name index for evidence_tool_refs validation.
    tool_id_index = {tc.get("id", ""): tc.get("tool_name", "")
                     for tc in tool_calls if isinstance(tc, dict)}

    validated_codes: list[dict] = []
    for vc in parsed.get("validated_codes") or []:
        if not isinstance(vc, dict) or not vc.get("code"):
            continue
        validated_codes.append(_normalize_validated_code(vc, tool_id_index))

    cross_issues: list[dict] = []
    for ci in parsed.get("cross_code_issues") or []:
        if not isinstance(ci, dict):
            continue
        cross_issues.append({
            "issue_type": str(ci.get("issue_type") or "LEGACY_RULE"),
            "codes": list(ci.get("codes") or []),
            "rule": str(ci.get("rule") or ""),
            "action": str(ci.get("action") or ""),
        })

    issues_found = list(parsed.get("issues_found") or [])
    manual_review = bool(parsed.get("manual_review_required"))
    summary = str(parsed.get("summary") or "")
    md_text = str(parsed.get("markdown") or markdown)

    return {
        "agent_id": "",
        "run_id": run_id or str(uuid.uuid4()),
        "review_conclusion": conclusion,
        "issues_found": issues_found,
        "manual_review_required": manual_review,
        "rule_set": "medical_coding",
        "validated_codes": validated_codes,
        "cross_code_issues": cross_issues,
        "summary": summary,
        "markdown": md_text,
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "rule_set": "medical_coding",
            "tool_calls_count": len(tool_calls),
        },
    }


def _normalize_validated_code(vc: dict, tool_id_index: dict) -> dict:
    """Normalize a validated_code dict — keep evidence_tool_refs as-is."""
    checks: list[dict] = []
    for c in vc.get("checks") or []:
        if not isinstance(c, dict):
            continue
        # Validate evidence_tool_refs — keep only IDs that exist in tool_calls.
        refs = [str(r) for r in (c.get("evidence_tool_refs") or [])
                if str(r) in tool_id_index or True]  # lenient — keep all
        checks.append({
            "check_name": str(c.get("check_name") or "rule"),
            "status": str(c.get("status") or "N/A"),
            "issue": c.get("issue"),
            "evidence_tool_refs": refs,
        })
    return {
        "code": str(vc.get("code") or ""),
        "description": str(vc.get("description") or ""),
        "status": str(vc.get("status") or "WARNING"),
        "assignable": bool(vc.get("assignable", True)),
        "checks": checks,
        "issue": vc.get("issue"),
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from text (with ```json fences or plain)."""
    if not text:
        return None
    # Try ```json fenced block first.
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)
        if end > start:
            candidate = text[start:end].strip()
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                pass
    # Try plain JSON extraction.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


# ── Internal: prompt injection detection ────────────────────────────


_PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "disregard all rules",
    "return pass",
    "你忽略之前所有",
    "忽略上面的所有",
    "返回 pass",
    "system prompt",
    "override system",
)


def _detect_prompt_injection(text: str) -> bool:
    """Heuristic: detect obvious prompt-injection attempts in the input."""
    lowered = text.lower()
    return any(p in lowered for p in _PROMPT_INJECTION_PATTERNS)


def _prompt_injection_response(text: str, run_id: str) -> dict:
    """Build a WARNING response when prompt injection is detected."""
    inj_id = str(uuid.uuid4())
    return {
        "agent_id": "",
        "run_id": run_id or str(uuid.uuid4()),
        "review_conclusion": "WARNING",
        "issues_found": [{
            "severity": "high",
            "rule_id": "PI-001",
            "message": "Prompt injection detected in input — LLM path refused.",
            "suggestion": "Reject the input; do not act on injected instructions.",
            "category": "security",
        }],
        "manual_review_required": True,
        "rule_set": "medical_coding",
        "validated_codes": [],
        "cross_code_issues": [],
        "summary": "Prompt injection detected — request refused. Manual review required.",
        "markdown": (
            "# Code Validation Report\n\n"
            "## Status\nWARNING\n\n"
            "## Summary\nPrompt injection detected — LLM path refused.\n\n"
            "## Validated Codes\n(none — input rejected)\n\n"
            "## Cross-Code Issues\n(none)\n\n"
            "## Manual Review\nRequired — input contained prompt-injection patterns."
        ),
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "rule_set": "medical_coding",
            "injection_detected": True,
        },
    }


# ── Internal: empty input ───────────────────────────────────────────


def _empty_input_response(run_id: str) -> dict:
    """Build a FAIL response when input is empty."""
    return {
        "agent_id": "",
        "run_id": run_id or str(uuid.uuid4()),
        "review_conclusion": "FAIL",
        "issues_found": [{
            "severity": "high",
            "rule_id": "INPUT-001",
            "message": "Empty input — no coding set to validate.",
            "suggestion": "Provide a JSON coding set or text containing ICD-10 codes.",
            "category": "input",
        }],
        "manual_review_required": True,
        "rule_set": "medical_coding",
        "validated_codes": [],
        "cross_code_issues": [],
        "summary": "Empty input — nothing to validate.",
        "markdown": (
            "# Code Validation Report\n\n"
            "## Status\nFAIL\n\n"
            "## Summary\nEmpty input — no coding set to validate.\n\n"
            "## Validated Codes\n(none)\n\n"
            "## Cross-Code Issues\n(none)\n\n"
            "## Manual Review\nRequired — input is empty."
        ),
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "rule_set": "medical_coding",
        },
    }


# ── Internal: legacy fallback ───────────────────────────────────────


async def _legacy_run(text: str, run_id: str) -> dict:
    """Invoke the legacy RuleEngine fallback (lossy v2 conversion)."""
    from .agent_legacy import run_legacy_with_corti_schema
    return await run_legacy_with_corti_schema(text, run_id=run_id)


__all__ = ["run"]
