"""StructuredOutputProjector — shared JSON-in-markdown parser.

Phase 5 Track C Gate 1 (2026-07-11): unified layer for extracting
structured output from PureLLM agent responses. Closes the B-2 P1
gap "unified API 不解析 JSON-in-markdown" (8 agents affected:
compliance-guardrail, note-completeness, procedure-extractor,
evidence-extractor, principal-dx-review, discharge-summary,
drg-analyzer, and partially medical-coding when not in MedCodER mode).

Design:
  - Markdown-first: PureLLM agents emit a markdown response. The
    projector extracts a structured `result` object by parsing
    JSON code blocks + section headers.
  - Per-agent contract: each agent's `output_contract()` declares
    a schema name (e.g. `icoder/NoteCompleteness/v1`). The
    projector applies agent-specific extraction rules.
  - Defensive: never raises. On any parse error, returns an empty
    dict + a `parse_warnings` list so the caller can fall back to
    the raw markdown.

Public API:
  - ``project(markdown, contract, agent_id) -> StructuredProjection``
  - ``StructuredProjection`` dataclass

Per Corti-parity (Track C Gate 0B finding corti-arch-003), Corti's
coding-expert emits `data-json` events with structured payloads
directly (no markdown wrapping). iCoDer PureLLM agents currently
emit markdown; this projector normalizes both shapes for the
unified `/api/v1/agents/{id}/run` response.

Hard rules:
  1. Never mutate the input markdown.
  2. Never raise — all errors become `parse_warnings` entries.
  3. Always return `raw_markdown` so callers can fall back.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StructuredProjection:
    """Result of projecting a markdown response into a structured object.

    Attributes:
        result: structured dict extracted from markdown. Empty if
            nothing parseable was found.
        raw_markdown: the original markdown (never mutated).
        parse_warnings: list of human-readable warnings. Empty on
            clean parse.
        contract: the contract name used for extraction.
        extraction_method: which strategy succeeded (json_block,
            section_header, kv_pairs, none).
    """

    result: dict[str, Any]
    raw_markdown: str
    parse_warnings: list[str] = field(default_factory=list)
    contract: str = ""
    extraction_method: str = "none"


# ── Extraction strategies ───────────────────────────────────────────────


_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n(\{.*?\}|\[.*?\])\s*\n```",
    re.DOTALL | re.IGNORECASE,
)
_JSON_BARE_RE = re.compile(r"(\{[\s\S]*\})", re.DOTALL)


def _try_json_fence(markdown: str) -> tuple[Any | None, str]:
    """Extract first ```json ... ``` block. Returns (parsed, warning)."""
    matches = _JSON_FENCE_RE.findall(markdown)
    for raw in matches:
        try:
            return json.loads(raw), ""
        except json.JSONDecodeError as e:
            continue
    if matches:
        return None, f"found {len(matches)} json fence(s) but all failed to parse"
    return None, ""


def _try_bare_json(markdown: str) -> tuple[Any | None, str]:
    """Extract first {...} bare JSON object. Last-resort strategy."""
    match = _JSON_BARE_RE.search(markdown)
    if not match:
        return None, ""
    try:
        return json.loads(match.group(1)), ""
    except json.JSONDecodeError as e:
        return None, f"bare json parse failed: {e}"


# ── Per-contract extractors ─────────────────────────────────────────────


def _extract_json_dict(md: str, warnings: list[str]) -> dict | None:
    """Try JSON fence then bare JSON. Append warnings, return dict or None."""
    parsed, w = _try_json_fence(md)
    if not isinstance(parsed, dict):
        parsed, w2 = _try_bare_json(md)
        if w and not isinstance(parsed, dict):
            warnings.append(w)
        if w2 and not isinstance(parsed, dict):
            warnings.append(w2)
    return parsed if isinstance(parsed, dict) else None


def _extract_note_completeness(md: str) -> tuple[dict, list[str]]:
    """Note completeness §7.6: required/present/missing/incomplete/conflicts."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        # Preferred §7.6 contract keys.
        for key in (
            "required_sections", "present_sections", "missing_sections",
            "incomplete_sections", "conflicts", "completeness_score",
            "review_conclusion", "corrected_draft",
        ):
            if key in parsed:
                result[key] = parsed[key]
        # Back-compat: older prompts emitted missing_fields/issues.
        if "missing_fields" in parsed and "missing_sections" not in result:
            result["missing_sections"] = parsed["missing_fields"]
        if "issues" in parsed and "conflicts" not in result:
            result["conflicts"] = parsed["issues"]
        if "category_scores" in parsed:
            result.setdefault("category_scores", parsed["category_scores"])
        if result:
            return result, warnings

    # Fallback 1: parse markdown tables. Match rows where status column
    # contains 缺失/missing. Row shape: `| **主诉** | **缺失** | ... |`.
    # Tolerates emoji prefixes like `❌ **缺失**` and `⚠️ **部分缺失**`.
    # Note: incomplete_keywords checked FIRST because `部分缺失` contains `缺失`.
    missing_from_table: list[str] = []
    incomplete_from_table: list[dict[str, str]] = []
    incomplete_keywords = ("部分缺失", "部分存在", "不完整", "incomplete")
    missing_keywords = ("缺失", "missing", "未提供")
    for row in re.findall(r"^\s*\|(.+)\|\s*$", md, re.MULTILINE):
        cells = [c.strip() for c in row.split("|")]
        if len(cells) < 2:
            continue
        status = cells[1].strip("* ").lower()
        label = cells[0].strip("* ").strip()
        if not label:
            continue
        if any(kw.lower() in status for kw in incomplete_keywords):
            incomplete_from_table.append({
                "section": label,
                "deficit_note": cells[2].strip("* ").strip() if len(cells) > 2 else "",
            })
        elif any(kw.lower() in status for kw in missing_keywords):
            if label not in missing_from_table:
                missing_from_table.append(label)
    if missing_from_table:
        result["missing_sections"] = missing_from_table
    if incomplete_from_table:
        result["incomplete_sections"] = incomplete_from_table

    # Fallback 1b: dedicated "Missing Sections" row shape
    if "missing_sections" not in result:
        m = re.search(
            r"\|\s*\*{0,2}\s*(?:Missing\s+Sections|缺失[章节字段]+)\s*\*{0,2}\s*\|([^|]+)\|",
            md, re.IGNORECASE,
        )
        if m:
            items = [s.strip().strip("*").strip() for s in m.group(1).split(",")]
            items = [s for s in items if s]
            if items:
                result["missing_sections"] = items

    # Fallback 2: bullet list under a Missing/缺失 section header.
    if "missing_sections" not in result:
        missing = re.findall(
            r"^\s*[-*]\s+(.+)$",
            _extract_section(md, ["Missing", "缺失", "缺失字段", "缺少"]) or "",
            re.MULTILINE,
        )
        if missing:
            result["missing_sections"] = [m.strip() for m in missing if m.strip()]

    # Score: try numeric patterns including `**2 / 8**` and `(completeness_score)`.
    score = _extract_score(
        md,
        [
            "completeness_score", "完整度", "完整度评分", "完整性评分",
            "Completeness Score",
        ],
    )
    if score is not None:
        result["completeness_score"] = score
    else:
        warnings.append("completeness_score not found in markdown")

    return result, warnings


def _extract_compliance_guardrail(md: str) -> tuple[dict, list[str]]:
    """Compliance: extract risk_points + violations + risk_level."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        for key in ("risk_points", "violations", "risk_level", "risk_score",
                    "compliant", "recommendations", "rules_triggered"):
            if key in parsed:
                result[key] = parsed[key]
        if result:
            return result, warnings

    risks = re.findall(
        r"^\s*[-*]\s+(.+)$",
        _extract_section(md, ["Risk", "风险", "风险点", "违规"]) or "",
        re.MULTILINE,
    )
    if risks:
        result["risk_points"] = [r.strip() for r in risks if r.strip()]

    level = _extract_kv(md, ["risk_level", "风险等级"])
    if level:
        result["risk_level"] = level
    return result, warnings


def _extract_procedure_extractor(md: str) -> tuple[dict, list[str]]:
    """Procedure: extract procedures[] + non_billable_mentions[] (Phase 5 Track C §7.3)."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        for key in (
            "procedures", "total_count", "coded_procedures",
            "non_billable_mentions", "issues_found", "manual_review_required",
        ):
            if key in parsed:
                result[key] = parsed[key]
        # Gate 2 §7.3 enforcement: filter procedures[] to status=performed only.
        if "procedures" in result and isinstance(result["procedures"], list):
            performed = []
            moved: list[dict[str, Any]] = []
            for proc in result["procedures"]:
                if not isinstance(proc, dict):
                    continue
                status = proc.get("status", "performed")  # default performed (back-compat)
                if status == "performed":
                    performed.append(proc)
                else:
                    moved.append({
                        "text": proc.get("display") or proc.get("text") or "",
                        "status": status,
                        "evidence_text": proc.get("evidence_text", ""),
                        "char_span": proc.get("char_span"),
                    })
            result["procedures"] = performed
            result.setdefault("non_billable_mentions", [])
            result["non_billable_mentions"] = (
                (result["non_billable_mentions"] or []) + moved
            )
            result["total_count"] = len(performed)
        if result:
            return result, warnings

    # Fallback: count markdown table rows that look like procedure entries.
    proc_section = _extract_section(md, ["Procedure", "手术", "操作"]) or ""
    proc_rows = [
        line for line in proc_section.splitlines()
        if line.strip().startswith("|") and "code" not in line.lower()
        and "手术" not in line
    ]
    if proc_rows:
        result["procedures"] = [r.strip().strip("|") for r in proc_rows]
        result["total_count"] = len(proc_rows)
    return result, warnings


def _extract_evidence_extractor(md: str) -> tuple[dict, list[str]]:
    """Evidence: extract supported/uncertain/rejected tiers (§7.1 + §7.4)."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        for key in (
            "supported_codes", "uncertain_candidates", "rejected_candidates",
            "coded_evidence", "overall_strength", "evidence_items",
            "uncoded_findings", "review_summary",
        ):
            if key in parsed:
                result[key] = parsed[key]
        if result:
            return result, warnings

    strength = _extract_score(md, ["overall_strength", "证据强度", "总体强度"])
    if strength is not None:
        result["overall_strength"] = strength
    return result, warnings


def _extract_principal_dx(md: str) -> tuple[dict, list[str]]:
    """Principal diagnosis: extract recommended + conflict + rationale (§7.5)."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        for key in (
            "candidates", "recommended", "not_recommended",
            "principal_dx", "principal_diagnosis",
            "coding_draft_consistent", "conflict_reason", "conflict",
            "conflict_detected", "manual_review_required",
            "rationale", "alternatives", "manual_review_prompt",
        ):
            if key in parsed:
                result[key] = parsed[key]
        if result:
            return result, warnings
    return result, warnings


def _extract_discharge_summary(md: str) -> tuple[dict, list[str]]:
    """Discharge: extract structured sections + diagnoses/procedures.

    Accepts bare JSON `{"diagnoses":[...],"procedures":[...],"treatment_summary":...}`
    or `{"structured_sections":{...}}` envelope. Normalizes the bare shape into
    ``structured_sections`` for downstream consumers.
    """
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        for key in ("structured_sections", "sections", "discharge_sections"):
            if key in parsed:
                result[key] = parsed[key]
        # Bare shape: diagnoses + procedures + treatment_summary at top level.
        if not result and any(
            k in parsed for k in
            ("diagnoses", "procedures", "treatment_summary", "discharge_plan", "medications")
        ):
            result["structured_sections"] = {
                k: parsed[k] for k in
                ("diagnoses", "procedures", "treatment_summary",
                 "discharge_plan", "medications")
                if k in parsed
            }
        if result:
            return result, warnings
    return result, warnings


def _extract_drg_analyzer(md: str) -> tuple[dict, list[str]]:
    """DRG: extract risk_points + drg_dip_rule_reservation_note."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        for key in ("risk_points", "drg_dip_rule_reservation_note",
                    "upcoding_risk", "downcoding_risk",
                    "inconsistency_risk", "missing_complication_risk"):
            if key in parsed:
                result[key] = parsed[key]
        if result:
            return result, warnings

    risks = re.findall(
        r"^\s*[-*]\s+(.+)$",
        _extract_section(md, ["Risk", "风险", "DRG", "DIP"]) or "",
        re.MULTILINE,
    )
    if risks:
        result["risk_points"] = [r.strip() for r in risks if r.strip()]
    return result, warnings


def _extract_code_validation(md: str) -> tuple[dict, list[str]]:
    """Code validation: extract validation_results[] + overall_valid."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        for key in ("validation_results", "overall_valid", "issues",
                    "validated_codes", "rules_checked"):
            if key in parsed:
                result[key] = parsed[key]
        if result:
            return result, warnings
    return result, warnings


_CONTRACT_EXTRACTORS: dict[str, callable] = {
    "icoder/NoteCompleteness/v1": _extract_note_completeness,
    "icoder/ComplianceGuardrail/v1": _extract_compliance_guardrail,
    "icoder/ProcedureExtractor/v1": _extract_procedure_extractor,
    "icoder/EvidenceExtractor/v1": _extract_evidence_extractor,
    "icoder/PrincipalDxReview/v1": _extract_principal_dx,
    "icoder/DischargeSummary/v1": _extract_discharge_summary,
    "icoder/DrgAnalyzer/v1": _extract_drg_analyzer,
    "icoder/CodeValidation/v1": _extract_code_validation,
}


# ── Generic helpers ─────────────────────────────────────────────────────


def _extract_section(md: str, headers: list[str]) -> str | None:
    """Extract the body of a markdown section by header keyword."""
    lines = md.splitlines()
    capturing = False
    captured: list[str] = []
    for line in lines:
        if line.lstrip().startswith("#"):
            header_text = line.lstrip("#").strip().lower()
            if capturing:
                break  # next section
            if any(h.lower() in header_text for h in headers):
                capturing = True
                continue
        elif capturing:
            captured.append(line)
    return "\n".join(captured).strip() if captured else None


def _extract_score(md: str, keys: list[str]) -> float | None:
    """Extract a numeric score by key patterns.

    Handles common markdown patterns:
      - ``completeness_score: 0.85``
      - ``**完整度**: 0.85``
      - ``completeness_score=0.85``
      - ``**完整性评分 (completeness_score)** | **2 / 8**`` (table cell,
        takes numerator)
      - ``完整性评分 (completeness_score)** 2 / 8`` (inline ratio)
    """
    for key in keys:
        for pattern in (
            rf"{re.escape(key)}\s*[:：]\s*(\d+(?:\.\d+)?)",
            rf"\*\*{re.escape(key)}\*\*\s*[:：]\s*(\d+(?:\.\d+)?)",
            rf"{re.escape(key)}\s*[=：:]\s*(\d+(?:\.\d+)?)",
            rf"{re.escape(key)}\).*?(\d+(?:\.\d+)?)\s*/\s*\d+",  # (key)** 2 / 8
            rf"\|\s*\*{{0,2}}(\d+(?:\.\d+)?)\s*/\s*\d+",  # table cell **2 / 8**
        ):
            m = re.search(pattern, md, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except (ValueError, IndexError):
                    continue
    return None


def _extract_kv(md: str, keys: list[str]) -> str | None:
    """Extract a string value by key patterns."""
    for key in keys:
        for pattern in (
            rf"{re.escape(key)}\s*[:：]\s*([^\n|]+)",
            rf"\*\*{re.escape(key)}\*\*\s*[:：]\s*([^\n|]+)",
        ):
            m = re.search(pattern, md, re.IGNORECASE)
            if m:
                return m.group(1).strip().strip("*").strip()
    return None


# ── Public API ──────────────────────────────────────────────────────────


def project(
    markdown: str,
    contract: str = "",
    agent_id: str = "",
) -> StructuredProjection:
    """Project a markdown response into a structured dict.

    Args:
        markdown: the raw LLM response markdown.
        contract: e.g. "icoder/NoteCompleteness/v1". If empty, only
            generic JSON-block extraction is attempted.
        agent_id: optional, used for warning context only.

    Returns:
        StructuredProjection with result + raw_markdown + warnings.
    """
    if not markdown:
        return StructuredProjection(
            result={}, raw_markdown="", contract=contract,
            parse_warnings=["empty markdown"],
            extraction_method="none",
        )

    extractor = _CONTRACT_EXTRACTORS.get(contract)
    if extractor is None:
        # Generic fallback: try JSON block, then bare JSON.
        parsed, w = _try_json_fence(markdown)
        if isinstance(parsed, dict):
            return StructuredProjection(
                result=parsed, raw_markdown=markdown, contract=contract,
                extraction_method="json_block",
            )
        parsed, w2 = _try_bare_json(markdown)
        if isinstance(parsed, dict):
            return StructuredProjection(
                result=parsed, raw_markdown=markdown, contract=contract,
                parse_warnings=[w] if w else [],
                extraction_method="bare_json",
            )
        return StructuredProjection(
            result={}, raw_markdown=markdown, contract=contract,
            parse_warnings=[w, w2, f"no extractor for contract {contract}"],
            extraction_method="none",
        )

    try:
        result, warnings = extractor(markdown)
        method = "json_block" if result and not warnings else (
            "section_header" if result else "none"
        )
        return StructuredProjection(
            result=result, raw_markdown=markdown, contract=contract,
            parse_warnings=warnings, extraction_method=method,
        )
    except Exception as e:
        logger.exception("StructuredOutputProjector: extractor failed")
        return StructuredProjection(
            result={}, raw_markdown=markdown, contract=contract,
            parse_warnings=[f"extractor {contract} raised: {type(e).__name__}: {e}"],
            extraction_method="none",
        )


def project_or_empty(
    markdown: str, contract: str = "", agent_id: str = "",
) -> dict[str, Any]:
    """Convenience: return just the result dict (empty on failure)."""
    return project(markdown, contract, agent_id).result
