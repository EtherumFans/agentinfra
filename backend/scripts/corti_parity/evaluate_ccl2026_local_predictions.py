"""Evaluate CCL 2026 code predictions inside a local, aggregate-only boundary.

The prediction packet is intentionally a transient sensitive artifact because it
contains case-level code predictions.  It must live below an explicitly supplied
isolated root.  This evaluator never copies that packet and emits only aggregate
counts, metrics, hashes, and conservative claim boundaries.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.corti_parity.audit_ccl2026_local_dataset import (  # noqa: E402
    _canonical_sha256,
    _sha256_file,
    validate_report as validate_dataset_audit,
)


PACKET_SCHEMA = "icoder.ccl2026-local-prediction-packet/v1"
REPORT_SCHEMA = "icoder.ccl2026-local-aggregate-evaluation/v1"
QUALITY_SCOPE = (
    "local_isolated_ccl2026_train_predictions_not_independent_clinical_gold"
)
ALLOWED_PROVIDER_CLASSES = {
    "local_model",
    "local_deterministic_baseline",
    "oracle_test_only",
}
ALLOWED_FAILURE_CATEGORIES = {
    "model_error",
    "timeout",
    "validation_error",
    "capacity",
    "cancelled",
    "other",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

TOP_LEVEL_KEYS = {
    "schema_version",
    "generated_at",
    "quality_scope",
    "dataset_binding",
    "run_metadata",
    "predictions",
}
DATASET_BINDING_KEYS = {
    "source_workbook_sha256",
    "fixture_sha256",
    "audit_report_sha256",
    "audit_report_canonical_sha256",
    "case_count",
}
RUN_METADATA_KEYS = {
    "execution_environment",
    "provider_class",
    "model_id",
    "model_revision",
    "network_used",
    "external_provider_used",
    "clinical_text_included",
    "raw_model_responses_persisted",
    "oracle_test_only",
}
PREDICTION_KEYS = {
    "case_digest",
    "status",
    "principal_diagnosis",
    "secondary_diagnoses",
    "principal_procedure",
    "other_procedures",
    "failure_category",
}
FORBIDDEN_REPORT_KEYS = {
    "predictions",
    "per_case",
    "case_digest",
    "encounter_id",
    "text",
    "chart",
    "admission_reason",
    "gold",
    "predicted",
    "error_examples",
}


def _exact_code(value: Any) -> str:
    """Normalize presentation only; never collapse code subdivisions."""

    return str(value or "").strip().upper()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read required JSON artifact: {type(exc).__name__}") from exc


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _case_digest(case: dict[str, Any]) -> str:
    return _canonical_sha256(case)


def _safe_identifier(value: Any) -> bool:
    return isinstance(value, str) and SAFE_ID_RE.fullmatch(value) is not None


def _safe_identifier_or_empty(value: Any) -> str:
    return value if _safe_identifier(value) else ""


def _safe_sha256_or_empty(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if re.fullmatch(r"[0-9a-f]{64}", normalized) else ""


def _exact_keyset(value: Any, expected: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == expected


def _code_list(value: Any) -> tuple[list[str], bool]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [], False
    normalized = [_exact_code(item) for item in value]
    valid = all(normalized) and len(normalized) == len(set(normalized))
    return normalized, valid


def _catalog_sets() -> tuple[set[str], set[str], dict[str, Any]]:
    from data.code_dicts.icd_data import load_catalogs

    diagnoses, procedures, status = load_catalogs()
    return (
        {_exact_code(code) for code, _name, _chapter in diagnoses},
        {_exact_code(code) for code, _name, _drg in procedures},
        dict(status),
    )


def build_oracle_test_packet(
    *,
    cases: list[dict[str, Any]],
    audit_report: dict[str, Any],
    audit_file_sha256: str,
    fixture_sha256: str,
    model_id: str = "oracle-contract-self-test",
) -> dict[str, Any]:
    """Build an explicit oracle-only packet for evaluator contract testing."""

    predictions = []
    for case in cases:
        predictions.append({
            "case_digest": _case_digest(case),
            "status": "completed",
            "principal_diagnosis": _exact_code(
                case.get("expected_principal_diagnosis")
            ),
            "secondary_diagnoses": [
                _exact_code(code)
                for code in case.get("expected_secondary_diagnoses") or []
            ],
            "principal_procedure": (
                _exact_code(case.get("expected_principal_procedure")) or None
            ),
            "other_procedures": [
                _exact_code(code) for code in case.get("expected_procedure_codes") or []
            ],
            "failure_category": None,
        })
    return {
        "schema_version": PACKET_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality_scope": QUALITY_SCOPE,
        "dataset_binding": {
            "source_workbook_sha256": str(
                (audit_report.get("source_workbook") or {}).get("sha256") or ""
            ),
            "fixture_sha256": fixture_sha256,
            "audit_report_sha256": audit_file_sha256,
            "audit_report_canonical_sha256": str(
                audit_report.get("report_sha256") or ""
            ),
            "case_count": len(cases),
        },
        "run_metadata": {
            "execution_environment": "local_isolated",
            "provider_class": "oracle_test_only",
            "model_id": model_id,
            "model_revision": "test-only",
            "network_used": False,
            "external_provider_used": False,
            "clinical_text_included": False,
            "raw_model_responses_persisted": False,
            "oracle_test_only": True,
        },
        "predictions": predictions,
    }


def _micro_metrics(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
    recall = tp / (tp + fn) if tp + fn else (1.0 if fp == 0 else 0.0)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "true_positive_count": tp,
        "false_positive_count": fp,
        "false_negative_count": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _set_counts(gold: set[str], predicted: set[str]) -> tuple[int, int, int, float]:
    tp = len(gold & predicted)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not gold else 0.0)
    recall = tp / (tp + fn) if tp + fn else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return tp, fp, fn, f1


def _score(
    cases: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> dict[str, Any]:
    total = len(cases)
    completed = sum(item["status"] == "completed" for item in predictions)
    principal_dx_correct = 0
    principal_proc_correct = 0
    principal_proc_gold_present = 0
    principal_proc_predicted_present = 0
    principal_proc_correct_when_gold_present = 0
    full_set_correct = 0
    secondary_totals = [0, 0, 0]
    other_proc_totals = [0, 0, 0]
    all_dx_totals = [0, 0, 0]
    all_proc_totals = [0, 0, 0]
    secondary_macro: list[float] = []
    other_proc_macro: list[float] = []

    for case, prediction in zip(cases, predictions, strict=True):
        gold_principal_dx = _exact_code(case.get("expected_principal_diagnosis"))
        gold_secondary = {
            _exact_code(code)
            for code in case.get("expected_secondary_diagnoses") or []
        }
        gold_principal_proc = _exact_code(case.get("expected_principal_procedure"))
        gold_other_proc = {
            _exact_code(code) for code in case.get("expected_procedure_codes") or []
        }

        if prediction["status"] == "completed":
            pred_principal_dx = prediction["principal_diagnosis"]
            pred_secondary = set(prediction["secondary_diagnoses"])
            pred_principal_proc = prediction["principal_procedure"] or ""
            pred_other_proc = set(prediction["other_procedures"])
        else:
            pred_principal_dx = ""
            pred_secondary = set()
            pred_principal_proc = ""
            pred_other_proc = set()

        principal_dx_correct += pred_principal_dx == gold_principal_dx
        principal_proc_correct += pred_principal_proc == gold_principal_proc
        principal_proc_gold_present += bool(gold_principal_proc)
        principal_proc_predicted_present += bool(pred_principal_proc)
        principal_proc_correct_when_gold_present += bool(
            gold_principal_proc and pred_principal_proc == gold_principal_proc
        )
        secondary = _set_counts(gold_secondary, pred_secondary)
        other_proc = _set_counts(gold_other_proc, pred_other_proc)
        for index in range(3):
            secondary_totals[index] += secondary[index]
            other_proc_totals[index] += other_proc[index]
        secondary_macro.append(secondary[3])
        other_proc_macro.append(other_proc[3])

        gold_dx = gold_secondary | {gold_principal_dx}
        pred_dx = pred_secondary | ({pred_principal_dx} if pred_principal_dx else set())
        gold_proc = gold_other_proc | ({gold_principal_proc} if gold_principal_proc else set())
        pred_proc = pred_other_proc | ({pred_principal_proc} if pred_principal_proc else set())
        all_dx = _set_counts(gold_dx, pred_dx)
        all_proc = _set_counts(gold_proc, pred_proc)
        for index in range(3):
            all_dx_totals[index] += all_dx[index]
            all_proc_totals[index] += all_proc[index]
        full_set_correct += gold_dx == pred_dx and gold_proc == pred_proc

    denominator = total or 1
    return {
        "case_count": total,
        "completed_case_count": completed,
        "safe_failure_case_count": total - completed,
        "execution_coverage": round(completed / denominator, 6),
        "principal_diagnosis_exact_accuracy": round(
            principal_dx_correct / denominator, 6
        ),
        "secondary_diagnosis": {
            **_micro_metrics(*secondary_totals),
            "macro_case_f1": round(sum(secondary_macro) / denominator, 6),
        },
        "all_diagnosis": _micro_metrics(*all_dx_totals),
        "principal_procedure_exact_accuracy": round(
            principal_proc_correct / denominator, 6
        ),
        "principal_procedure_gold_present_case_count": principal_proc_gold_present,
        "principal_procedure_predicted_present_case_count": (
            principal_proc_predicted_present
        ),
        "principal_procedure_exact_accuracy_when_gold_present": round(
            principal_proc_correct_when_gold_present / principal_proc_gold_present,
            6,
        ) if principal_proc_gold_present else 1.0,
        "other_procedure": {
            **_micro_metrics(*other_proc_totals),
            "macro_case_f1": round(sum(other_proc_macro) / denominator, 6),
        },
        "all_procedure": _micro_metrics(*all_proc_totals),
        "full_code_set_exact_match_rate": round(full_set_correct / denominator, 6),
    }


def _packet_errors(
    *,
    packet: Any,
    expected_case_digests: list[str],
    audit_report: dict[str, Any],
    audit_file_sha256: str,
    fixture_sha256: str,
    diagnosis_catalog: set[str],
    procedure_catalog: set[str],
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    counts = {
        "prediction_row_count": 0,
        "completed_case_count": 0,
        "safe_failure_case_count": 0,
        "duplicate_case_digest_count": 0,
        "missing_case_digest_count": 0,
        "unexpected_case_digest_count": 0,
        "invalid_diagnosis_assignment_count": 0,
        "invalid_procedure_assignment_count": 0,
        "malformed_prediction_row_count": 0,
    }
    if not _exact_keyset(packet, TOP_LEVEL_KEYS):
        return ["prediction packet top-level schema is not exact"], normalized, counts
    if packet.get("schema_version") != PACKET_SCHEMA:
        errors.append("unsupported prediction packet schema_version")
    if packet.get("quality_scope") != QUALITY_SCOPE:
        errors.append("prediction packet quality_scope is not conservative")
    if not isinstance(packet.get("generated_at"), str) or not packet["generated_at"]:
        errors.append("prediction packet generated_at is missing")

    binding = packet.get("dataset_binding")
    if not _exact_keyset(binding, DATASET_BINDING_KEYS):
        errors.append("dataset binding schema is not exact")
    else:
        expected_source_hash = str(
            (audit_report.get("source_workbook") or {}).get("sha256") or ""
        )
        expected_audit_digest = str(audit_report.get("report_sha256") or "")
        expected = {
            "source_workbook_sha256": expected_source_hash,
            "fixture_sha256": fixture_sha256,
            "audit_report_sha256": audit_file_sha256,
            "audit_report_canonical_sha256": expected_audit_digest,
            "case_count": len(expected_case_digests),
        }
        for key, value in expected.items():
            if binding.get(key) != value:
                errors.append(f"dataset binding mismatch: {key}")

    metadata = packet.get("run_metadata")
    if not _exact_keyset(metadata, RUN_METADATA_KEYS):
        errors.append("run metadata schema is not exact")
    else:
        if metadata.get("execution_environment") != "local_isolated":
            errors.append("execution environment is not local_isolated")
        provider_class = metadata.get("provider_class")
        if provider_class not in ALLOWED_PROVIDER_CLASSES:
            errors.append("provider_class is unsupported")
        for key in ("model_id", "model_revision"):
            if not _safe_identifier(metadata.get(key)):
                errors.append(f"run metadata identifier is invalid: {key}")
        for key in (
            "network_used",
            "external_provider_used",
            "clinical_text_included",
            "raw_model_responses_persisted",
        ):
            if metadata.get(key) is not False:
                errors.append(f"run metadata boundary must remain false: {key}")
        expected_oracle = provider_class == "oracle_test_only"
        if metadata.get("oracle_test_only") is not expected_oracle:
            errors.append("oracle_test_only attestation does not match provider_class")

    rows = packet.get("predictions")
    if not isinstance(rows, list):
        errors.append("predictions must be a list")
        return sorted(set(errors)), normalized, counts
    counts["prediction_row_count"] = len(rows)
    seen: set[str] = set()
    for row in rows:
        if not _exact_keyset(row, PREDICTION_KEYS):
            counts["malformed_prediction_row_count"] += 1
            continue
        digest = row.get("case_digest")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            counts["malformed_prediction_row_count"] += 1
            continue
        if digest in seen:
            counts["duplicate_case_digest_count"] += 1
        seen.add(digest)
        status = row.get("status")
        secondary, secondary_valid = _code_list(row.get("secondary_diagnoses"))
        other_procedures, other_valid = _code_list(row.get("other_procedures"))
        principal_dx = _exact_code(row.get("principal_diagnosis"))
        principal_proc = _exact_code(row.get("principal_procedure")) or None
        if not secondary_valid or not other_valid:
            counts["malformed_prediction_row_count"] += 1
            continue
        if status == "completed":
            counts["completed_case_count"] += 1
            if not principal_dx or row.get("failure_category") is not None:
                counts["malformed_prediction_row_count"] += 1
                continue
            if principal_dx in secondary or (principal_proc and principal_proc in other_procedures):
                counts["malformed_prediction_row_count"] += 1
                continue
        elif status == "failed":
            counts["safe_failure_case_count"] += 1
            if (
                principal_dx
                or secondary
                or principal_proc
                or other_procedures
                or row.get("failure_category") not in ALLOWED_FAILURE_CATEGORIES
            ):
                counts["malformed_prediction_row_count"] += 1
                continue
        else:
            counts["malformed_prediction_row_count"] += 1
            continue
        diagnosis_values = ([principal_dx] if principal_dx else []) + secondary
        procedure_values = ([principal_proc] if principal_proc else []) + other_procedures
        counts["invalid_diagnosis_assignment_count"] += sum(
            code not in diagnosis_catalog for code in diagnosis_values
        )
        counts["invalid_procedure_assignment_count"] += sum(
            code not in procedure_catalog for code in procedure_values
        )
        normalized.append({
            "case_digest": digest,
            "status": status,
            "principal_diagnosis": principal_dx,
            "secondary_diagnoses": secondary,
            "principal_procedure": principal_proc,
            "other_procedures": other_procedures,
            "failure_category": row.get("failure_category"),
        })

    expected_set = set(expected_case_digests)
    counts["missing_case_digest_count"] = len(expected_set - seen)
    counts["unexpected_case_digest_count"] = len(seen - expected_set)
    if len(rows) != len(expected_case_digests):
        errors.append("prediction packet case count is not exact")
    for key in (
        "duplicate_case_digest_count",
        "missing_case_digest_count",
        "unexpected_case_digest_count",
        "malformed_prediction_row_count",
        "invalid_diagnosis_assignment_count",
        "invalid_procedure_assignment_count",
    ):
        if counts[key]:
            errors.append(f"prediction packet integrity failure: {key}")
    if [item.get("case_digest") for item in normalized] != expected_case_digests:
        errors.append("prediction packet order does not match the bound fixture")
    return sorted(set(errors)), normalized, counts


def evaluate(
    *,
    audit_report_path: Path,
    fixture_path: Path,
    predictions_path: Path,
    isolated_root: Path,
    expected_case_count: int = 1800,
    diagnosis_catalog: set[str] | None = None,
    procedure_catalog: set[str] | None = None,
    catalog_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    audit_path = audit_report_path.resolve()
    fixture = fixture_path.resolve()
    predictions = predictions_path.resolve()
    isolated = isolated_root.resolve()
    if not _inside(predictions, isolated):
        errors.append("prediction packet escapes the explicitly isolated root")
    if not predictions.is_file():
        errors.append("prediction packet is missing")

    audit_report: dict[str, Any] = {}
    cases: list[dict[str, Any]] = []
    packet: Any = {}
    try:
        loaded_audit = _load_json(audit_path)
        if not isinstance(loaded_audit, dict):
            raise ValueError("dataset audit is not an object")
        audit_report = loaded_audit
        audit_errors = validate_dataset_audit(audit_report)
        if audit_errors or audit_report.get("status") != "ready_for_local_isolated_benchmark":
            errors.append("bound dataset audit is not valid and ready")
        loaded_fixture = _load_json(fixture)
        if not isinstance(loaded_fixture, list) or not all(
            isinstance(item, dict) for item in loaded_fixture
        ):
            raise ValueError("fixture is not a case list")
        cases = loaded_fixture
        if len(cases) != expected_case_count:
            errors.append("fixture case count is not exact")
        if predictions.is_file():
            packet = _load_json(predictions)
    except ValueError as exc:
        errors.append(str(exc))

    if diagnosis_catalog is None or procedure_catalog is None:
        try:
            diagnosis_catalog, procedure_catalog, loaded_status = _catalog_sets()
            catalog_status = loaded_status
        except Exception as exc:
            errors.append(f"trusted code catalog is unavailable: {type(exc).__name__}")
            diagnosis_catalog, procedure_catalog = set(), set()
    diagnosis_catalog = {_exact_code(value) for value in diagnosis_catalog}
    procedure_catalog = {_exact_code(value) for value in procedure_catalog}
    catalog_status = dict(catalog_status or {})
    if catalog_status.get("integrity_verified") is not True:
        errors.append("trusted code catalog integrity is not verified")

    fixture_sha = _sha256_file(fixture) if fixture.is_file() else ""
    audit_file_sha = _sha256_file(audit_path) if audit_path.is_file() else ""
    packet_sha = _sha256_file(predictions) if predictions.is_file() else ""
    audit_fixture = audit_report.get("bound_repository_fixture") or {}
    if audit_report and audit_fixture.get("sha256") != fixture_sha:
        errors.append("fixture does not match the bound dataset audit")
    if audit_report and audit_fixture.get("case_count") not in (None, len(cases)):
        errors.append("fixture case count does not match the bound dataset audit")
    expected_digests = [_case_digest(case) for case in cases]
    packet_errors, normalized, integrity = _packet_errors(
        packet=packet,
        expected_case_digests=expected_digests,
        audit_report=audit_report,
        audit_file_sha256=audit_file_sha,
        fixture_sha256=fixture_sha,
        diagnosis_catalog=diagnosis_catalog,
        procedure_catalog=procedure_catalog,
    )
    errors.extend(packet_errors)
    valid = not errors
    metadata = packet.get("run_metadata") if isinstance(packet, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "valid_local_training_set_measurement" if valid else "invalid",
        "quality_scope": QUALITY_SCOPE,
        "dataset_binding": {
            "source_workbook_sha256": _safe_sha256_or_empty(
                (audit_report.get("source_workbook") or {}).get("sha256") or ""
            ),
            "fixture_sha256": fixture_sha,
            "audit_report_sha256": audit_file_sha,
            "audit_report_canonical_sha256": _safe_sha256_or_empty(
                audit_report.get("report_sha256") or ""
            ),
            "case_count": len(cases),
        },
        "prediction_artifact": {
            "schema_version": (
                PACKET_SCHEMA
                if isinstance(packet, dict)
                and packet.get("schema_version") == PACKET_SCHEMA
                else ""
            ),
            "sha256": packet_sha,
            "size_bytes": predictions.stat().st_size if predictions.is_file() else 0,
            "retained_or_copied_by_evaluator": False,
        },
        "run_metadata": {
            "execution_environment": (
                "local_isolated"
                if metadata.get("execution_environment") == "local_isolated"
                else ""
            ),
            "provider_class": (
                metadata.get("provider_class", "")
                if metadata.get("provider_class") in ALLOWED_PROVIDER_CLASSES
                else ""
            ),
            "model_id": _safe_identifier_or_empty(metadata.get("model_id")),
            "model_revision": _safe_identifier_or_empty(
                metadata.get("model_revision")
            ),
            "oracle_test_only": metadata.get("oracle_test_only") is True,
        },
        "integrity": {
            **integrity,
            "dataset_audit_valid": (
                bool(audit_report)
                and not validate_dataset_audit(audit_report)
                and audit_report.get("status")
                == "ready_for_local_isolated_benchmark"
            ),
            "fixture_order_binding_valid": not any(
                "order does not match" in item for item in packet_errors
            ),
            "catalog_assignment_validity_rate": (
                1.0
                if not integrity["invalid_diagnosis_assignment_count"]
                and not integrity["invalid_procedure_assignment_count"]
                else 0.0
            ),
        },
        "metrics": _score(cases, normalized) if valid else {},
        "catalog_snapshot": {
            "schema_version": _safe_identifier_or_empty(
                catalog_status.get("schema_version")
            ),
            "catalog_release": _safe_identifier_or_empty(
                catalog_status.get("catalog_release")
            ),
            "integrity_verified": catalog_status.get("integrity_verified") is True,
            "diagnosis_count": int(catalog_status.get("diagnosis_count") or 0),
            "procedure_count": int(catalog_status.get("procedure_count") or 0),
        },
        "governance": {
            "aggregate_only_report": True,
            "raw_clinical_text_emitted": False,
            "encounter_identifiers_emitted": False,
            "case_level_labels_emitted": False,
            "case_level_predictions_emitted": False,
            "error_examples_emitted": False,
            "external_network_used_by_evaluator": False,
            "prediction_packet_confined_to_isolated_root": _inside(predictions, isolated),
            "prediction_generation_no_network_attested": (
                metadata.get("network_used") is False
                and metadata.get("external_provider_used") is False
            ),
            "prediction_generation_no_network_independently_verified": False,
            "prediction_packet_is_transient_sensitive_input": True,
        },
        "claim_boundaries": {
            "ccl2026_training_set_measurement": valid,
            "monoculture_evaluation": True,
            "independent_held_out_evaluation": False,
            "independent_clinical_gold_proven": False,
            "clinical_accuracy_proven": False,
            "corti_capability_parity_proven": False,
            "hospital_acceptance_proven": False,
            "production_readiness_proven": False,
            "model_capability_proven": False,
            "local_model_training_set_metrics_measured": (
                valid and metadata.get("provider_class") == "local_model"
            ),
            "local_deterministic_training_set_baseline_measured": (
                valid
                and metadata.get("provider_class")
                == "local_deterministic_baseline"
            ),
            "oracle_contract_self_test_only": metadata.get("oracle_test_only") is True,
        },
        "errors": sorted(set(errors)),
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_aggregate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != REPORT_SCHEMA:
        errors.append("unsupported aggregate report schema_version")
    supplied = str(report.get("report_sha256") or "")
    payload = copy.deepcopy(report)
    payload.pop("report_sha256", None)
    if supplied != _canonical_sha256(payload):
        errors.append("canonical aggregate report digest mismatch")
    forbidden = sorted(FORBIDDEN_REPORT_KEYS & set(_walk_keys(report)))
    if forbidden:
        errors.append("aggregate report contains prohibited case-level fields")
    governance = report.get("governance")
    governance = governance if isinstance(governance, dict) else {}
    for key in (
        "raw_clinical_text_emitted",
        "encounter_identifiers_emitted",
        "case_level_labels_emitted",
        "case_level_predictions_emitted",
        "error_examples_emitted",
        "external_network_used_by_evaluator",
        "prediction_generation_no_network_independently_verified",
    ):
        if governance.get(key) is not False:
            errors.append(f"aggregate governance boundary must remain false: {key}")
    if governance.get("aggregate_only_report") is not True:
        errors.append("evaluation report must remain aggregate-only")
    boundaries = report.get("claim_boundaries")
    boundaries = boundaries if isinstance(boundaries, dict) else {}
    for key in (
        "independent_held_out_evaluation",
        "independent_clinical_gold_proven",
        "clinical_accuracy_proven",
        "corti_capability_parity_proven",
        "hospital_acceptance_proven",
        "production_readiness_proven",
    ):
        if boundaries.get(key) is not False:
            errors.append(f"claim boundary must remain false: {key}")
    if report.get("status") == "valid_local_training_set_measurement":
        if report.get("errors"):
            errors.append("valid aggregate report contains errors")
        if not report.get("metrics"):
            errors.append("valid aggregate report has no metrics")
    elif report.get("metrics"):
        errors.append("invalid aggregate report must not expose trusted metrics")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--isolated-root", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=1800)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--assert-valid", action="store_true")
    parser.add_argument("--build-oracle-test-packet", action="store_true")
    parser.add_argument("--acknowledge-oracle-test-only", action="store_true")
    args = parser.parse_args()

    if not _inside(args.predictions, args.isolated_root):
        print("prediction packet escapes the explicitly isolated root", file=sys.stderr)
        return 2
    if args.build_oracle_test_packet:
        if not args.acknowledge_oracle_test_only:
            print("oracle test-only acknowledgement is required", file=sys.stderr)
            return 2
        audit = _load_json(args.audit_report.resolve())
        cases = _load_json(args.fixture.resolve())
        if not isinstance(audit, dict) or not isinstance(cases, list):
            print("oracle inputs are malformed", file=sys.stderr)
            return 2
        fixture_sha = _sha256_file(args.fixture.resolve())
        audit_fixture = audit.get("bound_repository_fixture") or {}
        if (
            validate_dataset_audit(audit)
            or audit.get("status") != "ready_for_local_isolated_benchmark"
            or audit_fixture.get("sha256") != fixture_sha
            or len(cases) != args.expected_case_count
        ):
            print("oracle inputs are not bound to a valid ready audit", file=sys.stderr)
            return 2
        packet = build_oracle_test_packet(
            cases=cases,
            audit_report=audit,
            audit_file_sha256=_sha256_file(args.audit_report.resolve()),
            fixture_sha256=fixture_sha,
        )
        args.predictions.parent.mkdir(parents=True, exist_ok=True)
        args.predictions.write_text(
            json.dumps(packet, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "oracle_test_packet_created",
            "case_count": len(cases),
            "sha256": _sha256_file(args.predictions.resolve()),
        }))
        return 0

    if args.output is None:
        print("--output is required when evaluating", file=sys.stderr)
        return 2
    report = evaluate(
        audit_report_path=args.audit_report,
        fixture_path=args.fixture,
        predictions_path=args.predictions,
        isolated_root=args.isolated_root,
        expected_case_count=args.expected_case_count,
    )
    validation_errors = validate_aggregate_report(report)
    if validation_errors:
        report["status"] = "invalid"
        report["errors"] = sorted(set(report["errors"] + validation_errors))
        report["metrics"] = {}
        report.pop("report_sha256", None)
        report["report_sha256"] = _canonical_sha256(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "case_count": report["dataset_binding"]["case_count"],
        "completed_case_count": report["integrity"]["completed_case_count"],
        "safe_failure_case_count": report["integrity"]["safe_failure_case_count"],
        "output": str(args.output.resolve()),
    }))
    return 1 if validation_errors or (
        args.assert_valid and report["status"] != "valid_local_training_set_measurement"
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
