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
        # A strict Pack contract may evolve faster than this compatibility
        # projector. Preserve every model-emitted field, then apply only the
        # documented aliases/normalizations below. Dropping valid fields here
        # makes a conformant provider response fail its Pack contract.
        result.update(parsed)
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
        if "documentation_gaps" not in result:
            gaps: list[dict[str, Any]] = []
            for section in result.get("missing_sections") or []:
                gaps.append({
                    "section": section,
                    "gap_type": "missing",
                    "description": f"{section}缺失",
                })
            for item in result.get("incomplete_sections") or []:
                if isinstance(item, dict):
                    gaps.append({
                        "section": item.get("section", ""),
                        "gap_type": "incomplete",
                        "description": item.get("deficit_note", ""),
                    })
            for conflict in result.get("conflicts") or []:
                if isinstance(conflict, dict):
                    conflict_description = str(
                        conflict.get("note")
                        or conflict.get("description")
                        or ""
                    )
                else:
                    conflict_description = str(conflict)
                gaps.append({
                    "section": "",
                    "gap_type": "conflict",
                    "description": conflict_description,
                })
            result["documentation_gaps"] = gaps
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
        result.update(parsed)
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
        result.update(parsed)
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
        result.update(parsed)
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
        result.update(parsed)
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


def _extract_governed_principal_dx(md: str) -> tuple[dict, list[str]]:
    """Preserve documented draft evidence while enforcing non-selection constants."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    allowed_fields = {
        "review_status", "review_purpose", "coding_standard",
        "documentation_scope", "documented_coding_draft", "candidates",
        "declared_selection_basis", "candidate_evidence_gaps", "input_conflicts",
        "draft_in_candidate_set", "draft_evidence_complete",
        "draft_consistency_status", "selection_basis_status", "review_method",
        "evidence_items", "missing_required_fields", "limitations",
        "diagnosis_extraction_performed", "code_assignment_performed",
        "principal_diagnosis_selection_performed", "clinical_inference_performed",
        "external_rules_used", "production_submission_blocked",
        "production_writeback_blocked", "manual_review_required", "trace_refs",
    }
    result = {key: value for key, value in parsed.items() if key in allowed_fields}
    result["review_method"] = (
        "DOCUMENTED_DRAFT_EVIDENCE_AND_SET_CONSISTENCY_ONLY"
    )
    documented_draft = result.get("documented_coding_draft")
    if isinstance(documented_draft, dict):
        documented_draft = dict(documented_draft)
        documented_draft["authority_status"] = (
            "CODER_DOCUMENTED_DRAFT_NOT_CLINICALLY_VALIDATED"
        )
        result["documented_coding_draft"] = documented_draft
    result["diagnosis_extraction_performed"] = False
    result["code_assignment_performed"] = False
    result["principal_diagnosis_selection_performed"] = False
    result["clinical_inference_performed"] = False
    result["external_rules_used"] = False
    result["production_submission_blocked"] = True
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
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
        result.update(parsed)
        for key in ("structured_sections", "sections", "discharge_sections"):
            if key in parsed:
                result[key] = parsed[key]
        # Bare shape: diagnoses + procedures + treatment_summary at top level.
        if "structured_sections" not in result and any(
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


def _extract_governed_discharge_summary(md: str) -> tuple[dict, list[str]]:
    """Preserve documented discharge sections and enforce safety constants."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["summary_generation_status"] = (
        "VERBATIM_SECTION_REORGANIZATION_ONLY"
    )
    result["icd_codes_assigned"] = False
    result["medication_reconciliation_performed"] = False
    result["clinical_inference_performed"] = False
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_governed_referral(md: str) -> tuple[dict, list[str]]:
    """Preserve documented referral fields and enforce the delivery boundary."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["draft_generation_status"] = "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
    result["clinical_inference_performed"] = False
    result["new_diagnosis_generated"] = False
    result["new_treatment_recommended"] = False
    result["external_knowledge_used"] = False
    result["production_transmission_blocked"] = True
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_governed_prior_authorization(md: str) -> tuple[dict, list[str]]:
    """Preserve documented authorization evidence and enforce review gates."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["medical_necessity_assessment_status"] = (
        "NOT_ASSESSED_POLICY_AND_CLINICAL_REVIEW_REQUIRED"
    )
    result["draft_generation_status"] = "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
    result["clinical_inference_performed"] = False
    result["new_diagnosis_generated"] = False
    result["new_treatment_recommended"] = False
    result["external_knowledge_used"] = False
    result["medical_calculator_used"] = False
    result["medical_coding_validation_performed"] = False
    result["production_submission_blocked"] = True
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_governed_claim_check(md: str) -> tuple[dict, list[str]]:
    """Preserve documented claim facts and enforce adjudication boundaries."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["evidence_consistency_status"] = "NOT_ASSESSED_LITERAL_PACKET_ONLY"
    result["comparison_basis"] = "DOCUMENTED_CLAIM_AND_POLICY_ONLY"
    result["clinical_support_assessed"] = False
    result["medical_necessity_assessed"] = False
    result["benefit_eligibility_determined"] = False
    result["code_assignment_performed"] = False
    result["drg_dip_grouping_performed"] = False
    result["external_knowledge_used"] = False
    result["production_submission_blocked"] = True
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_governed_denial_appeals(md: str) -> tuple[dict, list[str]]:
    """Preserve documented denial facts and enforce review/delivery gates."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["denial_classification_status"] = "DOCUMENTED_ONLY_NO_INFERENCE"
    result["draft_generation_status"] = "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
    result["clinical_support_assessed"] = False
    result["medical_necessity_assessed"] = False
    result["benefit_eligibility_determined"] = False
    result["denial_root_cause_inferred"] = False
    result["payer_policy_lookup_performed"] = False
    result["medical_coding_validation_performed"] = False
    result["external_knowledge_used"] = False
    result["production_submission_blocked"] = True
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_governed_clinical_education(md: str) -> tuple[dict, list[str]]:
    """Preserve source-bound teaching material and enforce safety constants."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["content_generation_status"] = "SOURCE_BOUND_TEMPLATE_ONLY"
    result["question_classification_performed"] = False
    result["clinical_reasoning_performed"] = False
    result["diagnostic_advice_generated"] = False
    result["treatment_advice_generated"] = False
    result["drug_interaction_assessed"] = False
    result["medical_calculator_used"] = False
    result["pubmed_lookup_performed"] = False
    result["web_search_performed"] = False
    result["external_knowledge_used"] = False
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_governed_clinical_guidelines(md: str) -> tuple[dict, list[str]]:
    """Preserve declared-rule comparison and enforce non-inference constants."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["source_authenticity_status"] = (
        "USER_DOCUMENTED_METADATA_ONLY_NOT_INDEPENDENTLY_VERIFIED"
    )
    result["source_currency_verified"] = False
    result["evaluation_method"] = "DECLARED_RULES_DETERMINISTIC_COMPARISON"
    result["guideline_retrieval_performed"] = False
    result["web_search_performed"] = False
    result["clinical_inference_performed"] = False
    result["clinical_significance_assessed"] = False
    result["treatment_recommendations_generated"] = False
    result["external_knowledge_used"] = False
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_drg_analyzer(md: str) -> tuple[dict, list[str]]:
    """DRG: extract risk_points + drg_dip_rule_reservation_note."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        result.update(parsed)
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


def _extract_governed_drg_analyzer(md: str) -> tuple[dict, list[str]]:
    """Preserve the governed coded-case review and enforce non-billing flags."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    allowed_fields = {
        "review_status", "review_conclusion", "review_method", "coded_case",
        "development_candidate_group", "dip_review", "risk_findings",
        "review_actions", "quality_flags", "governance", "evidence_items",
        "missing_required_fields", "input_conflicts", "limitations",
        "code_extraction_performed", "code_assignment_performed",
        "code_validation_performed", "clinical_inference_performed",
        "local_development_rules_used", "official_grouping_performed",
        "official_dip_scoring_performed", "payment_calculation_performed",
        "billing_authoritative", "production_submission_blocked",
        "production_writeback_blocked", "manual_review_required", "trace_refs",
    }
    result = {key: value for key, value in parsed.items() if key in allowed_fields}
    result["review_method"] = (
        "EXPLICIT_CODED_CASE_DETERMINISTIC_UNVERIFIED_RISK_REVIEW"
    )
    candidate = result.get("development_candidate_group")
    if isinstance(candidate, dict):
        candidate = {
            key: value for key, value in candidate.items()
            if key in {
                "candidate_drg", "candidate_name", "mdc", "mdc_name", "adrg",
                "cc_level", "grouping_method", "coverage", "result_status",
            }
        }
        result["development_candidate_group"] = candidate
    governance = result.get("governance")
    if isinstance(governance, dict):
        governance = dict(governance)
        governance.update({
            "rule_pack_id": "cn.drg_dip.risk_heuristics",
            "rule_pack_version": "1.0.0-development",
            "jurisdiction": "CN_GENERIC_DEVELOPMENT",
            "authority_status": "experimental_unverified",
            "license_status": "external_review_required",
            "use_restriction": (
                "development_risk_review_only_not_for_grouping_payment_or_settlement"
            ),
        })
        result["governance"] = governance
    result["code_extraction_performed"] = False
    result["code_assignment_performed"] = False
    result["code_validation_performed"] = False
    result["clinical_inference_performed"] = False
    result["official_grouping_performed"] = False
    result["official_dip_scoring_performed"] = False
    result["payment_calculation_performed"] = False
    result["billing_authoritative"] = False
    result["production_submission_blocked"] = True
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_code_validation(md: str) -> tuple[dict, list[str]]:
    """Code validation: extract validation_results[] + overall_valid."""
    warnings: list[str] = []
    result: dict[str, Any] = {}

    parsed = _extract_json_dict(md, warnings)
    if isinstance(parsed, dict):
        result.update(parsed)
        for key in ("validation_results", "overall_valid", "issues",
                    "validated_codes", "rules_checked"):
            if key in parsed:
                result[key] = parsed[key]
        if result:
            return result, warnings
    return result, warnings


def _extract_diagnosis_extraction(md: str) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    raw_status = str(result.get("status") or "").strip().casefold()
    normalized_status = {
        "completed": "PASS",
        "success": "PASS",
        "pass": "PASS",
        "warning": "WARNING",
        "warnings": "WARNING",
        "requires_review": "REQUIRES_REVIEW",
        "review": "REQUIRES_REVIEW",
    }.get(raw_status)
    if normalized_status is not None:
        result["status"] = normalized_status
    result.setdefault("non_codable_mentions", [])
    result.setdefault("issues_found", list(result.get("manual_review_reasons") or []))

    # DiagnosisExtractionOutput/v6 permits an empty ``diagnoses`` list, but
    # every item that remains in that list is a *codable* diagnosis and must
    # carry a verified ICD-10-CN code and display name.  A tool-aware model
    # may responsibly leave those fields empty when search/verification is
    # unavailable.  Do not turn that safe refusal into a whole-response
    # contract failure and, critically, never invent a code here.  Remove the
    # unverified item from the codable list, retain a PHI-free audit issue and
    # force manual review.
    diagnoses = result.get("diagnoses")
    if isinstance(diagnoses, list):
        codable_diagnoses: list[Any] = []
        omitted_indexes: list[int] = []
        for index, diagnosis in enumerate(diagnoses):
            if not isinstance(diagnosis, dict):
                # Preserve malformed shapes so the schema validator still
                # fails closed instead of silently discarding unknown data.
                codable_diagnoses.append(diagnosis)
                continue
            code = str(diagnosis.get("icd10_cn_code") or "").strip()
            name = str(diagnosis.get("icd10_cn_name") or "").strip()
            if not code or not name:
                omitted_indexes.append(index)
                continue
            codable_diagnoses.append(diagnosis)
        if omitted_indexes:
            result["diagnoses"] = codable_diagnoses
            existing_issues = result.get("issues_found")
            if not isinstance(existing_issues, list):
                existing_issues = []
            for index in omitted_indexes:
                issue = (
                    f"diagnoses[{index}] omitted from codable output because "
                    "ICD-10-CN code/name was not verified"
                )
                if issue not in existing_issues:
                    existing_issues.append(issue)
            result["issues_found"] = existing_issues
            result["manual_review_required"] = True
            result["status"] = "REQUIRES_REVIEW"
            warnings.append(
                f"omitted {len(omitted_indexes)} unverified diagnosis item(s); "
                "manual review required"
            )
    return result, warnings


def _extract_rule_explanation(md: str) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    explanation = result.get("explanation")
    if isinstance(explanation, dict):
        result.setdefault("explanation_summary", explanation.get("application_notes") or [])
        result.setdefault("guideline_basis", explanation.get("general_rules") or [])
        result.setdefault("evidence_tool_refs", explanation.get("catalog_facts") or [])
    limitations = list(result.get("unsupported_scope") or [])
    limitations.extend(result.get("tool_errors") or [])
    result.setdefault("limitations", limitations)
    return result, warnings


def _extract_medication_reconciliation(md: str) -> tuple[dict, list[str]]:
    """Preserve governed medication facts while enforcing public safety flags."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["interaction_screening_status"] = (
        "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED"
    )
    result["interaction_risks"] = []
    result["manual_review_required"] = True
    return result, warnings


def _extract_nursing_handoff(md: str) -> tuple[dict, list[str]]:
    """Preserve documented handoff facts while enforcing local safety flags."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["clinical_priority_assessed"] = False
    result["medical_calculator_used"] = False
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_icu_summary(md: str) -> tuple[dict, list[str]]:
    """Preserve documented ICU facts while enforcing local safety flags."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["clinical_scores_status"] = (
        "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED"
    )
    result["medication_screening_status"] = (
        "NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED"
    )
    result["clinical_recommendations_generated"] = False
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_discharge_education(md: str) -> tuple[dict, list[str]]:
    """Preserve documented discharge facts while enforcing safety flags."""
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    result["medication_reconciliation_status"] = (
        "NOT_RECONCILED_GOVERNED_MEDICATION_RECONCILIATION_REQUIRED"
    )
    result["translation_status"] = "VERBATIM_DOCUMENTED_CONTENT_ONLY"
    result["external_knowledge_used"] = False
    result["clinical_interpretation_performed"] = False
    result["clinical_recommendations_generated"] = False
    result["production_writeback_blocked"] = True
    result["manual_review_required"] = True
    return result, warnings


def _extract_icd10_navigator(md: str) -> tuple[dict, list[str]]:
    """Normalize the ICD-10 navigator's unverified-source safety boundary.

    A language model may still emit an empty notes list (or memorized codes)
    after correctly admitting that no catalog version was supplied.  The
    public contract must be deterministic: no source means no candidate code
    claims, an explicit manual catalog-review note, and mandatory review.
    """
    warnings: list[str] = []
    parsed = _extract_json_dict(md, warnings)
    if not isinstance(parsed, dict):
        return {}, warnings
    result = dict(parsed)
    source_version = str(result.get("source_version") or "").strip()
    normalized_version = source_version.casefold()
    source_missing = not source_version or any(
        marker in normalized_version
        for marker in (
            "未提供", "未知", "缺失", "无法确认",
            "not provided", "unknown", "missing", "unavailable",
        )
    )
    if source_missing:
        result["source_version"] = source_version or "未提供"
        result["candidate_codes"] = []
        result["hierarchy_notes"] = [
            "未提供可验证的 ICD-10-CN 目录版本，类目层级须由编码员人工核对。"
        ]
        result["inclusion_exclusion_notes"] = [
            "未提供可验证的 ICD-10-CN 目录版本，包括/不包括说明须由编码员人工核对。"
        ]
        result["manual_review_required"] = True
        warnings.append("unverified ICD-10 source normalized to manual-review-only output")
    return result, warnings


_CONTRACT_EXTRACTORS: dict[str, callable] = {
    "icoder/ClaimCheckOutput/v4": _extract_governed_claim_check,
    "icoder/DenialAppealOutput/v3": _extract_governed_denial_appeals,
    "icoder/ClinicalEducationOutput/v4": _extract_governed_clinical_education,
    "icoder/ClinicalEducationOutput/v5": _extract_governed_clinical_education,
    "icoder/ClinicalEducationOutput/v6": _extract_governed_clinical_education,
    "icoder/ClinicalGuidelinesOutput/v5": _extract_governed_clinical_guidelines,
    "icoder/ClinicalGuidelinesOutput/v6": _extract_governed_clinical_guidelines,
    "icoder/NoteCompleteness/v1": _extract_note_completeness,
    "icoder/NoteCompletenessOutput/v1": _extract_note_completeness,
    "icoder/NoteCompletenessOutput/v2": _extract_note_completeness,
    "icoder/ComplianceGuardrail/v1": _extract_compliance_guardrail,
    "icoder/ComplianceGuardrailOutput/v1": _extract_compliance_guardrail,
    "icoder/ComplianceGuardrailOutput/v2": _extract_compliance_guardrail,
    "icoder/ComplianceGuardrailOutput/v3": _extract_compliance_guardrail,
    "icoder/ComplianceGuardrailOutput/v4": _extract_compliance_guardrail,
    "icoder/ProcedureExtractor/v1": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v1": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v2": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v3": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v4": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v5": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v6": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v7": _extract_procedure_extractor,
    "icoder/ProcedureCodingOutput/v8": _extract_procedure_extractor,
    "icoder/EvidenceExtractor/v1": _extract_evidence_extractor,
    "icoder/CodedEvidence/v1": _extract_evidence_extractor,
    "icoder/CodedEvidence/v2": _extract_evidence_extractor,
    "icoder/CodedEvidence/v3": _extract_evidence_extractor,
    "icoder/CodedEvidence/v4": _extract_evidence_extractor,
    "icoder/CodedEvidence/v5": _extract_evidence_extractor,
    "icoder/CodedEvidence/v6": _extract_evidence_extractor,
    "icoder/CodedEvidence/v7": _extract_evidence_extractor,
    "icoder/CodedEvidence/v8": _extract_evidence_extractor,
    "icoder/CodedEvidence/v9": _extract_evidence_extractor,
    "icoder/CodedEvidence/v10": _extract_evidence_extractor,
    "icoder/PrincipalDxReview/v1": _extract_principal_dx,
    "icoder/PrincipalDxReview/v2": _extract_principal_dx,
    "icoder/PrincipalDxReview/v3": _extract_principal_dx,
    "icoder/PrincipalDxReview/v4": _extract_principal_dx,
    "icoder/PrincipalDxReview/v5": _extract_principal_dx,
    "icoder/PrincipalDxReview/v6": _extract_principal_dx,
    "icoder/PrincipalDxReview/v7": _extract_principal_dx,
    "icoder/PrincipalDxReview/v8": _extract_principal_dx,
    "icoder/PrincipalDxReview/v9": _extract_principal_dx,
    "icoder/PrincipalDxReview/v10": _extract_principal_dx,
    "icoder/PrincipalDxReview/v11": _extract_governed_principal_dx,
    "icoder/DischargeSummary/v1": _extract_discharge_summary,
    "icoder/DischargeSummaryStructured/v1": _extract_discharge_summary,
    "icoder/DischargeSummaryStructured/v2": _extract_discharge_summary,
    "icoder/DischargeSummaryStructured/v3": _extract_discharge_summary,
    "icoder/DischargeSummaryStructured/v4": _extract_governed_discharge_summary,
    "icoder/DischargeSummaryStructured/v5": _extract_governed_discharge_summary,
    "icoder/ReferralOutput/v3": _extract_governed_referral,
    "icoder/PriorAuthorizationOutput/v3": _extract_governed_prior_authorization,
    "icoder/PriorAuthorizationOutput/v4": _extract_governed_prior_authorization,
    "icoder/PriorAuthorizationOutput/v5": _extract_governed_prior_authorization,
    "icoder/DrgAnalyzer/v1": _extract_drg_analyzer,
    "icoder/DRGDIPRiskReview/v1": _extract_drg_analyzer,
    "icoder/DRGDIPRiskReview/v2": _extract_drg_analyzer,
    "icoder/DRGDIPRiskReview/v3": _extract_drg_analyzer,
    "icoder/DRGDIPRiskReview/v4": _extract_drg_analyzer,
    "icoder/DRGDIPRiskReview/v5": _extract_governed_drg_analyzer,
    "icoder/DRGDIPRiskReview/v6": _extract_governed_drg_analyzer,
    "icoder/DRGDIPRiskReview/v7": _extract_governed_drg_analyzer,
    "icoder/DRGDIPRiskReview/v8": _extract_governed_drg_analyzer,
    "icoder/CodeValidation/v1": _extract_code_validation,
    "icoder/CodeValidationOutput/v2": _extract_code_validation,
    "icoder/CodeValidationOutput/v3": _extract_code_validation,
    "icoder/CodeValidationOutput/v4": _extract_code_validation,
    "icoder/CodeValidationOutput/v5": _extract_code_validation,
    "icoder/DiagnosisExtractionOutput/v1": _extract_diagnosis_extraction,
    "icoder/DiagnosisExtractionOutput/v2": _extract_diagnosis_extraction,
    "icoder/DiagnosisExtractionOutput/v3": _extract_diagnosis_extraction,
    "icoder/DiagnosisExtractionOutput/v4": _extract_diagnosis_extraction,
    "icoder/DiagnosisExtractionOutput/v5": _extract_diagnosis_extraction,
    "icoder/DiagnosisExtractionOutput/v6": _extract_diagnosis_extraction,
    "icoder/DiagnosisExtractionOutput/v7": _extract_diagnosis_extraction,
    "icoder/RuleExplanationOutput/v1": _extract_rule_explanation,
    "icoder/RuleExplanationOutput/v2": _extract_rule_explanation,
    "icoder/RuleExplanationOutput/v3": _extract_rule_explanation,
    "icoder/RuleExplanationOutput/v4": _extract_rule_explanation,
    "icoder/MedicationReconciliationOutput/v3": _extract_medication_reconciliation,
    "icoder/MedicationReconciliationOutput/v4": _extract_medication_reconciliation,
    "icoder/NursingHandoffOutput/v3": _extract_nursing_handoff,
    "icoder/NursingHandoffOutput/v4": _extract_nursing_handoff,
    "icoder/IcuSummaryOutput/v3": _extract_icu_summary,
    "icoder/DischargeEducationOutput/v3": _extract_discharge_education,
    "icoder/Icd10NavigatorOutput/v1": _extract_icd10_navigator,
    "icoder/Icd10NavigatorOutput/v2": _extract_icd10_navigator,
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
