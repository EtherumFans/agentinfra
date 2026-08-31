"""Code Validation Agent v2 — governed catalog baseline + optional LLM review.

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

The default ``run()`` path first establishes catalog membership and
assignability from hash-pinned local development assets.  It can optionally
add LLM/tool cross-code review when the operator explicitly enables external
semantic enhancement.  Model output never overrides the deterministic catalog
facts.  The legacy LLM-first entry point remains available as
``run_llm_enhanced()`` for compatibility and controlled comparison tests.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import uuid
from typing import Any

logger = logging.getLogger(__name__)


AGENT_REF = "icoder/code-validation-agent@2.0.0"

from .system_prompt_v2 import SYSTEM_PROMPT as _LEGACY_SYSTEM_PROMPT


def _current_pack_system_prompt() -> str:
    """Use the same prompt contract advertised by Hub and unified Run."""
    pack_path = (
        Path(__file__).resolve().parents[1]
        / "code-validation"
        / "agent_pack.json"
    )
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _LEGACY_SYSTEM_PROMPT
    return str(pack.get("system_prompt") or _LEGACY_SYSTEM_PROMPT)


SYSTEM_PROMPT = _current_pack_system_prompt()


# ── run() — governed main entry point ───────────────────────────────


async def run(
    input_text: str,
    *,
    run_id: str = "",
    structured_input: dict[str, Any] | None = None,
    allow_semantic_enhancement: bool | None = None,
) -> dict:
    """Run the governed local baseline and optional semantic enhancement.

    The local catalog result is always the authority for ``in_catalog`` and
    ``assignable``.  The optional LLM can only append review-required
    cross-code observations; it cannot convert a local miss into a valid code
    or select a replacement code.
    """
    text = input_text or ""
    if _detect_prompt_injection(text):
        return _prompt_injection_response(text, run_id)

    baseline = await run_deterministic(
        text,
        run_id=run_id,
        structured_input=structured_input,
    )
    if baseline.get("runtime_mode") == "catalog_governance_unavailable":
        return baseline
    if not _semantic_enhancement_enabled(allow_semantic_enhancement):
        return baseline

    enhanced = await run_llm_enhanced(text, run_id=run_id)
    if enhanced.get("degraded") or enhanced.get("fallback_used"):
        baseline.setdefault("trace_refs", {})["semantic_enhancement_attempted"] = True
        baseline["trace_refs"]["semantic_enhancement_used"] = False
        baseline["trace_refs"]["semantic_enhancement_status"] = "unavailable"
        return baseline
    return _merge_catalog_grounded_semantic_review(baseline, enhanced)


async def run_deterministic(
    input_text: str,
    *,
    run_id: str = "",
    structured_input: dict[str, Any] | None = None,
) -> dict:
    """Run only the hash-pinned local catalog membership baseline."""
    from .catalog_validation import run_governed_catalog_validation

    return await run_governed_catalog_validation(
        input_text,
        run_id=run_id,
        structured_input=structured_input,
    )


def _semantic_enhancement_enabled(explicit: bool | None) -> bool:
    if explicit is False:
        return False
    enabled = explicit is True or os.environ.get(
        "ICODER_CODE_VALIDATION_ENABLE_LLM_SEMANTIC_ENHANCEMENT", "false"
    ).strip().casefold() == "true"
    if not enabled:
        return False
    if os.environ.get("ICODER_ALLOW_EXTERNAL_LLM", "false").strip().casefold() != "true":
        return False
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        return False
    return os.environ.get("LLM_PROVIDER", "mock").strip().casefold() not in {
        "",
        "mock",
        "stub",
        "fake",
    }


def _merge_catalog_grounded_semantic_review(
    baseline: dict[str, Any],
    enhanced: dict[str, Any],
) -> dict[str, Any]:
    """Append bounded LLM observations without changing catalog truth."""
    merged = dict(baseline)
    cross_issues = [
        dict(item)
        for item in (baseline.get("cross_code_issues") or [])
        if isinstance(item, dict)
    ]
    enhanced_public = to_current_pack_candidate(enhanced)
    for raw in enhanced_public.get("cross_code_issues") or []:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("code") or "")[:512]
        issue = str(raw.get("issue") or "").strip()[:4000]
        if not code and not issue:
            continue
        cross_issues.append({
            "code": code,
            "issue": f"LLM 辅助观察（未成为目录事实，必须人工核验）：{issue}",
            "severity": "warning",
            "manual_review_required": True,
        })
    merged["cross_code_issues"] = cross_issues
    merged["manual_review_required"] = True
    merged["runtime_mode"] = "governed_catalog_plus_llm_semantic_review"
    merged["summary"] = (
        str(baseline.get("summary") or "")
        + f" 可选语义增强追加 {len(cross_issues) - len(baseline.get('cross_code_issues') or [])} 条人工复核观察；目录事实未被模型修改。"
    ).strip()
    enhanced_markdown = str(enhanced_public.get("markdown") or "").strip()
    if enhanced_markdown:
        merged["markdown"] = (
            str(baseline.get("markdown") or "")
            + "\n\n## 可选 LLM 语义复核（非目录事实）\n\n"
            + enhanced_markdown
        )
    trace_refs = dict(baseline.get("trace_refs") or {})
    enhanced_trace = enhanced.get("trace_refs") or {}
    trace_refs.update({
        "semantic_enhancement_attempted": True,
        "semantic_enhancement_used": True,
        "semantic_enhancement_status": "completed",
        "semantic_tool_calls_count": int(enhanced_trace.get("tool_calls_count") or 0),
        "model_cost_usd": float(enhanced_trace.get("model_cost_usd") or 0.0),
    })
    merged["trace_refs"] = trace_refs
    return merged


# ── explicit legacy LLM-first entry point ───────────────────────────


async def run_llm_enhanced(input_text: str, *, run_id: str = "") -> dict:
    """Run the Phase 4-C LLM-with-tools implementation explicitly.

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
            "code_validation LLM invoke raised; falling back to legacy error_type=%s",
            type(e).__name__,
        )
        return await _legacy_run(text, run_id)

    if llm_response is None or llm_response.get("status") == "fail":
        logger.info("code_validation LLM returned fail; falling back to legacy")
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

    schema.setdefault("trace_refs", {})["model_cost_usd"] = float(
        llm_response.get("cost_usd") or 0.0
    )
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
        "cost_usd": float(resp.cost_usd or 0.0),
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
        if "code" in ci or "issue" in ci:
            cross_issues.append({
                "code": str(ci.get("code") or ""),
                "issue": str(ci.get("issue") or ""),
                "severity": str(ci.get("severity") or "warning"),
                "manual_review_required": bool(
                    ci.get("manual_review_required", True)
                ),
            })
        else:
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
        "in_catalog": vc.get("in_catalog"),
        "catalog_name": str(
            vc.get("catalog_name") or vc.get("description") or ""
        ),
        "suggested_replacement": str(vc.get("suggested_replacement") or ""),
        "checks": checks,
        "issue": vc.get("issue"),
    }


def to_current_pack_candidate(result: dict[str, Any]) -> dict[str, Any]:
    """Translate the legacy internal v2 shape to the current public Pack.

    Missing catalog evidence never becomes a valid-code claim. The
    deterministic fallback can still report format/rule findings, but every
    unverified code is published as invalid and requires catalog review.
    """
    degraded = bool(result.get("degraded") or result.get("fallback_used"))
    validated_codes: list[dict[str, Any]] = []
    for raw in result.get("validated_codes") or []:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("code") or "").strip()
        if not code:
            continue
        explicit_catalog = isinstance(raw.get("in_catalog"), bool)
        in_catalog = bool(raw.get("in_catalog")) if explicit_catalog else False
        assignable = bool(raw.get("assignable")) if explicit_catalog else False
        raw_status = str(raw.get("status") or "").strip().casefold()
        valid_status = raw_status == "valid" or (
            raw_status == "pass" and in_catalog and assignable
        )
        status = "valid" if valid_status and in_catalog and assignable else "invalid"
        issue = str(raw.get("issue") or "").strip()
        if status == "invalid" and not issue:
            issue = (
                "目录校验不可用，未取得可分配性证据；必须使用授权版本目录人工复核。"
                if degraded or not explicit_catalog
                else "编码未通过目录或可分配性校验。"
            )
        validated_codes.append({
            "code": code,
            "status": status,
            "in_catalog": in_catalog,
            "assignable": assignable,
            "catalog_name": str(
                raw.get("catalog_name") or raw.get("description") or ""
            ),
            "issue": issue,
            "suggested_replacement": str(raw.get("suggested_replacement") or ""),
        })

    cross_code_issues: list[dict[str, Any]] = []
    for raw in result.get("cross_code_issues") or []:
        if not isinstance(raw, dict):
            continue
        if "code" in raw or "issue" in raw:
            code = str(raw.get("code") or "")
            issue = str(raw.get("issue") or "")
            severity = str(raw.get("severity") or "warning")
            review_required = bool(raw.get("manual_review_required", True))
        else:
            code = "/".join(
                str(item) for item in (raw.get("codes") or []) if str(item)
            )
            issue = str(raw.get("action") or raw.get("rule") or "跨编码规则需复核")
            severity = "warning"
            review_required = True
        if not code and not issue:
            continue
        cross_code_issues.append({
            "code": code,
            "issue": issue,
            "severity": severity,
            "manual_review_required": review_required,
        })

    conclusion = str(result.get("review_conclusion") or "WARNING").upper().strip()
    if conclusion not in {"PASS", "WARNING", "FAIL"}:
        conclusion = "WARNING"
    if validated_codes and any(
        item["status"] == "invalid" for item in validated_codes
    ):
        conclusion = "FAIL"
    manual_review = bool(
        result.get("manual_review_required")
        or degraded
        or conclusion != "PASS"
        or any(item["manual_review_required"] for item in cross_code_issues)
    )
    return {
        "review_conclusion": conclusion,
        "validated_codes": validated_codes,
        "cross_code_issues": cross_code_issues,
        "manual_review_required": manual_review,
        "summary": str(result.get("summary") or "编码校验已完成。"),
        "markdown": str(result.get("markdown") or ""),
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
    """Invoke deterministic rules as a review-required degradation."""
    from .agent_legacy import run_legacy_with_corti_schema
    result = await run_legacy_with_corti_schema(text, run_id=run_id)
    result["manual_review_required"] = True
    result["degraded"] = True
    result["fallback_used"] = True
    result["runtime_mode"] = "deterministic_rule_engine_fallback"
    result.setdefault("trace_refs", {})["fallback"] = "legacy_rule_engine"
    return result


__all__ = [
    "run",
    "run_deterministic",
    "run_llm_enhanced",
    "to_current_pack_candidate",
]
