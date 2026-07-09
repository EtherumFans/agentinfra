"""Code Validation Output Schema v2 — Corti-style (Phase 4-C).

Replaces the v1 schema (``fired_rules`` / ``code_assignment_summary`` /
``trace_refs``) with a Corti-mirroring schema:

  - ``validated_codes`` — per-code check results with tool provenance
  - ``cross_code_issues`` — EXCLUDES1/sequencing/missing-companion etc.
  - ``markdown`` — Corti-style 6-section report
  - ``summary`` — 1-2 sentence plain-language summary

The v1 schema (``CodeValidationOutput`` in
``compliance_services.medical_coding_rules``) is preserved for the
``validate_codes`` MCP tool, which still serves RuleEngine consumers.
The new v2 schema is what the LLM-based ``code_validation/agent.py``
produces.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── Per-code check results ───────────────────────────────────────────


CheckStatus = Literal["PASS", "FAIL", "WARNING", "N/A"]
CheckName = Literal[
    "assignability",
    "completeness",
    "7th_char",
    "laterality",
    "age_sex",
    "unsupported_assumptions",
    "documentation",
    "rule",
]


class CheckResult(BaseModel):
    """One check on one code (assignability / 7th-char / laterality / ...).

    ``evidence_tool_refs`` is the list of tool_call_ids that ground this
    check's verdict — the LLM must cite tool results, not hallucinate
    rules. Empty in the legacy RuleEngine fallback path (Phase 4-C:
    legacy path produces no tool calls).
    """

    check_name: str = Field(..., description="Rule/check name (e.g. 'assignability', 'R003', 'rule:7th_char').")
    status: CheckStatus
    issue: str | None = Field(default=None, description="Issue description when status != PASS.")
    evidence_tool_refs: list[str] = Field(
        default_factory=list,
        description="tool_call_ids that ground this check (citations).",
    )


CodeStatus = Literal["PASS", "FAIL", "WARNING"]


class ValidatedCode(BaseModel):
    """Per-code validation result."""

    code: str
    description: str = ""
    status: CodeStatus
    assignable: bool = Field(..., description="True iff the code is a leaf code (not a category).")
    checks: list[CheckResult] = Field(default_factory=list)
    issue: str | None = None


# ── Cross-code issues ────────────────────────────────────────────────


CrossCodeIssueType = Literal[
    "EXCLUDES1_CONFLICT",
    "EXCLUDES2_CONFLICT",
    "SEQUENCING",
    "MISSING_COMPANION",
    "COMBINATION_CODE",
    "SYMPTOM_SUPPRESSION",
    "LATERALITY_MISMATCH",
    "DUPLICATE",
    "LEGACY_RULE",
]


class CrossCodeIssue(BaseModel):
    """Issue involving 2+ codes (e.g. EXCLUDES1 conflict, missing companion)."""

    issue_type: CrossCodeIssueType
    codes: list[str] = Field(default_factory=list)
    rule: str = Field(default="", description="Rule name / EXCLUDES note that triggered this issue.")
    action: str = Field(default="", description="Recommended action (e.g. 'remove X', 'add Y'.")


# ── Top-level schema ─────────────────────────────────────────────────


ReviewConclusion = Literal["PASS", "WARNING", "FAIL"]


class CodeValidationOutputV2(BaseModel):
    """Corti-style Code Validation output (Phase 4-C).

    Replaces ``CodeValidationOutput`` (v1). The legacy v1 schema is
    preserved for the ``validate_codes`` MCP tool (which still serves
    RuleEngine consumers); the new v2 schema is what the LLM-based
    ``code_validation/agent.py`` produces.
    """

    agent_id: str = ""
    run_id: str = ""
    review_conclusion: ReviewConclusion
    issues_found: list[dict] = Field(default_factory=list)
    manual_review_required: bool = False
    rule_set: str = "medical_coding"
    validated_codes: list[ValidatedCode] = Field(default_factory=list)
    cross_code_issues: list[CrossCodeIssue] = Field(default_factory=list)
    summary: str = ""
    markdown: str = ""
    trace_refs: dict = Field(default_factory=dict)


__all__ = [
    "CodeValidationOutputV2",
    "ValidatedCode",
    "CheckResult",
    "CrossCodeIssue",
    "CheckStatus",
    "CodeStatus",
    "ReviewConclusion",
    "CrossCodeIssueType",
]
