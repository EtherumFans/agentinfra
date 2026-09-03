"""Generate a no-network deterministic CCL 2026 catalog-match baseline.

This is deliberately not a clinical model.  It scans only the case ``text``
field for exact current-catalog names, ranks matches deterministically, and
writes a transient prediction packet below an explicitly isolated root.  Gold
label fields are never read for prediction; the complete case is hashed only to
bind output order to the governed fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.corti_parity.audit_ccl2026_local_dataset import (  # noqa: E402
    _canonical_sha256,
    _sha256_file,
    validate_report as validate_dataset_audit,
)
from scripts.corti_parity.evaluate_ccl2026_local_predictions import (  # noqa: E402
    PACKET_SCHEMA,
    QUALITY_SCOPE,
)


BASELINE_ID = "catalog-exact-name-frequency-recency-v1"
WHITESPACE_RE = re.compile(r"\s+")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _normalize_text(value: Any) -> str:
    return WHITESPACE_RE.sub("", str(value or "")).upper()


def _catalog_index(
    entries: list[tuple[str, str, str]], *, minimum_name_length: int = 3
) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """Index each unique name by its least-common three-character anchor."""

    name_codes: dict[str, set[str]] = defaultdict(set)
    for code, name, _group in entries:
        normalized_name = _normalize_text(name)
        normalized_code = str(code or "").strip().upper()
        if len(normalized_name) >= minimum_name_length and normalized_code:
            name_codes[normalized_name].add(normalized_code)
    grams_by_name = {
        name: {name[index:index + 3] for index in range(len(name) - 2)}
        for name in name_codes
    }
    frequencies = Counter(
        gram for grams in grams_by_name.values() for gram in grams
    )
    anchored: dict[str, list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for name, codes in name_codes.items():
        anchor = min(grams_by_name[name], key=lambda gram: (frequencies[gram], gram))
        anchored[anchor].append((name, tuple(sorted(codes))))
    return dict(anchored)


def _rank_matches(
    text: str,
    index: dict[str, list[tuple[str, tuple[str, ...]]]],
) -> list[str]:
    normalized = _normalize_text(text)
    if len(normalized) < 3:
        return []
    anchors = {normalized[position:position + 3] for position in range(len(normalized) - 2)}
    ranked: dict[str, tuple[int, int, int, str]] = {}
    for anchor in anchors:
        for name, codes in index.get(anchor, ()):  # exact verification follows
            first = normalized.find(name)
            if first < 0:
                continue
            count = normalized.count(name)
            last = normalized.rfind(name)
            for code in codes:
                score = (count, last, len(name), code)
                if code not in ranked or score > ranked[code]:
                    ranked[code] = score
    return [
        code
        for code, _score in sorted(
            ranked.items(),
            key=lambda item: (
                -item[1][0],
                -item[1][1],
                -item[1][2],
                item[0],
            ),
        )
    ]


def generate_predictions(
    *,
    cases: list[dict[str, Any]],
    diagnosis_entries: list[tuple[str, str, str]],
    procedure_entries: list[tuple[str, str, str]],
    max_diagnoses: int = 16,
    max_procedures: int = 12,
) -> list[dict[str, Any]]:
    diagnosis_index = _catalog_index(diagnosis_entries)
    procedure_index = _catalog_index(procedure_entries)
    predictions: list[dict[str, Any]] = []
    for case in cases:
        text = str(case.get("text") or "")
        diagnoses = _rank_matches(text, diagnosis_index)[:max_diagnoses]
        procedures = _rank_matches(text, procedure_index)[:max_procedures]
        if diagnoses:
            predictions.append({
                "case_digest": _canonical_sha256(case),
                "status": "completed",
                "principal_diagnosis": diagnoses[0],
                "secondary_diagnoses": diagnoses[1:],
                "principal_procedure": procedures[0] if procedures else None,
                "other_procedures": procedures[1:] if procedures else [],
                "failure_category": None,
            })
        else:
            predictions.append({
                "case_digest": _canonical_sha256(case),
                "status": "failed",
                "principal_diagnosis": "",
                "secondary_diagnoses": [],
                "principal_procedure": None,
                "other_procedures": [],
                "failure_category": "validation_error",
            })
    return predictions


def build_packet(
    *,
    cases: list[dict[str, Any]],
    audit_report: dict[str, Any],
    audit_file_sha256: str,
    fixture_sha256: str,
    diagnosis_entries: list[tuple[str, str, str]],
    procedure_entries: list[tuple[str, str, str]],
    catalog_release: str,
) -> dict[str, Any]:
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
            "provider_class": "local_deterministic_baseline",
            "model_id": BASELINE_ID,
            "model_revision": catalog_release,
            "network_used": False,
            "external_provider_used": False,
            "clinical_text_included": False,
            "raw_model_responses_persisted": False,
            "oracle_test_only": False,
        },
        "predictions": generate_predictions(
            cases=cases,
            diagnosis_entries=diagnosis_entries,
            procedure_entries=procedure_entries,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--isolated-root", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=1800)
    args = parser.parse_args()
    predictions = args.predictions.resolve()
    isolated = args.isolated_root.resolve()
    if not _inside(predictions, isolated):
        print("prediction packet escapes the explicitly isolated root", file=sys.stderr)
        return 2
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
    packet = build_packet(
        cases=cases,
        audit_report=audit,
        audit_file_sha256=_sha256_file(args.audit_report.resolve()),
        fixture_sha256=fixture_sha,
        diagnosis_entries=diagnoses,
        procedure_entries=procedures,
        catalog_release=str(catalog_status.get("catalog_release") or "unknown"),
    )
    predictions.parent.mkdir(parents=True, exist_ok=True)
    predictions.write_text(
        json.dumps(packet, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    completed = sum(row["status"] == "completed" for row in packet["predictions"])
    print(json.dumps({
        "status": "local_deterministic_baseline_packet_created",
        "case_count": len(cases),
        "completed_case_count": completed,
        "safe_failure_case_count": len(cases) - completed,
        "sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
