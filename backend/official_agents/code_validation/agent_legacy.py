"""Code Validation Agent — LEGACY implementation (pure RuleEngine, no LLM).

Phase 4-C: this file is preserved as the legacy fallback for the new
LLM-based ``agent.py`` (v2). When the LLM path fails (timeout, parse
error, prompt-injection refusal), the new ``agent.py`` falls back to
``run_legacy_with_corti_schema()`` which:

  1. Calls ``run_legacy()`` — the original deterministic RuleEngine path.
  2. Lossily converts the v1 output shape to the v2 Corti-style shape
     (``validated_codes`` / ``cross_code_issues`` / ``markdown`` /
     ``summary``). Some v2 fields (e.g. ``evidence_tool_refs`` on each
     check) are empty in the legacy path because the RuleEngine has no
     tool-call provenance.

Original docstring (Phase 3-D1 Task 5):

Input: text containing a coding set. Accepted formats (auto-detected):
  1. JSON object with primary_diagnosis / secondary_diagnoses / procedures
  2. Plain text containing ICD-10 codes (A-Z + digits) and ICD-9-CM-3
     procedure codes (digits + dot) — parsed via regex.

Output (CodeValidationOutputSchema v1 — kept for the ``validate_codes``
MCP tool and other v1 consumers):
  {
    "review_conclusion": "PASS" | "WARNING" | "FAIL",
    "issues_found": [ {severity, rule_id, message, suggestion, category} ],
    "manual_review_required": bool,
    "rule_set": "medical_coding",
    "fired_rules": ["R001", "R002", ...],
    "code_assignment_summary": {
      "primary_diagnosis": {"code", "description", "confidence"},
      "secondary_diagnoses": [...],
      "procedures": [...]
    },
    "trace_refs": {"run_id", "agent_ref", "rule_set"}
  }

Deterministic: no LLM. The RuleEngine + MedicalCodingRuleSet (R001-R010 +
MC-R-M80-001) is the source of truth.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

# ICD-10: letter + 2 digits + optional . + 1-4 digits (e.g. I50.9, S72.001A)
ICD10_REGEX = re.compile(r"\b([A-Z]\d{2}(?:\.\d{1,4})?)\b")
# ICD-9-CM-3: 2 digits + . + 1-4 digits (e.g. 79.31, 01.24)
ICD9CM3_REGEX = re.compile(r"\b(\d{2}\.\d{1,4})\b")


def _try_parse_json(text: str) -> dict | None:
    """Try to parse the input as JSON. Return None on failure."""
    text = text.strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        candidate = text[start : end + 1]
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_coding_set_from_text(text: str) -> dict:
    """Parse a coding set from free text using regex."""
    icd10_codes = list(dict.fromkeys(ICD10_REGEX.findall(text)))
    icd9_codes = list(dict.fromkeys(ICD9CM3_REGEX.findall(text)))

    primary = {
        "code": icd10_codes[0] if icd10_codes else "",
        "description": "",
        "confidence": 1.0 if icd10_codes else 0.0,
        "category": "primary",
        "evidence": [],
    }
    secondary = [
        {
            "code": c, "description": "", "confidence": 1.0,
            "category": "secondary", "evidence": [],
        }
        for c in icd10_codes[1:]
    ]
    procedures = [
        {
            "code": c, "description": "", "confidence": 1.0,
            "category": "procedure", "evidence": [],
        }
        for c in icd9_codes
    ]
    return {
        "primary_diagnosis": primary,
        "secondary_diagnoses": secondary,
        "procedures": procedures,
    }


def _normalize_input(text: str) -> tuple[dict, str]:
    """Return (coding_set, emr_text) from the input."""
    parsed = _try_parse_json(text)
    if parsed is not None:
        coding_set = {
            "primary_diagnosis": parsed.get("primary_diagnosis") or {},
            "secondary_diagnoses": parsed.get("secondary_diagnoses") or [],
            "procedures": parsed.get("procedures") or [],
        }
        emr_text = parsed.get("encounter_text") or parsed.get("emr_text") or ""
        return coding_set, emr_text

    coding_set = _parse_coding_set_from_text(text)
    return coding_set, text


def _conclusion_from_issues(issues: list) -> str:
    """PASS = no issues; WARNING = medium/low; FAIL = critical/high."""
    if not issues:
        return "PASS"
    severities = {i.get("severity", "info") for i in issues}
    if severities & {"critical", "high"}:
        return "FAIL"
    return "WARNING"


async def run_legacy(input_text: str, *, run_id: str = "") -> dict:
    """Run the legacy RuleEngine Code Validation Agent (v1 shape)."""
    from compliance_services.medical_coding_rules import MedicalCodingRuleSet
    from compliance_services.rule_engine import RuleEngine

    engine = RuleEngine()
    engine.register(MedicalCodingRuleSet())

    coding_set, emr_text = _normalize_input(input_text)
    result = engine.validate(
        "medical_coding",
        coding_set,
        context={"encounter_text": emr_text},
    )

    issues = [i.to_dict() for i in result.issues]
    conclusion = _conclusion_from_issues(issues)
    manual_review = bool(
        result.manual_review_required
        or conclusion == "FAIL"
        or any(i.get("severity") in ("critical", "high") for i in issues)
    )

    return {
        "review_conclusion": conclusion,
        "issues_found": issues,
        "manual_review_required": manual_review,
        "rule_set": "medical_coding",
        "fired_rules": result.rules_fired,
        "code_assignment_summary": {
            "primary_diagnosis": coding_set.get("primary_diagnosis", {}),
            "secondary_diagnoses": coding_set.get("secondary_diagnoses", []),
            "procedures": coding_set.get("procedures", []),
        },
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": "icoder/code-validation-agent@1.0.0",
            "rule_set": "medical_coding",
        },
    }


# Backwards compat: existing callers import ``run``.
run = run_legacy


# ── v2 legacy fallback wrapper ───────────────────────────────────────


async def run_legacy_with_corti_schema(input_text: str, *, run_id: str = "") -> dict:
    """Run the legacy RuleEngine, then lossily convert to v2 Corti shape.

    The v2 schema (``CodeValidationOutputV2``) is what the new LLM-based
    ``agent.py`` produces. When the LLM path fails, the new agent falls
    back here so consumers always get a v2-shape response — but with
    empty ``evidence_tool_refs`` (no tool calls in the legacy path) and
    a markdown summary generated from the v1 issues list.

    Lossy fields (empty in legacy path):
      - ``validated_codes[].checks[].evidence_tool_refs`` — RuleEngine
        has no tool-call provenance, so this is always ``[]``.
      - ``cross_code_issues`` — derived from the v1 ``issues_found``
        list, but only for issues that name 2+ codes (best-effort).
    """
    v1 = await run_legacy(input_text, run_id=run_id)
    return _convert_v1_to_v2(v1, run_id=run_id)


def _convert_v1_to_v2(v1: dict, *, run_id: str) -> dict:
    """Lossily convert a v1 CodeValidationOutputSchema dict to v2 shape."""
    coding_summary = v1.get("code_assignment_summary") or {}
    primary = coding_summary.get("primary_diagnosis") or {}
    secondary = list(coding_summary.get("secondary_diagnoses") or [])

    validated_codes: list[dict] = []
    for entry in [primary, *secondary]:
        if not isinstance(entry, dict) or not entry.get("code"):
            continue
        validated_codes.append(_build_validated_code_from_v1(
            entry, v1.get("issues_found") or [],
        ))

    # cross_code_issues — best-effort: pull issues whose message references 2+ codes.
    cross_issues: list[dict] = []
    for issue in v1.get("issues_found") or []:
        if not isinstance(issue, dict):
            continue
        msg = str(issue.get("message") or "")
        codes_in_msg = ICD10_REGEX.findall(msg) + ICD9CM3_REGEX.findall(msg)
        if len(set(codes_in_msg)) >= 2:
            cross_issues.append({
                "issue_type": "LEGACY_RULE",
                "codes": list(set(codes_in_msg))[:5],
                "rule": str(issue.get("rule_id") or ""),
                "action": str(issue.get("suggestion") or ""),
            })

    markdown = _build_markdown_from_v1(v1, validated_codes)

    return {
        "agent_id": "",
        "run_id": run_id or (v1.get("trace_refs") or {}).get("run_id", ""),
        "review_conclusion": v1.get("review_conclusion") or "WARNING",
        "issues_found": list(v1.get("issues_found") or []),
        "manual_review_required": bool(v1.get("manual_review_required")),
        "rule_set": "medical_coding",
        "validated_codes": validated_codes,
        "cross_code_issues": cross_issues,
        "summary": (
            f"Legacy RuleEngine fallback: {len(v1.get('fired_rules') or [])} "
            f"rules fired, conclusion={v1.get('review_conclusion')}."
        ),
        "markdown": markdown,
        "trace_refs": {
            **(v1.get("trace_refs") or {}),
            "fallback": "legacy_rule_engine",
        },
    }


def _build_validated_code_from_v1(entry: dict, issues: list) -> dict:
    """Build a v2 ``ValidatedCode`` dict from a v1 coding entry + issues list."""
    code = str(entry.get("code") or "")
    description = str(entry.get("description") or "")

    related_issues = [
        i for i in issues
        if isinstance(i, dict) and code in str(i.get("message") or "")
    ]

    related_severities = {i.get("severity", "info") for i in related_issues}
    if related_severities & {"critical", "high"}:
        status = "FAIL"
    elif related_issues:
        status = "WARNING"
    else:
        status = "PASS"

    checks: list[dict] = []
    for issue in related_issues:
        checks.append({
            "check_name": str(issue.get("rule_id") or "rule"),
            "status": _severity_to_check_status(issue.get("severity", "info")),
            "issue": str(issue.get("message") or ""),
            "evidence_tool_refs": [],
        })

    return {
        "code": code,
        "description": description,
        "status": status,
        "assignable": True,
        "checks": checks,
        "issue": related_issues[0].get("message") if related_issues else None,
    }


def _severity_to_check_status(severity: str) -> str:
    """Map v1 severity → v2 check status (PASS/FAIL/WARNING/N/A)."""
    s = (severity or "").lower()
    if s in ("critical", "high"):
        return "FAIL"
    if s in ("medium", "low"):
        return "WARNING"
    if s == "info":
        return "PASS"
    return "N/A"


def _build_markdown_from_v1(v1: dict, validated_codes: list[dict]) -> str:
    """Build a v2 markdown summary from the v1 output."""
    conclusion = v1.get("review_conclusion") or "WARNING"
    fired = list(v1.get("fired_rules") or [])
    issues = list(v1.get("issues_found") or [])
    lines = [
        "# Code Validation — Legacy RuleEngine Fallback",
        "",
        f"## Status\n\n{conclusion}",
        "",
        f"## Summary\n\n{len(fired)} rule(s) fired, {len(issues)} issue(s) found.",
        "",
        "## Validated Codes",
        "",
    ]
    if not validated_codes:
        lines.append("(no codes in input)")
    for vc in validated_codes:
        lines.append(
            f"- **{vc['code']}** — {vc['status']} "
            f"({vc['description'] or 'no description'})"
        )
    lines.extend([
        "",
        "## Fired Rules",
        "",
        ", ".join(fired) if fired else "(none)",
        "",
        "## Note",
        "",
        "This output was produced by the legacy RuleEngine fallback "
        "(LLM path failed or was unavailable). Tool-call provenance "
        "(``evidence_tool_refs``) is empty in this path.",
        "",
    ])
    return "\n".join(lines)


__all__ = ["run", "run_legacy", "run_legacy_with_corti_schema"]
