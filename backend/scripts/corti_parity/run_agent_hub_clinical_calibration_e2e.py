"""Run the governed 50-invocation clinical calibration over Agent Hub HTTP.

The suite is intentionally limited to fixture records already classified for
a controlled external-provider development run:

* 40 de-identified, bilingual-derived CDI calibration cases (Chinese input)
* 5 PHI-free synthetic Medical Coding cases in both Chinese and English

CCL-derived 1,800/201/100-case assets are never read by this runner.  The run
is serial, loopback-only, resumable for diagnostics, and requires an explicit
egress acknowledgement.  A passing report remains engineering-team-authored
synthetic calibration evidence, not independent clinical gold.
"""

from __future__ import annotations

import argparse
import copy
import ipaddress
import json
import re
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.icoder.agent_runtime.cdi.domain import EvidenceSpan, ProviderQuery  # noqa: E402
from app.icoder.agent_runtime.cdi.single_dimension_gate import (  # noqa: E402
    evaluate_single_dimension,
)
from scripts.corti_parity.agent_hub_live_evidence import (  # noqa: E402
    canonical_sha256,
    capture_trace_artifact,
    execution_provenance,
    pack_snapshot,
    row_execution_evidence,
    sha256_file,
    utc_now_iso,
)
from scripts.corti_parity.build_agent_hub_clinical_calibration_plan import (  # noqa: E402
    BILINGUAL_FIXTURE,
    CDI_FIXTURE,
    QUALITY_SCOPE,
    _validate_bilingual_fixture,
    _validate_cdi_fixture,
)
from scripts.corti_parity.bilingual_coding_gold_review import (  # noqa: E402
    validate_completed_adjudication,
)
from scripts.corti_parity.run_agent_hub_examples_e2e import (  # noqa: E402
    _assert_native_stacks_not_loaded,
    _evaluate,
    _login,
)


SCHEMA_VERSION = "icoder.agent-hub-clinical-calibration-e2e/v1"
INDEPENDENT_CODING_GOLD_SCOPE = (
    "development_calibration_with_independently_reviewed_bilingual_coding_gold"
)
DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "agent_hub" / "clinical_calibration_e2e"
EXPECTED_CDI_CASES = 40
EXPECTED_BILINGUAL_BASE_CASES = 5
EXPECTED_INVOCATIONS = 50
ESCAPE_PHRASES = (
    "无法确定",
    "不确定",
    "不详",
    "未明确",
    "未知",
    "尚不明确",
    "unable to determine",
    "cannot determine",
    "unknown",
    "not documented",
    "other",
)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {path}: {exc}") from exc


def _loopback_base_url(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base URL must be HTTP(S)")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.casefold() == "localhost"
    if not loopback:
        raise ValueError("clinical calibration is restricted to loopback transport")
    return value.rstrip("/")


def _agent_pack(agents_dir: Path, agent_id: str) -> dict[str, Any]:
    candidates = sorted(agents_dir.glob("*/agent_pack.json"))
    for path in candidates:
        pack = _read_json(path)
        current_id = str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]
        if current_id == agent_id:
            pack["_source_path"] = str(path.resolve())
            return pack
    raise ValueError(f"Agent Pack not found: {agent_id}")


def _domain_result(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    return result if isinstance(result, dict) else {}


def _exact_code(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def _set_f1(expected: set[str], predicted: set[str]) -> float:
    expected = {_exact_code(value) for value in expected if _exact_code(value)}
    predicted = {_exact_code(value) for value in predicted if _exact_code(value)}
    if not expected and not predicted:
        return 1.0
    if not expected or not predicted:
        return 0.0
    true_positive = len(expected & predicted)
    if not true_positive:
        return 0.0
    precision = true_positive / len(predicted)
    recall = true_positive / len(expected)
    return 2 * precision * recall / (precision + recall)


def _span_quotes(item: dict[str, Any]) -> list[str]:
    spans = item.get("evidence_spans")
    spans = spans if isinstance(spans, list) else []
    quotes = [
        str(span.get("quote") or "")
        for span in spans
        if isinstance(span, dict) and str(span.get("quote") or "")
    ]
    if quotes:
        return quotes
    primary = item.get("evidence_span")
    primary = primary if isinstance(primary, dict) else {}
    quote = str(primary.get("quote") or "")
    return [quote] if quote else []


def _provider_query(value: dict[str, Any]) -> ProviderQuery:
    span_value = value.get("evidence_span")
    span_value = span_value if isinstance(span_value, dict) else {}
    span = EvidenceSpan(
        document_id=str(span_value.get("document_id") or "calibration-chart"),
        quote=str(span_value.get("quote") or ""),
        char_start=int(span_value.get("char_start") or 0),
        char_end=int(span_value.get("char_end") or 0),
        documented_at=str(span_value.get("documented_at") or ""),
    )
    return ProviderQuery(
        query_id=str(value.get("query_id") or "calibration-query"),
        gap_id=str(value.get("gap_id") or "calibration-gap"),
        topic=str(value.get("topic") or ""),
        reason=str(value.get("reason") or ""),
        evidence_span=span,
        query_text=str(value.get("query_text") or ""),
        response_options=[str(item) for item in value.get("response_options") or []],
    )


def score_cdi_response(
    *, case: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    result = _domain_result(response)
    chart = str(case.get("chart_zh") or "")
    queries = result.get("proposed_provider_queries")
    queries = [item for item in queries or [] if isinstance(item, dict)]
    gaps = result.get("documentation_gaps")
    gaps = [item for item in gaps or [] if isinstance(item, dict)]
    expected = case.get("expected")
    expected = expected if isinstance(expected, dict) else {}
    minimum = int(expected.get("query_count_min") or 0)
    maximum = int(expected.get("query_count_max") or 0)

    query_quotes = [quote for query in queries for quote in _span_quotes(query)]
    gap_quotes = [quote for gap in gaps for quote in _span_quotes(gap)]
    all_quotes = query_quotes + gap_quotes
    exact_anchor_checks = [bool(quote and quote in chart) for quote in all_quotes]
    single_dimension = [
        evaluate_single_dimension(_provider_query(query)).verdict == "SINGLE_DIM"
        for query in queries
    ]
    option_counts = [len(query.get("response_options") or []) for query in queries]
    escape_checks = [
        any(
            phrase.casefold() in str(option).casefold()
            for option in query.get("response_options") or []
            for phrase in ESCAPE_PHRASES
        )
        for query in queries
    ]
    nlq_checks = [
        str(query.get("nlq_gate_verdict") or "").upper() == "PASS"
        for query in queries
    ]
    human = result.get("human_review")
    human = human if isinstance(human, dict) else {}
    category = str(case.get("category") or "")
    query_count = len(queries)
    return {
        "case_id": str(case.get("case_id") or ""),
        "category": category,
        "query_count": query_count,
        "query_count_min": minimum,
        "query_count_max": maximum,
        "query_count_in_expected_range": minimum <= query_count <= maximum,
        "complete_chart_over_query": category == "complete_chart" and query_count > maximum,
        "clear_gap_under_query": category == "clear_gap" and query_count < minimum,
        "final_queries_single_dimension": all(single_dimension),
        "multi_dimension_final_query_count": sum(not item for item in single_dimension),
        "evidence_span_count": len(all_quotes),
        "evidence_exact_anchor_rate": (
            sum(exact_anchor_checks) / len(exact_anchor_checks)
            if exact_anchor_checks
            else (1.0 if not queries and not gaps else 0.0)
        ),
        "response_options_four_plus_rate": (
            sum(value >= 4 for value in option_counts) / len(option_counts)
            if option_counts
            else 1.0
        ),
        "escape_hatch_rate": (
            sum(escape_checks) / len(escape_checks) if escape_checks else 1.0
        ),
        "non_leading_gate_pass_rate": (
            sum(nlq_checks) / len(nlq_checks) if nlq_checks else 1.0
        ),
        "human_review_enforced": bool(
            human.get("cdi_specialist_review_required") is True
            and human.get("clinician_response_required") is True
        ),
    }


def _expected_codes(case: dict[str, Any]) -> dict[str, set[str] | str]:
    primary = case.get("expected_principal_diagnosis")
    primary = primary if isinstance(primary, dict) else {}
    secondary = case.get("expected_secondary_diagnoses")
    secondary = secondary if isinstance(secondary, list) else []
    procedure = case.get("expected_primary_procedure")
    procedure = procedure if isinstance(procedure, dict) else {}
    return {
        "primary": _exact_code(primary.get("code")),
        "secondary": {
            _exact_code(item.get("code"))
            for item in secondary
            if isinstance(item, dict) and _exact_code(item.get("code"))
        },
        "procedures": (
            {_exact_code(procedure.get("code"))}
            if _exact_code(procedure.get("code"))
            else set()
        ),
    }


def apply_adjudicated_coding_gold(
    cases: list[dict[str, Any]], adjudication: dict[str, Any]
) -> list[dict[str, Any]]:
    """Replace engineering labels with a validated adjudication decision set."""

    decisions = {
        str(item.get("case_id") or ""): item
        for item in adjudication.get("final_decisions") or []
        if isinstance(item, dict)
    }
    if set(decisions) != {str(case.get("case_id") or "") for case in cases}:
        raise ValueError("adjudicated gold must cover every bilingual coding case")
    reviewed_cases: list[dict[str, Any]] = []
    for source_case in cases:
        case = copy.deepcopy(source_case)
        case_id = str(case.get("case_id") or "")
        decision = decisions[case_id]
        principal = decision.get("principal_diagnosis")
        principal = principal if isinstance(principal, dict) else {}
        secondary = decision.get("secondary_diagnoses")
        secondary = secondary if isinstance(secondary, list) else []
        procedure = decision.get("primary_procedure")
        procedure = procedure if isinstance(procedure, dict) else None
        case["expected_principal_diagnosis"] = {
            "code": str(principal.get("code") or "")
        }
        case["expected_secondary_diagnoses"] = [
            {"code": str(item.get("code") or "")}
            for item in secondary
            if isinstance(item, dict)
        ]
        case["expected_primary_procedure"] = (
            {"code": str(procedure.get("code") or "")} if procedure else None
        )
        case["calibration_gold_source"] = "independent_bilingual_coding_adjudication"
        reviewed_cases.append(case)
    return reviewed_cases


def _assigned_code_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    assignment = result.get("code_assignment")
    assignment = assignment if isinstance(assignment, dict) else {}
    items: list[dict[str, Any]] = []
    primary = assignment.get("primary_diagnosis")
    if isinstance(primary, dict) and _exact_code(primary.get("code")):
        items.append(primary)
    for field in ("secondary_diagnoses", "procedures"):
        values = assignment.get(field)
        items.extend(item for item in values or [] if isinstance(item, dict))
    return items


def score_coding_response(
    *, case: dict[str, Any], language: str, response: dict[str, Any]
) -> dict[str, Any]:
    result = _domain_result(response)
    chart = str(case.get("chart_zh") if language == "zh-CN" else case.get("chart_en") or "")
    assignment = result.get("code_assignment")
    assignment = assignment if isinstance(assignment, dict) else {}
    primary = assignment.get("primary_diagnosis")
    primary = primary if isinstance(primary, dict) else {}
    secondary = assignment.get("secondary_diagnoses")
    secondary = [item for item in secondary or [] if isinstance(item, dict)]
    procedures = assignment.get("procedures")
    procedures = [item for item in procedures or [] if isinstance(item, dict)]
    expected = _expected_codes(case)
    predicted_primary = _exact_code(primary.get("code"))
    predicted_secondary = {
        _exact_code(item.get("code"))
        for item in secondary
        if _exact_code(item.get("code"))
    }
    predicted_procedures = {
        _exact_code(item.get("code"))
        for item in procedures
        if _exact_code(item.get("code"))
    }
    assigned = _assigned_code_items(result)
    evidence_checks: list[bool] = []
    for item in assigned:
        evidence = item.get("evidence")
        evidence = [value for value in evidence or [] if isinstance(value, dict)]
        if not evidence:
            evidence_checks.append(False)
            continue
        evidence_checks.extend(
            bool(str(value.get("text") or "") and str(value.get("text") or "") in chart)
            for value in evidence
        )
    validation = result.get("validation_summary")
    validation = validation if isinstance(validation, dict) else {}
    human = result.get("human_review")
    human = human if isinstance(human, dict) else {}
    return {
        "case_id": str(case.get("case_id") or ""),
        "language": language,
        "expected_primary": str(expected["primary"]),
        "predicted_primary": predicted_primary,
        "principal_diagnosis_exact_match": predicted_primary == expected["primary"],
        "expected_secondary": sorted(expected["secondary"]),
        "predicted_secondary": sorted(predicted_secondary),
        "secondary_diagnosis_set_f1": _set_f1(
            expected["secondary"], predicted_secondary
        ),
        "expected_procedures": sorted(expected["procedures"]),
        "predicted_procedures": sorted(predicted_procedures),
        "primary_procedure_exact_match": predicted_procedures == expected["procedures"],
        "predicted_all_codes": sorted(
            ({predicted_primary} if predicted_primary else set())
            | predicted_secondary
            | predicted_procedures
        ),
        "assigned_code_count": len(assigned),
        "assigned_code_evidence_exact_anchor_rate": (
            sum(evidence_checks) / len(evidence_checks) if evidence_checks else 0.0
        ),
        "human_review_enforced": bool(
            response.get("manual_review_required") is True
            and validation.get("manual_review_required") is True
            and human.get("review_required") is True
        ),
    }


def _execution_checks(
    common_evaluation: dict[str, Any], execution_evidence: dict[str, Any]
) -> dict[str, bool]:
    trace = execution_evidence.get("trace")
    trace = trace if isinstance(trace, dict) else {}
    result_attestation = execution_evidence.get("result_attestation")
    result_attestation = (
        result_attestation if isinstance(result_attestation, dict) else {}
    )
    return {
        "contract_and_safety_passed": common_evaluation.get("passed") is True,
        "result_attestation_signature_verified": (
            result_attestation.get("signature_verified") is True
        ),
        "trace_http_success": trace.get("http_status") == 200,
        "trace_run_id_matches": trace.get("run_id_matches") is True,
        "trace_attestation_signature_verified": (
            trace.get("trace_attestation_signature_verified") is True
        ),
        "real_model_call_observed": trace.get("model_call_observed") is True,
        "non_mock_model": trace.get("mock_detected") is False,
        "non_degraded_model": trace.get("degraded_detected") is False,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cdi = [row for row in rows if row.get("suite_id") == "cdi_zh_40"]
    coding = [
        row
        for row in rows
        if row.get("suite_id") == "medical_coding_bilingual_seed_5x2"
    ]
    execution_valid = bool(rows) and all(
        all((row.get("execution_checks") or {}).values()) for row in rows
    )
    cdi_scores = [row.get("calibration") or {} for row in cdi]
    coding_scores = [row.get("calibration") or {} for row in coding]
    query_total = sum(int(score.get("query_count") or 0) for score in cdi_scores)
    bilingual_pairs: dict[str, dict[str, set[str]]] = {}
    for score in coding_scores:
        case_id = str(score.get("case_id") or "")
        language = str(score.get("language") or "")
        bilingual_pairs.setdefault(case_id, {})[language] = set(
            score.get("predicted_all_codes") or []
        )
    pair_checks = [
        languages.get("zh-CN", set()) == languages.get("en-US", set())
        and set(languages) == {"zh-CN", "en-US"}
        for languages in bilingual_pairs.values()
    ]
    procedure_cases = [score for score in coding_scores if score.get("expected_procedures")]
    metrics = {
        "execution": {
            "fresh_real_model_attested_rate": (
                sum(all((row.get("execution_checks") or {}).values()) for row in rows)
                / len(rows)
                if rows
                else 0.0
            ),
            "valid": execution_valid and len(rows) == EXPECTED_INVOCATIONS,
        },
        "cdi": {
            "case_count": len(cdi_scores),
            "query_count_expected_range_rate": (
                sum(bool(score.get("query_count_in_expected_range")) for score in cdi_scores)
                / len(cdi_scores)
                if cdi_scores
                else 0.0
            ),
            "complete_chart_over_query_rate": (
                sum(bool(score.get("complete_chart_over_query")) for score in cdi_scores)
                / max(1, sum(score.get("category") == "complete_chart" for score in cdi_scores))
            ),
            "clear_gap_under_query_rate": (
                sum(bool(score.get("clear_gap_under_query")) for score in cdi_scores)
                / max(1, sum(score.get("category") == "clear_gap" for score in cdi_scores))
            ),
            "final_query_single_dimension_rate_recomputed": (
                1.0
                - sum(int(score.get("multi_dimension_final_query_count") or 0) for score in cdi_scores)
                / query_total
                if query_total
                else 1.0
            ),
            "evidence_exact_anchor_rate": (
                sum(float(score.get("evidence_exact_anchor_rate") or 0.0) for score in cdi_scores)
                / len(cdi_scores)
                if cdi_scores
                else 0.0
            ),
            "response_options_four_plus_rate": (
                sum(float(score.get("response_options_four_plus_rate") or 0.0) for score in cdi_scores)
                / len(cdi_scores)
                if cdi_scores
                else 0.0
            ),
            "escape_hatch_rate": (
                sum(float(score.get("escape_hatch_rate") or 0.0) for score in cdi_scores)
                / len(cdi_scores)
                if cdi_scores
                else 0.0
            ),
            "non_leading_gate_pass_rate": (
                sum(float(score.get("non_leading_gate_pass_rate") or 0.0) for score in cdi_scores)
                / len(cdi_scores)
                if cdi_scores
                else 0.0
            ),
            "human_review_enforcement_rate": (
                sum(bool(score.get("human_review_enforced")) for score in cdi_scores)
                / len(cdi_scores)
                if cdi_scores
                else 0.0
            ),
        },
        "medical_coding": {
            "invocation_count": len(coding_scores),
            "base_case_count": len(bilingual_pairs),
            "principal_diagnosis_exact_match_rate": (
                sum(bool(score.get("principal_diagnosis_exact_match")) for score in coding_scores)
                / len(coding_scores)
                if coding_scores
                else 0.0
            ),
            "secondary_diagnosis_set_f1": (
                sum(float(score.get("secondary_diagnosis_set_f1") or 0.0) for score in coding_scores)
                / len(coding_scores)
                if coding_scores
                else 0.0
            ),
            "primary_procedure_exact_match_rate": (
                sum(bool(score.get("primary_procedure_exact_match")) for score in procedure_cases)
                / len(procedure_cases)
                if procedure_cases
                else 1.0
            ),
            "assigned_code_evidence_exact_anchor_rate": (
                sum(float(score.get("assigned_code_evidence_exact_anchor_rate") or 0.0) for score in coding_scores)
                / len(coding_scores)
                if coding_scores
                else 0.0
            ),
            "cross_language_code_set_consistency_rate": (
                sum(pair_checks) / len(pair_checks) if pair_checks else 0.0
            ),
            "human_review_enforcement_rate": (
                sum(bool(score.get("human_review_enforced")) for score in coding_scores)
                / len(coding_scores)
                if coding_scores
                else 0.0
            ),
        },
    }
    targets = {
        "cdi_case_count_40": len(cdi_scores) == EXPECTED_CDI_CASES,
        "coding_invocation_count_10": len(coding_scores) == 2 * EXPECTED_BILINGUAL_BASE_CASES,
        "execution_valid": metrics["execution"]["valid"],
        "cdi_expected_range_rate_1": metrics["cdi"]["query_count_expected_range_rate"] == 1.0,
        "cdi_complete_over_query_rate_0": metrics["cdi"]["complete_chart_over_query_rate"] == 0.0,
        "cdi_clear_gap_under_query_rate_0": metrics["cdi"]["clear_gap_under_query_rate"] == 0.0,
        "cdi_single_dimension_rate_1": metrics["cdi"]["final_query_single_dimension_rate_recomputed"] == 1.0,
        "cdi_evidence_anchor_rate_1": metrics["cdi"]["evidence_exact_anchor_rate"] == 1.0,
        "cdi_non_leading_rate_1": metrics["cdi"]["non_leading_gate_pass_rate"] == 1.0,
        "coding_principal_exact_rate_ge_0_8": metrics["medical_coding"]["principal_diagnosis_exact_match_rate"] >= 0.8,
        "coding_secondary_f1_ge_0_7": metrics["medical_coding"]["secondary_diagnosis_set_f1"] >= 0.7,
        "coding_procedure_exact_rate_ge_0_8": metrics["medical_coding"]["primary_procedure_exact_match_rate"] >= 0.8,
        "coding_bilingual_consistency_ge_0_8": metrics["medical_coding"]["cross_language_code_set_consistency_rate"] >= 0.8,
        "coding_evidence_anchor_rate_1": metrics["medical_coding"]["assigned_code_evidence_exact_anchor_rate"] == 1.0,
        "human_review_rate_1": (
            metrics["cdi"]["human_review_enforcement_rate"] == 1.0
            and metrics["medical_coding"]["human_review_enforcement_rate"] == 1.0
        ),
    }
    return {
        "metrics": metrics,
        "targets": targets,
        "execution_valid": targets["execution_valid"],
        "calibration_targets_passed": all(targets.values()),
        "failed_targets": sorted(key for key, value in targets.items() if not value),
    }


def _write_report(
    *,
    out_dir: Path,
    rows: list[dict[str, Any]],
    base_url: str,
    session_started_at: str,
    packs: list[dict[str, Any]],
    gold_review_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aggregate_result = aggregate(rows)
    independent_gold_used = gold_review_snapshot is not None
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality_scope": (
            INDEPENDENT_CODING_GOLD_SCOPE
            if independent_gold_used
            else QUALITY_SCOPE
        ),
        "status": (
            "passed_development_calibration"
            if aggregate_result["calibration_targets_passed"]
            else "quality_gaps"
            if aggregate_result["execution_valid"]
            else "invalid_or_incomplete_evidence"
        ),
        "execution_provenance": execution_provenance(
            rows, base_url=base_url, session_started_at=session_started_at
        ),
        "fixture_snapshot": {
            "cdi": {
                "path": str(CDI_FIXTURE.resolve()),
                "sha256": sha256_file(CDI_FIXTURE),
                "case_count": EXPECTED_CDI_CASES,
            },
            "medical_coding_bilingual": {
                "path": str(BILINGUAL_FIXTURE.resolve()),
                "sha256": sha256_file(BILINGUAL_FIXTURE),
                "base_case_count": EXPECTED_BILINGUAL_BASE_CASES,
                "language_invocations": 2,
            },
        },
        "agent_snapshot": pack_snapshot(packs),
        "summary": aggregate_result,
        "rows": rows,
        "claim_boundaries": {
            "clinical_accuracy_proven": False,
            "independent_gold_used": independent_gold_used,
            "corti_parity_proven": False,
            "hospital_acceptance_proven": False,
            "production_ready_proven": False,
        },
        "limitations": [
            "The CDI cases are teacher-calibration fixtures, not independent clinical gold.",
            (
                "The five bilingual coding cases use externally reviewed adjudicated labels, but ten language invocations are too small for production accuracy claims."
                if independent_gold_used
                else "The five bilingual coding cases are synthetic and engineering-team-authored; ten language invocations are too small for production accuracy claims."
            ),
            "CCL-derived 1,800/201/100-case records were not read or sent to the external provider.",
            "Corti head-to-head, independent coder review, hospital-distribution validation, and production acceptance remain external gates.",
        ],
    }
    if gold_review_snapshot is not None:
        report["gold_review_snapshot"] = gold_review_snapshot
    report["report_sha256"] = canonical_sha256(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "agent_hub_clinical_calibration_e2e.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def validate_report_file(report_path: Path) -> list[str]:
    """Validate report digest, scope, counts, and bound source artifacts."""

    errors: list[str] = []
    report_path = report_path.resolve()
    try:
        report = _read_json(report_path)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(report, dict):
        return ["clinical calibration report is not an object"]
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported clinical calibration schema_version")
    quality_scope = report.get("quality_scope")
    if quality_scope not in {QUALITY_SCOPE, INDEPENDENT_CODING_GOLD_SCOPE}:
        errors.append("clinical calibration quality_scope is missing or overstated")
    supplied_digest = str(report.get("report_sha256") or "")
    digest_payload = dict(report)
    digest_payload.pop("report_sha256", None)
    if supplied_digest != canonical_sha256(digest_payload):
        errors.append("clinical calibration canonical digest mismatch")
    rows = report.get("rows")
    rows = rows if isinstance(rows, list) else []
    if len(rows) != EXPECTED_INVOCATIONS:
        errors.append("clinical calibration must contain exactly 50 rows")
    counts = Counter(str(row.get("suite_id") or "") for row in rows if isinstance(row, dict))
    if counts.get("cdi_zh_40") != 40:
        errors.append("clinical calibration must contain 40 CDI rows")
    if counts.get("medical_coding_bilingual_seed_5x2") != 10:
        errors.append("clinical calibration must contain 10 bilingual coding rows")
    claims = report.get("claim_boundaries")
    claims = claims if isinstance(claims, dict) else {}
    for field in (
        "clinical_accuracy_proven",
        "corti_parity_proven",
        "hospital_acceptance_proven",
        "production_ready_proven",
    ):
        if claims.get(field) is not False:
            errors.append(f"clinical calibration claim boundary must be false: {field}")
    independent_gold_used = claims.get("independent_gold_used") is True
    if independent_gold_used != (quality_scope == INDEPENDENT_CODING_GOLD_SCOPE):
        errors.append("independent gold claim does not match quality_scope")
    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    rebuilt_summary = aggregate(rows)
    if summary != rebuilt_summary:
        errors.append("clinical calibration aggregate does not match its rows")
    root = report_path.parent
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row[{index}] is not an object")
            continue
        evidence = row.get("execution_evidence")
        evidence = evidence if isinstance(evidence, dict) else {}
        if evidence.get("artifact_source") != "run":
            errors.append(f"row[{index}] is not a fresh HTTP run")
        response_path = Path(str(row.get("response_path") or ""))
        trace = evidence.get("trace")
        trace = trace if isinstance(trace, dict) else {}
        trace_path = Path(str(trace.get("artifact_path") or ""))
        for label, path, expected_hash in (
            ("response", response_path, str(evidence.get("response_sha256") or "")),
            ("trace", trace_path, str(trace.get("artifact_sha256") or "")),
        ):
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                errors.append(f"row[{index}] {label} artifact escapes report directory")
                continue
            if not resolved.is_file():
                errors.append(f"row[{index}] {label} artifact is missing")
            elif sha256_file(resolved) != expected_hash:
                errors.append(f"row[{index}] {label} artifact digest mismatch")
    fixtures = report.get("fixture_snapshot")
    fixtures = fixtures if isinstance(fixtures, dict) else {}
    expected_fixtures = {
        "cdi": CDI_FIXTURE,
        "medical_coding_bilingual": BILINGUAL_FIXTURE,
    }
    for label, path in expected_fixtures.items():
        supplied = fixtures.get(label)
        supplied = supplied if isinstance(supplied, dict) else {}
        if str(supplied.get("sha256") or "") != sha256_file(path):
            errors.append(f"{label} fixture digest mismatch")
    gold_snapshot = report.get("gold_review_snapshot")
    if independent_gold_used:
        gold_snapshot = gold_snapshot if isinstance(gold_snapshot, dict) else {}
        artifacts = gold_snapshot.get("artifacts")
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        required = {"packet", "review_a", "review_b", "adjudication"}
        if gold_snapshot.get("validation_passed") is not True or set(artifacts) != required:
            errors.append("independent gold snapshot is missing or incomplete")
        resolved_artifacts: dict[str, Path] = {}
        for label in required:
            metadata = artifacts.get(label)
            metadata = metadata if isinstance(metadata, dict) else {}
            path = Path(str(metadata.get("path") or ""))
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                errors.append(f"gold review {label} artifact escapes report directory")
                continue
            resolved_artifacts[label] = resolved
            if not resolved.is_file():
                errors.append(f"gold review {label} artifact is missing")
            elif sha256_file(resolved) != str(metadata.get("sha256") or ""):
                errors.append(f"gold review {label} artifact digest mismatch")
        if set(resolved_artifacts) == required and all(
            path.is_file() for path in resolved_artifacts.values()
        ):
            adjudication_errors = validate_completed_adjudication(
                _read_json(resolved_artifacts["packet"]),
                _read_json(resolved_artifacts["review_a"]),
                _read_json(resolved_artifacts["review_b"]),
                _read_json(resolved_artifacts["adjudication"]),
            )
            errors.extend(
                f"gold review validation: {item}" for item in adjudication_errors
            )
    elif gold_snapshot is not None:
        errors.append("synthetic calibration cannot attach an independent gold snapshot")
    return sorted(set(errors))


def _run_case(
    *,
    base_url: str,
    headers: dict[str, str],
    pack: dict[str, Any],
    suite_id: str,
    case_id: str,
    language: str,
    text: str,
    response_path: Path,
    trace_path: Path,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started_at = utc_now_iso()
    started = time.perf_counter()
    try:
        agent_id = str(pack["agent_ref"]).rsplit("/", 1)[-1].split("@", 1)[0]
        request_extra: dict[str, Any] = {
            "calibration_case_id": case_id,
            "calibration_suite_id": suite_id,
            "language": language,
        }
        if agent_id == "medical-coding-agent":
            # The Pack promises both diagnosis and procedure coding.  Make
            # the governed calibration request explicit so procedure quality
            # is measured against an actually requested ICD-9-CM-3 output.
            request_extra["coding_systems"] = ["icd10cn", "icd9cm3"]
        raw = requests.post(
            f"{base_url}/api/v1/agents/{agent_id}/run",
            headers=headers,
            json={
                "input": {
                    "text": text,
                    "extra": request_extra,
                },
                "include_trace": True,
                "include_evidence": True,
            },
            timeout=timeout,
        )
        try:
            response = raw.json()
        except ValueError:
            response = {
                "error": True,
                "error_reason": "non_json_response",
                "body": raw.text[:1000],
            }
        response["_http_status"] = raw.status_code
    except requests.RequestException as exc:
        response = {
            "_http_status": 0,
            "error": True,
            "error_reason": type(exc).__name__,
            "summary": str(exc)[:500],
        }
    response["_elapsed_seconds"] = round(time.perf_counter() - started, 3)
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(
        json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    trace_evidence = capture_trace_artifact(
        base_url=base_url,
        headers=headers,
        response=response,
        trace_path=trace_path,
        timeout=timeout,
    )
    completed_at = utc_now_iso()
    evidence = row_execution_evidence(
        action="run",
        response=response,
        response_path=response_path,
        pack=pack,
        trace_evidence=trace_evidence,
        started_at=started_at,
        completed_at=completed_at,
    )
    return response, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--allow-self-register", action="store_true")
    parser.add_argument(
        "--acknowledge-external-provider-egress",
        action="store_true",
        help="Acknowledge that the 50 allowed synthetic/de-identified inputs will reach the configured model provider.",
    )
    parser.add_argument(
        "--case-ids",
        default="",
        help="Diagnostic subset only; a subset can never satisfy the 50-invocation gate.",
    )
    parser.add_argument("--blind-review-packet", type=Path)
    parser.add_argument("--review-a", type=Path)
    parser.add_argument("--review-b", type=Path)
    parser.add_argument("--gold-adjudication", type=Path)
    args = parser.parse_args()
    if not args.acknowledge_external_provider_egress:
        raise SystemExit(
            "--acknowledge-external-provider-egress is required for this controlled run"
        )
    base_url = _loopback_base_url(args.base_url)
    _assert_native_stacks_not_loaded()
    cdi_payload = _read_json(CDI_FIXTURE)
    cdi_cases, cdi_errors = _validate_cdi_fixture(cdi_payload)
    bilingual_payload = _read_json(BILINGUAL_FIXTURE)
    bilingual_cases, bilingual_errors = _validate_bilingual_fixture(
        bilingual_payload
    )
    fixture_errors = cdi_errors + bilingual_errors
    if fixture_errors:
        raise SystemExit("fixture governance failed: " + "; ".join(fixture_errors))

    out_dir = args.out_dir.resolve()
    review_inputs = {
        "packet": args.blind_review_packet,
        "review_a": args.review_a,
        "review_b": args.review_b,
        "adjudication": args.gold_adjudication,
    }
    supplied_review_inputs = {
        name: path for name, path in review_inputs.items() if path is not None
    }
    gold_review_snapshot: dict[str, Any] | None = None
    if supplied_review_inputs and set(supplied_review_inputs) != set(review_inputs):
        raise SystemExit(
            "independent gold requires --blind-review-packet, --review-a, "
            "--review-b, and --gold-adjudication together"
        )
    if supplied_review_inputs:
        review_documents = {
            name: _read_json(path.resolve())
            for name, path in supplied_review_inputs.items()
        }
        review_errors = validate_completed_adjudication(
            review_documents["packet"],
            review_documents["review_a"],
            review_documents["review_b"],
            review_documents["adjudication"],
        )
        if review_errors:
            raise SystemExit(
                "independent gold governance failed: " + "; ".join(review_errors)
            )
        bilingual_cases = apply_adjudicated_coding_gold(
            bilingual_cases, review_documents["adjudication"]
        )
        copied_dir = out_dir / "gold_review_inputs"
        copied_dir.mkdir(parents=True, exist_ok=True)
        copied_paths: dict[str, Path] = {}
        filenames = {
            "packet": "blind_review_packet.json",
            "review_a": "reviewer_a_response.json",
            "review_b": "reviewer_b_response.json",
            "adjudication": "gold_adjudication.json",
        }
        for name, source in supplied_review_inputs.items():
            destination = copied_dir / filenames[name]
            shutil.copy2(source.resolve(), destination)
            copied_paths[name] = destination.resolve()
        gold_review_snapshot = {
            "validation_passed": True,
            "independent_bilingual_coding_gold_used": True,
            "packet_sha256": review_documents["packet"].get("packet_sha256"),
            "adjudication_sha256": review_documents["adjudication"].get(
                "adjudication_sha256"
            ),
            "artifacts": {
                name: {
                    "path": str(path),
                    "sha256": sha256_file(path),
                }
                for name, path in copied_paths.items()
            },
        }

    agents_dir = args.agents_dir.resolve()
    cdi_pack = _agent_pack(agents_dir, "clinical-documentation-improvement-agent")
    coding_pack = _agent_pack(agents_dir, "medical-coding-agent")
    packs = [cdi_pack, coding_pack]
    selected = {value.strip() for value in args.case_ids.split(",") if value.strip()}
    invocations: list[dict[str, Any]] = []
    for case in cdi_cases:
        invocations.append(
            {
                "suite_id": "cdi_zh_40",
                "case_id": str(case["case_id"]),
                "language": "zh-CN",
                "text": str(case["chart_zh"]),
                "case": case,
                "pack": cdi_pack,
            }
        )
    for case in bilingual_cases:
        for language, field in (("zh-CN", "chart_zh"), ("en-US", "chart_en")):
            invocations.append(
                {
                    "suite_id": "medical_coding_bilingual_seed_5x2",
                    "case_id": str(case["case_id"]),
                    "language": language,
                    "text": str(case[field]),
                    "case": case,
                    "pack": coding_pack,
                }
            )
    if selected:
        invocations = [item for item in invocations if item["case_id"] in selected]
        missing = selected - {item["case_id"] for item in invocations}
        if missing:
            raise SystemExit(f"unknown case IDs: {sorted(missing)}")
    if not selected and len(invocations) != EXPECTED_INVOCATIONS:
        raise SystemExit(
            f"governed full suite must contain {EXPECTED_INVOCATIONS} invocations"
        )

    token = _login(base_url, allow_self_register=args.allow_self_register)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    responses_dir = out_dir / "responses"
    traces_dir = out_dir / "traces"
    rows: list[dict[str, Any]] = []
    session_started_at = utc_now_iso()
    for index, item in enumerate(invocations, 1):
        _assert_native_stacks_not_loaded()
        artifact_id = f"{item['suite_id']}__{item['case_id']}__{item['language']}"
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", artifact_id)
        response, evidence = _run_case(
            base_url=base_url,
            headers=headers,
            pack=item["pack"],
            suite_id=item["suite_id"],
            case_id=item["case_id"],
            language=item["language"],
            text=item["text"],
            response_path=responses_dir / f"{safe_id}.json",
            trace_path=traces_dir / f"{safe_id}.json",
            timeout=args.timeout,
        )
        common = _evaluate(item["pack"], response, input_text=item["text"])
        calibration = (
            score_cdi_response(case=item["case"], response=response)
            if item["suite_id"] == "cdi_zh_40"
            else score_coding_response(
                case=item["case"], language=item["language"], response=response
            )
        )
        checks = _execution_checks(common, evidence)
        rows.append(
            {
                "suite_id": item["suite_id"],
                "case_id": item["case_id"],
                "language": item["language"],
                "agent_id": str(item["pack"]["agent_ref"])
                .rsplit("/", 1)[-1]
                .split("@", 1)[0],
                "http_status": response.get("_http_status", 0),
                "elapsed_seconds": response.get("_elapsed_seconds", 0),
                "response_path": str((responses_dir / f"{safe_id}.json").resolve()),
                "execution_checks": checks,
                "execution_evidence": evidence,
                "common_evaluation": common,
                "calibration": calibration,
            }
        )
        report = _write_report(
            out_dir=out_dir,
            rows=rows,
            base_url=base_url,
            session_started_at=session_started_at,
            packs=packs,
            gold_review_snapshot=gold_review_snapshot,
        )
        print(
            f"[{index:02d}/{len(invocations)}] {artifact_id}: "
            f"{'PASS' if all(checks.values()) else 'FAIL'} "
            f"http={response.get('_http_status', 0)} status={report['status']}",
            flush=True,
        )
        if index < len(invocations) and args.delay > 0:
            time.sleep(args.delay)

    final = _write_report(
        out_dir=out_dir,
        rows=rows,
        base_url=base_url,
        session_started_at=session_started_at,
        packs=packs,
        gold_review_snapshot=gold_review_snapshot,
    )
    report_path = out_dir / "agent_hub_clinical_calibration_e2e.json"
    validation_errors = validate_report_file(report_path)
    if validation_errors:
        print(json.dumps({"validation_errors": validation_errors}, ensure_ascii=False, indent=2))
        return 3
    print(
        json.dumps(
            {
                "status": final["status"],
                "invocations": len(rows),
                "execution_valid": final["summary"]["execution_valid"],
                "failed_targets": final["summary"]["failed_targets"],
                "report": str(
                    report_path.resolve()
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if final["summary"]["calibration_targets_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
