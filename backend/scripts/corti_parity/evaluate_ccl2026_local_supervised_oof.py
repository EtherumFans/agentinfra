"""Evaluate a bounded, no-network supervised CCL baseline with OOF predictions.

The governed training fixture is split into deterministic stratified folds.
Every case is predicted by a model that cannot see that case or an identical
text digest during training.  Clinical text, case digests, labels, predictions,
neighbors, and error examples never enter the aggregate report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
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
from scripts.corti_parity.evaluate_ccl2026_local_predictions import (  # noqa: E402
    _score,
)


REPORT_SCHEMA = "icoder.ccl2026-local-supervised-oof/v1"
MODEL_ID = "bounded-char-ngram-neighbor-v1"
DEFAULT_SPLIT_SEED = "icoder-ccl2026-oof-v1"
TOKEN_RE = re.compile(r"[\u3400-\u9fffA-Z0-9]+")
DIGIT_RE = re.compile(r"\d+")
FORBIDDEN_REPORT_KEYS = {
    "case",
    "cases",
    "case_digest",
    "encounter_id",
    "text",
    "clinical_text",
    "prediction",
    "predictions",
    "per_case",
    "gold",
    "label",
    "labels",
    "neighbor",
    "neighbors",
    "error_example",
    "error_examples",
    "code",
    "codes",
}


class SupervisedOofError(ValueError):
    """The governed OOF contract cannot be satisfied."""


@dataclass(frozen=True)
class EvaluationInput:
    text_digest: str
    features: tuple[int, ...]


@dataclass(frozen=True)
class TrainingExample:
    text_digest: str
    features: tuple[int, ...]
    principal_diagnosis: str
    diagnoses: tuple[str, ...]
    principal_procedure: str
    procedures: tuple[str, ...]


def _normalized_segments(value: Any) -> list[str]:
    normalized = DIGIT_RE.sub("0", str(value or "").upper())
    return TOKEN_RE.findall(normalized)


def _feature_hash(size: int, gram: str) -> int:
    return zlib.crc32(gram.encode("utf-8"), size) & 0xFFFFFFFF


def document_features(value: Any, *, maximum_features: int = 2048) -> tuple[int, ...]:
    if maximum_features < 64:
        raise ValueError("maximum_features must be at least 64")
    features: set[int] = set()
    for segment in _normalized_segments(value):
        for size in (2, 3):
            if len(segment) < size:
                continue
            for index in range(len(segment) - size + 1):
                features.add(_feature_hash(size, segment[index:index + size]))
    if len(features) > maximum_features:
        features = set(sorted(features)[:maximum_features])
    return tuple(sorted(features))


def _text_digest(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _exact_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _code_tuple(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(sorted({_exact_code(value) for value in values if _exact_code(value)}))


def _fold_assignments(
    cases: list[dict[str, Any]], *, folds: int, seed: str
) -> list[int]:
    if folds < 2:
        raise SupervisedOofError("fold count must be at least two")
    grouped_by_text: dict[str, list[int]] = defaultdict(list)
    for index, case in enumerate(cases):
        grouped_by_text[_text_digest(case.get("text"))].append(index)
    by_label: dict[str, list[tuple[str, list[int]]]] = defaultdict(list)
    for digest, indexes in grouped_by_text.items():
        labels = {_exact_code(cases[index].get("expected_principal_diagnosis")) for index in indexes}
        if len(labels) != 1 or "" in labels:
            raise SupervisedOofError("identical text has inconsistent or missing principal labels")
        by_label[next(iter(labels))].append((digest, indexes))
    assignments = [-1] * len(cases)
    for label, groups in sorted(by_label.items()):
        if len(groups) < folds:
            raise SupervisedOofError("a principal label cannot populate every fold")
        ordered = sorted(
            groups,
            key=lambda item: hashlib.sha256(
                f"{seed}|{label}|{item[0]}".encode("ascii")
            ).hexdigest(),
        )
        for position, (_digest, indexes) in enumerate(ordered):
            fold = position % folds
            for index in indexes:
                assignments[index] = fold
    if any(value < 0 for value in assignments):
        raise SupervisedOofError("fold assignment is incomplete")
    return assignments


def _training_example(case: dict[str, Any], features: tuple[int, ...]) -> TrainingExample:
    principal_dx = _exact_code(case.get("expected_principal_diagnosis"))
    diagnoses = tuple(sorted(set(_code_tuple(case.get("expected_secondary_diagnoses"))) | {principal_dx}))
    principal_proc = _exact_code(case.get("expected_principal_procedure"))
    procedures = tuple(sorted(
        set(_code_tuple(case.get("expected_procedure_codes")))
        | ({principal_proc} if principal_proc else set())
    ))
    return TrainingExample(
        text_digest=_text_digest(case.get("text")),
        features=features,
        principal_diagnosis=principal_dx,
        diagnoses=diagnoses,
        principal_procedure=principal_proc,
        procedures=procedures,
    )


def _evaluation_input(case: dict[str, Any], features: tuple[int, ...]) -> EvaluationInput:
    return EvaluationInput(
        text_digest=_text_digest(case.get("text")),
        features=features,
    )


def _neighbor_index(
    training: list[TrainingExample], *, maximum_document_fraction: float = 0.22
) -> tuple[dict[int, tuple[int, ...]], dict[int, float], list[float]]:
    document_frequency: Counter[int] = Counter()
    for example in training:
        document_frequency.update(example.features)
    maximum_frequency = max(2, int(len(training) * maximum_document_fraction))
    idf = {
        feature: math.log((len(training) + 1) / (frequency + 0.5))
        for feature, frequency in document_frequency.items()
        if 2 <= frequency <= maximum_frequency
    }
    mutable_postings: dict[int, list[int]] = defaultdict(list)
    norms: list[float] = []
    for index, example in enumerate(training):
        norm = 0.0
        for feature in example.features:
            weight = idf.get(feature)
            if weight is None:
                continue
            mutable_postings[feature].append(index)
            norm += weight
        norms.append(norm)
    return (
        {feature: tuple(indexes) for feature, indexes in mutable_postings.items()},
        idf,
        norms,
    )


def _rank_neighbors(
    item: EvaluationInput,
    training: list[TrainingExample],
    postings: dict[int, tuple[int, ...]],
    idf: dict[int, float],
    norms: list[float],
    *,
    maximum_neighbors: int,
) -> list[tuple[TrainingExample, float]]:
    shared: dict[int, float] = defaultdict(float)
    query_norm = 0.0
    for feature in item.features:
        weight = idf.get(feature)
        if weight is None:
            continue
        query_norm += weight
        for index in postings.get(feature, ()):
            shared[index] += weight
    if query_norm <= 0:
        return []
    ranked = sorted(
        (
            (training[index], overlap / math.sqrt(query_norm * norms[index]))
            for index, overlap in shared.items()
            if norms[index] > 0 and training[index].text_digest != item.text_digest
        ),
        key=lambda pair: (-pair[1], pair[0].text_digest),
    )
    return ranked[:maximum_neighbors]


def _weighted_votes(
    neighbors: list[tuple[TrainingExample, float]], attribute: str
) -> tuple[Counter[str], Counter[str], float]:
    votes: Counter[str] = Counter()
    support: Counter[str] = Counter()
    total = 0.0
    for example, similarity in neighbors:
        weight = similarity * similarity
        total += weight
        for code in getattr(example, attribute):
            votes[code] += weight
            support[code] += 1
    return votes, support, total


def predict_fold(
    training: list[TrainingExample],
    evaluation: list[EvaluationInput],
    *,
    maximum_neighbors: int = 19,
) -> list[dict[str, Any]]:
    if not training:
        raise SupervisedOofError("training fold is empty")
    principal_prior = Counter(example.principal_diagnosis for example in training)
    fallback_principal = min(
        principal_prior,
        key=lambda code: (-principal_prior[code], code),
    )
    postings, idf, norms = _neighbor_index(training)
    results: list[dict[str, Any]] = []
    for item in evaluation:
        neighbors = _rank_neighbors(
            item,
            training,
            postings,
            idf,
            norms,
            maximum_neighbors=maximum_neighbors,
        )
        principal_votes: Counter[str] = Counter()
        for example, similarity in neighbors:
            principal_votes[example.principal_diagnosis] += similarity * similarity
        principal = min(
            principal_votes or {fallback_principal: 1.0},
            key=lambda code: (-(principal_votes or {fallback_principal: 1.0})[code], code),
        )
        diagnosis_votes, diagnosis_support, diagnosis_total = _weighted_votes(
            neighbors, "diagnoses"
        )
        selected_diagnoses = {
            code
            for code, vote in diagnosis_votes.items()
            if diagnosis_total > 0
            and vote / diagnosis_total >= 0.22
            and diagnosis_support[code] >= 2
        }
        selected_diagnoses.add(principal)
        ranked_diagnoses = sorted(
            selected_diagnoses,
            key=lambda code: (-diagnosis_votes[code], code),
        )[:12]

        procedure_votes, procedure_support, procedure_total = _weighted_votes(
            neighbors, "procedures"
        )
        procedure_case_weight = sum(
            similarity * similarity
            for example, similarity in neighbors
            if example.procedures
        )
        selected_procedures: list[str] = []
        if procedure_total > 0 and procedure_case_weight / procedure_total >= 0.38:
            selected_procedures = sorted(
                (
                    code
                    for code, vote in procedure_votes.items()
                    if vote / procedure_total >= 0.20 and procedure_support[code] >= 2
                ),
                key=lambda code: (-procedure_votes[code], code),
            )[:8]
        results.append({
            "status": "completed",
            "principal_diagnosis": principal,
            "secondary_diagnoses": [
                code for code in ranked_diagnoses if code != principal
            ],
            "principal_procedure": selected_procedures[0] if selected_procedures else None,
            "other_procedures": selected_procedures[1:],
            "failure_category": None,
        })
    return results


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


def validate_aggregate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != REPORT_SCHEMA:
        errors.append("unsupported report schema")
    if report.get("status") != "valid_local_supervised_oof_measurement":
        errors.append("report status is not valid")
    leaked = sorted({key for key in _walk_keys(report) if key.lower() in FORBIDDEN_REPORT_KEYS})
    if leaked:
        errors.append("aggregate report contains forbidden case-level keys")
    claims = report.get("claim_boundaries") or {}
    required_false = (
        "independent_clinical_gold_proven",
        "external_generalization_proven",
        "corti_capability_parity_proven",
        "clinical_production_readiness_proven",
        "external_network_used",
        "case_level_artifacts_emitted",
    )
    if any(claims.get(key) is not False for key in required_false):
        errors.append("claim boundary is not conservative")
    if claims.get("all_predictions_out_of_fold") is not True:
        errors.append("out-of-fold claim is missing")
    integrity = report.get("integrity") or {}
    if integrity.get("training_row_self_exposure_count") != 0:
        errors.append("training row self exposure is non-zero")
    return errors


def validate_persisted_report(report: dict[str, Any]) -> list[str]:
    errors = validate_aggregate_report(report)
    claimed = report.get("report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    if not isinstance(claimed, str) or claimed != _canonical_sha256(unsigned):
        errors.append("aggregate report digest is invalid")
    return errors


def evaluate(
    *,
    cases: list[dict[str, Any]],
    audit_report: dict[str, Any],
    audit_file_sha256: str,
    fixture_sha256: str,
    diagnosis_catalog: set[str],
    procedure_catalog: set[str],
    catalog_release: str,
    folds: int = 5,
    split_seed: str = DEFAULT_SPLIT_SEED,
) -> dict[str, Any]:
    if len(cases) < folds:
        raise SupervisedOofError("case count is smaller than fold count")
    features = [document_features(case.get("text")) for case in cases]
    assignments = _fold_assignments(cases, folds=folds, seed=split_seed)
    predictions: list[dict[str, Any] | None] = [None] * len(cases)
    fold_sizes: list[int] = []
    training_sizes: list[int] = []
    self_exposure_count = 0
    for fold in range(folds):
        training_indexes = [index for index, value in enumerate(assignments) if value != fold]
        evaluation_indexes = [index for index, value in enumerate(assignments) if value == fold]
        training = [_training_example(cases[index], features[index]) for index in training_indexes]
        evaluation = [_evaluation_input(cases[index], features[index]) for index in evaluation_indexes]
        training_digests = {example.text_digest for example in training}
        self_exposure_count += sum(item.text_digest in training_digests for item in evaluation)
        fold_predictions = predict_fold(training, evaluation)
        for index, prediction in zip(evaluation_indexes, fold_predictions, strict=True):
            predictions[index] = prediction
        fold_sizes.append(len(evaluation_indexes))
        training_sizes.append(len(training_indexes))
    if any(prediction is None for prediction in predictions):
        raise SupervisedOofError("OOF prediction coverage is incomplete")
    normalized_predictions = [prediction for prediction in predictions if prediction is not None]
    predicted_dx = {
        code
        for prediction in normalized_predictions
        for code in [prediction["principal_diagnosis"], *prediction["secondary_diagnoses"]]
        if code
    }
    predicted_proc = {
        code
        for prediction in normalized_predictions
        for code in [prediction["principal_procedure"], *prediction["other_procedures"]]
        if code
    }
    if not predicted_dx <= diagnosis_catalog or not predicted_proc <= procedure_catalog:
        raise SupervisedOofError("OOF predictions contain out-of-catalog codes")
    metrics = _score(cases, normalized_predictions)
    text_digest_counts = Counter(_text_digest(case.get("text")) for case in cases)
    split_binding = hashlib.sha256(
        "|".join(str(value) for value in assignments).encode("ascii")
    ).hexdigest()
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "valid_local_supervised_oof_measurement",
        "evaluation": {
            "mode": "deterministic_stratified_out_of_fold",
            "fold_count": folds,
            "evaluated_case_count": len(cases),
            "fold_sizes": fold_sizes,
            "training_sizes": training_sizes,
            "completed_case_count": metrics["completed_case_count"],
            "safe_failure_case_count": metrics["safe_failure_case_count"],
        },
        "model": {
            "model_id": MODEL_ID,
            "implementation": "bounded_hashed_character_ngram_neighbor",
            "maximum_features_per_document": 2048,
            "maximum_neighbors": 19,
            "native_ml_runtime_loaded": False,
            "network_used": False,
            "external_provider_used": False,
            "persistent_model_artifact_created": False,
        },
        "dataset_binding": {
            "source_workbook_sha256": str(
                (audit_report.get("source_workbook") or {}).get("sha256") or ""
            ),
            "fixture_sha256": fixture_sha256,
            "audit_report_sha256": audit_file_sha256,
            "audit_report_canonical_sha256": str(audit_report.get("report_sha256") or ""),
            "catalog_release": catalog_release,
            "case_count": len(cases),
            "split_assignment_sha256": split_binding,
        },
        "integrity": {
            "unique_text_digest_count": len(text_digest_counts),
            "duplicate_text_group_count": sum(count > 1 for count in text_digest_counts.values()),
            "training_row_self_exposure_count": self_exposure_count,
            "out_of_catalog_diagnosis_count": len(predicted_dx - diagnosis_catalog),
            "out_of_catalog_procedure_count": len(predicted_proc - procedure_catalog),
        },
        "metrics": metrics,
        "privacy": {
            "clinical_text_emitted": False,
            "encounter_identifiers_emitted": False,
            "case_digests_emitted": False,
            "case_level_labels_emitted": False,
            "case_level_predictions_emitted": False,
            "neighbors_emitted": False,
            "error_examples_emitted": False,
        },
        "claim_boundaries": {
            "local_supervised_development_baseline_measured": True,
            "all_predictions_out_of_fold": True,
            "identical_text_cross_fold_leakage_blocked": True,
            "case_level_artifacts_emitted": False,
            "external_network_used": False,
            "independent_clinical_gold_proven": False,
            "external_generalization_proven": False,
            "corti_capability_parity_proven": False,
            "clinical_production_readiness_proven": False,
        },
    }
    errors = validate_aggregate_report(report)
    if errors:
        raise SupervisedOofError("aggregate report failed validation")
    report["report_sha256"] = _canonical_sha256(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=1800)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--assert-valid", action="store_true")
    args = parser.parse_args()
    try:
        audit = json.loads(args.audit_report.resolve().read_text(encoding="utf-8"))
        cases = json.loads(args.fixture.resolve().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"cannot read governed input: {type(exc).__name__}", file=sys.stderr)
        return 2
    fixture_sha = _sha256_file(args.fixture.resolve())
    audit_fixture = audit.get("bound_repository_fixture") or {}
    if (
        not isinstance(audit, dict)
        or not isinstance(cases, list)
        or not all(isinstance(case, dict) for case in cases)
        or validate_dataset_audit(audit)
        or audit.get("status") != "ready_for_local_isolated_benchmark"
        or audit_fixture.get("sha256") != fixture_sha
        or len(cases) != args.expected_case_count
    ):
        print("inputs are not bound to a valid ready dataset audit", file=sys.stderr)
        return 2
    from data.code_dicts.icd_data import load_catalogs

    diagnoses, procedures, catalog_status = load_catalogs()
    if catalog_status.get("integrity_verified") is not True:
        print("trusted code catalog integrity is not verified", file=sys.stderr)
        return 2
    try:
        report = evaluate(
            cases=cases,
            audit_report=audit,
            audit_file_sha256=_sha256_file(args.audit_report.resolve()),
            fixture_sha256=fixture_sha,
            diagnosis_catalog={_exact_code(row[0]) for row in diagnoses},
            procedure_catalog={_exact_code(row[0]) for row in procedures},
            catalog_release=str(catalog_status.get("catalog_release") or "unknown"),
            folds=args.folds,
        )
    except SupervisedOofError as exc:
        print(f"supervised OOF evaluation failed: {exc}", file=sys.stderr)
        return 2
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    persisted = json.loads(args.output.resolve().read_text(encoding="utf-8"))
    print(json.dumps({
        "status": report["status"],
        "case_count": report["evaluation"]["evaluated_case_count"],
        "report_sha256": report["report_sha256"],
    }))
    if args.assert_valid and validate_persisted_report(persisted):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
