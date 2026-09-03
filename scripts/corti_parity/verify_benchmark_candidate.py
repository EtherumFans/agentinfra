"""Verify a frozen Corti/iCoDer benchmark without running models or network calls.

The default mode checks artifact integrity and reports parity gaps. ``--strict``
also makes unresolved metric targets fail the command, which is useful for a
future release gate once the frozen baseline is expected to meet them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE = (
    REPO_ROOT / "reports" / "track_h" / "h4_benchmark_candidate_rc5"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _crlf_bytes(path: Path) -> bytes | None:
    """Return the historical Windows serialization for text artifacts.

    The frozen manifest predates the repository LF policy. Git legitimately
    normalizes these JSON files to LF, so integrity accepts either the checked
    out bytes or their deterministic CRLF transport representation.
    """
    try:
        raw = path.read_bytes()
        raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def _safe_artifact_path(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("artifact path must be non-empty and relative")
    resolved_root = root.resolve()
    resolved_path = (resolved_root / relative_path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("artifact path escapes the candidate directory") from exc
    return resolved_path


def _nested(mapping: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _metric(
    name: str,
    value: Any,
    target: str,
    passed: bool,
) -> Dict[str, Any]:
    return {"name": name, "value": value, "target": target, "passed": passed}


def _verify_file_entries(
    candidate: Path,
    entries: Iterable[Mapping[str, Any]],
    errors: List[str],
) -> List[Path]:
    verified: List[Path] = []
    for index, entry in enumerate(entries):
        relative_path = entry.get("path")
        if not isinstance(relative_path, str):
            errors.append(f"artifact[{index}] has no string path")
            continue
        try:
            path = _safe_artifact_path(candidate, relative_path)
        except ValueError as exc:
            errors.append(f"{relative_path!r}: {exc}")
            continue
        if not path.is_file():
            errors.append(f"{relative_path}: file is missing")
            continue
        expected_size = entry.get("size_bytes")
        expected_hash = entry.get("sha256")
        actual_hash = _sha256(path)
        crlf = _crlf_bytes(path)
        crlf_hash = hashlib.sha256(crlf).hexdigest() if crlf is not None else None
        normalized_match = (
            crlf is not None
            and expected_size == len(crlf)
            and expected_hash == crlf_hash
        )
        if expected_size != path.stat().st_size and not normalized_match:
            errors.append(
                f"{relative_path}: size mismatch "
                f"(manifest={expected_size}, actual={path.stat().st_size})"
            )
        if expected_hash != actual_hash and not normalized_match:
            errors.append(f"{relative_path}: sha256 mismatch")
        verified.append(path)
    return verified


def verify_candidate(candidate: Path) -> Dict[str, Any]:
    """Return integrity evidence and explicit unresolved parity gaps."""

    candidate = candidate.resolve()
    manifest_path = candidate / "MANIFEST.json"
    errors: List[str] = []
    if not manifest_path.is_file():
        return {
            "schema_version": "1.0",
            "candidate": str(candidate),
            "integrity": "failed",
            "errors": ["MANIFEST.json is missing"],
            "parity_status": "not_evaluated",
            "metrics": [],
            "gaps": [],
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "1.0",
            "candidate": str(candidate),
            "integrity": "failed",
            "errors": [f"MANIFEST.json cannot be parsed: {exc}"],
            "parity_status": "not_evaluated",
            "metrics": [],
            "gaps": [],
        }

    file_entries = manifest.get("files", [])
    per_case_entries = manifest.get("per_case_files", [])
    if not isinstance(file_entries, list) or not isinstance(per_case_entries, list):
        errors.append("manifest files and per_case_files must be arrays")
        file_entries = []
        per_case_entries = []

    verified_files = _verify_file_entries(candidate, file_entries, errors)
    per_case_files = _verify_file_entries(candidate, per_case_entries, errors)

    declared_case_count = manifest.get("case_count")
    if declared_case_count != len(per_case_entries):
        errors.append(
            "case_count mismatch "
            f"(manifest={declared_case_count}, entries={len(per_case_entries)})"
        )
    declared_file_count = manifest.get("file_count_total")
    actual_file_count = len(file_entries) + len(per_case_entries)
    if declared_file_count != actual_file_count:
        errors.append(
            "file_count_total mismatch "
            f"(manifest={declared_file_count}, entries={actual_file_count})"
        )

    case_ids = set()
    for path in per_case_files:
        relative_path = path.relative_to(candidate).as_posix()
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{relative_path}: cannot parse case JSON: {exc}")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{relative_path}: missing case_id")
        elif case_id in case_ids:
            errors.append(f"{relative_path}: duplicate case_id {case_id}")
        else:
            case_ids.add(case_id)
        if case.get("patient_ref") != "DEID" or case.get("encounter_ref") != "DEID":
            errors.append(f"{relative_path}: case is not explicitly de-identified")

    cross = _nested(manifest, ["cross_platform_normalizer", "section_9_9_cross_platform"])
    safety = _nested(manifest, ["cross_platform_normalizer", "section_9_10_icoder_safety"])
    quality = manifest.get("h4_1_quality_summary", {})
    h41_safety = manifest.get("h4_1_safety_summary", {})
    if not isinstance(cross, Mapping) or not isinstance(safety, Mapping):
        errors.append("cross-platform metric sections are missing")
        cross, safety = {}, {}

    agreement = cross.get("agreement_rate_delta_le_1")
    average_delta = cross.get("avg_abs_query_count_delta")
    range_rate = _nested(cross, ["icoder_range_conformance", "rate"])
    over_query = _nested(safety, ["over_query_complete_chart", "rate"])
    under_query = _nested(safety, ["under_query_clear_gap", "rate"])
    multi_dimension = safety.get("multi_dimension_query_rate")
    evidence_verbatim = quality.get("evidence_quote_verbatim_rate")
    response_options = quality.get("response_options_4plus_rate")
    non_leading = quality.get("non_leading_query_rate")
    unsupported = h41_safety.get("unsupported_query_rate")

    metrics = [
        _metric("agreement_rate_delta_le_1", agreement, ">= 0.80", isinstance(agreement, (int, float)) and agreement >= 0.80),
        _metric("avg_abs_query_count_delta", average_delta, "<= 0.50", isinstance(average_delta, (int, float)) and average_delta <= 0.50),
        _metric("icoder_range_conformance", range_rate, ">= 0.60", isinstance(range_rate, (int, float)) and range_rate >= 0.60),
        _metric("complete_chart_over_query_rate", over_query, "= 0", over_query == 0),
        _metric("clear_gap_under_query_rate", under_query, "= 0", under_query == 0),
        _metric("multi_dimension_query_rate", multi_dimension, "= 0", multi_dimension == 0),
        _metric("evidence_quote_verbatim_rate", evidence_verbatim, ">= 0.95", isinstance(evidence_verbatim, (int, float)) and evidence_verbatim >= 0.95),
        _metric("response_options_4plus_rate", response_options, ">= 0.95", isinstance(response_options, (int, float)) and response_options >= 0.95),
        _metric("non_leading_query_rate", non_leading, ">= 0.95", isinstance(non_leading, (int, float)) and non_leading >= 0.95),
        _metric("unsupported_query_rate", unsupported, "= 0", unsupported == 0),
    ]
    gaps = [
        {"metric": metric["name"], "value": metric["value"], "target": metric["target"]}
        for metric in metrics
        if not metric["passed"]
    ]

    return {
        "schema_version": "1.0",
        "candidate": str(candidate),
        "candidate_version": manifest.get("candidate_version"),
        "integrity": "passed" if not errors else "failed",
        "verified_artifact_files": len(verified_files),
        "verified_case_files": len(per_case_files),
        "unique_case_ids": len(case_ids),
        "errors": errors,
        "parity_status": "passed" if not gaps else "partial",
        "metrics": metrics,
        "gaps": gaps,
        "network_used": False,
        "models_loaded": False,
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", nargs="?", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return exit code 2 when any parity metric target is unresolved",
    )
    args = parser.parse_args(list(argv) if argv else None)
    result = verify_candidate(args.candidate)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["integrity"] != "passed":
        return 1
    if args.strict and result["parity_status"] != "passed":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
