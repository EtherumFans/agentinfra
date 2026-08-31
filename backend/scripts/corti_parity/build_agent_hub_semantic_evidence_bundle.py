"""Validate and bundle fresh Agent Hub semantic release evidence.

This gate is intentionally strict.  Contract-only, safe-fail, mock, resumed,
unbound-seed, partial, stale, or Pack-mismatched reports cannot increase the
runtime matrix's live-semantic count.  A stability first-round seed is accepted
only when it is byte-bound to the same bundle's fresh happy/adversarial run.
The output contains hashes and bounded metadata, never prompts, response
bodies, credentials, or clinical text.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.corti_parity.agent_hub_live_evidence import (  # noqa: E402
    canonical_sha256,
    extract_trace_evidence,
    result_attestation_evidence,
    sha256_file,
    utc_now_iso,
)


DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_REFERENCE_CASES = Path(__file__).with_name(
    "agent_hub_reference_quality_cases.json"
)
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "agent_hub" / "semantic_evidence"
EXPECTED_AGENT_COUNT = 26
SUPPORTED_SCHEMAS = {
    "examples": "icoder.agent-hub-examples-e2e/v3",
    "adversarial": "icoder.agent-hub-adversarial-e2e/v3",
    "reference": "icoder.agent-hub-reference-quality-replay/v1",
    "stability": "icoder.agent-hub-stability-benchmark/v2",
}
REFERENCE_SCOPE = "pack_owned_synthetic_reference_semantics_not_independent_clinical_gold"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read JSON report {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"report must be a JSON object: {path}")
    return value


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _artifact_path(value: Any, report_path: Path) -> Path:
    path = Path(str(value or ""))
    if path.is_absolute() and path.exists():
        return path.resolve()
    if not path.is_absolute():
        candidate = report_path.parent / path
        if candidate.exists():
            return candidate.resolve()
    # Uploaded evidence may be extracted under a different root.  Runner
    # artifacts always live in a bounded responses/ or traces/ child next to
    # their report, so relocate by the final two path components only.
    if path.name and path.parent.name in {"responses", "traces"}:
        relocated = report_path.parent / path.parent.name / path.name
        if relocated.exists():
            return relocated.resolve()
    return path.resolve() if path.is_absolute() else (report_path.parent / path).resolve()


def _raw_visible_packs(agents_dir: Path) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    for path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = _read_json(path)
        manifest = pack.get("manifest") or {}
        if manifest.get("hidden_from_hub") is not True:
            packs.append(pack)
    return packs


def _snapshot_from_agents_dir(agents_dir: Path) -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for pack in _raw_visible_packs(agents_dir):
        agent_id = str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]
        snapshot[agent_id] = {
            "agent_ref": str(pack.get("agent_ref") or ""),
            "pack_sha256": str((pack.get("integrity") or {}).get("sha256") or ""),
            "output_schema_ref": str((pack.get("output_contract") or {}).get("schema_ref") or ""),
            "backend_provider": str(pack.get("backend_provider") or ""),
        }
    return {key: snapshot[key] for key in sorted(snapshot)}


def _freshness_errors(
    report: dict[str, Any],
    *,
    label: str,
    now: datetime,
    max_age: timedelta,
) -> list[str]:
    generated = _parse_utc(report.get("generated_at"))
    if generated is None:
        return [f"{label}: generated_at is missing or invalid"]
    if generated > now + timedelta(minutes=5):
        return [f"{label}: generated_at is in the future"]
    if now - generated > max_age:
        return [f"{label}: report is stale"]
    return []


def _validate_snapshot(
    report: dict[str, Any],
    *,
    label: str,
    current_snapshot: dict[str, dict[str, str]],
) -> list[str]:
    if report.get("agent_snapshot") != current_snapshot:
        return [f"{label}: Agent Pack snapshot does not match current visible Packs"]
    return []


def _validate_execution_row(
    row: dict[str, Any],
    *,
    report_path: Path,
    current_snapshot: dict[str, dict[str, str]],
    external_agents: set[str],
    now: datetime,
    trusted_seed_sha256: str = "",
) -> list[str]:
    agent_id = str(row.get("agent_id") or "")
    prefix = f"{report_path.name}:{agent_id or '<missing>'}"
    errors: list[str] = []
    current = current_snapshot.get(agent_id)
    evidence = row.get("execution_evidence")
    if current is None:
        return [f"{prefix}: Agent is not in the current visible set"]
    if not isinstance(evidence, dict):
        return [f"{prefix}: execution_evidence is missing"]
    artifact_source = str(evidence.get("artifact_source") or "")
    trusted_seed = bool(
        artifact_source == "seed"
        and trusted_seed_sha256
        and evidence.get("response_sha256") == trusted_seed_sha256
    )
    if artifact_source != "run" and not trusted_seed:
        errors.append(f"{prefix}: artifact_source must be a fresh HTTP run or bound fresh seed")
    if evidence.get("pack_sha256") != current["pack_sha256"]:
        errors.append(f"{prefix}: Pack digest mismatch")
    if evidence.get("output_schema_ref") != current["output_schema_ref"]:
        errors.append(f"{prefix}: output contract mismatch")
    completed = _parse_utc(evidence.get("completed_at"))
    if completed is None or completed > now + timedelta(minutes=5):
        errors.append(f"{prefix}: completion timestamp is invalid")

    response_path = _artifact_path(row.get("response_path"), report_path)
    if not response_path.is_file():
        errors.append(f"{prefix}: response artifact is missing")
        return errors
    if evidence.get("response_sha256") != sha256_file(response_path):
        errors.append(f"{prefix}: response artifact digest mismatch")
        return errors
    try:
        response = _read_json(response_path)
    except ValueError:
        errors.append(f"{prefix}: response artifact is invalid JSON")
        return errors
    if response.get("error") is not False:
        errors.append(f"{prefix}: response is not a successful capability result")
    run_id = str(response.get("run_id") or "")
    if not run_id.startswith("run-"):
        errors.append(f"{prefix}: run_id is missing")
    if not str(response.get("trace_id") or "").startswith("trace-"):
        errors.append(f"{prefix}: trace_id is missing")

    attestation = result_attestation_evidence(
        response,
        agent_id=agent_id,
        output_schema_ref=current["output_schema_ref"],
    )
    recorded_attestation = evidence.get("result_attestation")
    if recorded_attestation != attestation:
        errors.append(f"{prefix}: result attestation evidence mismatch")
    if (
        not attestation["present"]
        or not attestation["claims_bound"]
        or not attestation["signature_verified"]
    ):
        errors.append(
            f"{prefix}: server result attestation is absent, unbound, or has an invalid signature"
        )
    if int(attestation.get("expires_at_epoch") or 0) <= int(now.timestamp()):
        errors.append(f"{prefix}: server result attestation is expired")

    if trusted_seed:
        return errors

    recorded_trace = evidence.get("trace")
    if not isinstance(recorded_trace, dict):
        errors.append(f"{prefix}: trace evidence is missing")
        return errors
    trace_path = _artifact_path(recorded_trace.get("artifact_path"), report_path)
    if not trace_path.is_file():
        errors.append(f"{prefix}: trace artifact is missing")
        return errors
    if recorded_trace.get("artifact_sha256") != sha256_file(trace_path):
        errors.append(f"{prefix}: trace artifact digest mismatch")
        return errors
    try:
        trace = _read_json(trace_path)
    except ValueError:
        errors.append(f"{prefix}: trace artifact is invalid JSON")
        return errors
    actual_trace = extract_trace_evidence(trace, run_id=run_id)
    comparable = {
        key: value
        for key, value in recorded_trace.items()
        if key not in {"artifact_path", "artifact_sha256"}
    }
    if comparable != actual_trace:
        errors.append(f"{prefix}: extracted trace evidence mismatch")
    if actual_trace["http_status"] != 200 or not actual_trace["run_id_matches"]:
        errors.append(f"{prefix}: tenant-scoped RunTrace was not captured successfully")
    if (
        not actual_trace["trace_attestation_present"]
        or not actual_trace["trace_attestation_claims_bound"]
        or not actual_trace["trace_attestation_signature_verified"]
    ):
        errors.append(
            f"{prefix}: RunTrace attestation is absent, unbound, or has an invalid signature"
        )
    if int(actual_trace.get("trace_attestation_expires_at_epoch") or 0) <= int(
        now.timestamp()
    ):
        errors.append(f"{prefix}: RunTrace attestation is expired")
    if not actual_trace["event_count"] or not actual_trace["backend_providers"]:
        errors.append(f"{prefix}: Provider completion telemetry is absent")
    if actual_trace["mock_detected"]:
        errors.append(f"{prefix}: mock/test model telemetry is forbidden")
    if actual_trace["degraded_detected"]:
        errors.append(f"{prefix}: degraded/fallback Provider execution is forbidden")
    if agent_id in external_agents and not actual_trace["model_call_observed"]:
        errors.append(f"{prefix}: real model provider/name telemetry is absent")
    return errors


def _validate_live_report(
    *,
    label: str,
    report_path: Path,
    report: dict[str, Any],
    current_snapshot: dict[str, dict[str, str]],
    external_agents: set[str],
    now: datetime,
    max_age: timedelta,
    expected_count: int = EXPECTED_AGENT_COUNT,
    trusted_seed_hashes: dict[tuple[str, str], str] | None = None,
    trusted_seed_reports: dict[str, dict[str, str]] | None = None,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    if report.get("schema_version") != SUPPORTED_SCHEMAS[label]:
        errors.append(f"{label}: unsupported schema_version")
    errors.extend(_freshness_errors(report, label=label, now=now, max_age=max_age))
    errors.extend(
        _validate_snapshot(report, label=label, current_snapshot=current_snapshot)
    )
    rows = report.get("rows")
    rows = rows if isinstance(rows, list) else []
    provenance = report.get("execution_provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    if label != "stability":
        if not provenance.get("all_rows_fresh_http"):
            errors.append(f"{label}: report contains resumed, seeded, or unknown artifacts")
        if provenance.get("fresh_http_runs") != len(rows):
            errors.append(f"{label}: fresh HTTP run count does not match rows")
    elif provenance.get("resumed_artifacts") or provenance.get("unknown_artifacts"):
        errors.append("stability: resumed or unknown artifacts are forbidden")

    expected_ids = set(current_snapshot)
    per_agent: dict[str, dict[str, Any]] = {}
    if label in {"examples", "adversarial"}:
        ids = [str(row.get("agent_id") or "") for row in rows]
        if len(rows) != expected_count or set(ids) != expected_ids or len(ids) != len(set(ids)):
            errors.append(f"{label}: rows must contain each visible Agent exactly once")
        if label == "examples":
            counts_ok = bool(
                report.get("total") == expected_count
                and report.get("passed") == expected_count
                and report.get("capability_passed") == expected_count
                and report.get("safe_fail_closed") == 0
                and report.get("failed") == 0
            )
        else:
            counts_ok = bool(
                report.get("expected") == expected_count
                and report.get("completed") == expected_count
                and report.get("passed") == expected_count
                and report.get("semantic_capability_passed") == expected_count
                and report.get("safe_fail_closed") == 0
                and report.get("failed") == 0
                and report.get("complete") is True
            )
        if not counts_ok:
            errors.append(f"{label}: capability counts are incomplete or include safe-fail results")
        for row in rows:
            agent_id = str(row.get("agent_id") or "")
            row_errors = _validate_execution_row(
                row,
                report_path=report_path,
                current_snapshot=current_snapshot,
                external_agents=external_agents,
                now=now,
            )
            if not isinstance(row.get("evaluation"), dict) or row["evaluation"].get("passed") is not True:
                row_errors.append(f"{label}:{agent_id}: semantic evaluation did not pass")
            errors.extend(row_errors)
            per_agent[agent_id] = {
                "passed": not row_errors,
                "response_sha256": str(
                    (row.get("execution_evidence") or {}).get("response_sha256") or ""
                ),
            }
    else:
        repetitions = report.get("repetitions")
        expected_rows = expected_count * 2 * int(repetitions or 0)
        ids = {str(row.get("agent_id") or "") for row in rows}
        gates = report.get("gates")
        gates = gates if isinstance(gates, dict) else {}
        if not isinstance(repetitions, int) or repetitions < 2:
            errors.append("stability: repetitions must be at least 2")
        seed_count = int(provenance.get("seeded_artifacts") or 0)
        fresh_count = int(provenance.get("fresh_http_runs") or 0)
        if seed_count not in {0, expected_count * 2}:
            errors.append("stability: seeds must be absent or cover exactly one round of both scenarios")
        if fresh_count + seed_count != len(rows):
            errors.append("stability: fresh/seed execution counts do not match rows")
        if seed_count:
            supplied_seed_sources = report.get("seed_sources")
            supplied_seed_sources = (
                supplied_seed_sources if isinstance(supplied_seed_sources, dict) else {}
            )
            if supplied_seed_sources != (trusted_seed_reports or {}):
                errors.append("stability: seed source report digests are absent or mismatched")
        if (
            expected_rows <= 0
            or report.get("expected") != expected_rows
            or report.get("completed") != expected_rows
            or len(rows) != expected_rows
            or report.get("passed") != expected_rows
            or report.get("failed") != 0
            or report.get("complete") is not True
            or not gates
            or not all(value is True for value in gates.values())
            or ids != expected_ids
        ):
            errors.append("stability: completeness, pass, Agent-set, or reliability gates failed")
        grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in expected_ids}
        for row in rows:
            agent_id = str(row.get("agent_id") or "")
            case_kind = str(row.get("case_kind") or "")
            grouped.setdefault(agent_id, []).append(row)
            errors.extend(
                _validate_execution_row(
                    row,
                    report_path=report_path,
                    current_snapshot=current_snapshot,
                    external_agents=external_agents,
                    now=now,
                    trusted_seed_sha256=str(
                        (trusted_seed_hashes or {}).get((agent_id, case_kind), "")
                    ),
                )
            )
            if not isinstance(row.get("evaluation"), dict) or row["evaluation"].get("passed") is not True:
                errors.append(
                    f"stability:{row.get('agent_id')}: repeated semantic evaluation did not pass"
                )
        repeated = {
            str(item.get("agent_id") or ""): item
            for item in (report.get("per_agent") or [])
            if isinstance(item, dict)
        }
        for agent_id in expected_ids:
            agent_rows = grouped.get(agent_id) or []
            case_kinds = [str(row.get("case_kind") or "") for row in agent_rows]
            valid = bool(
                len(agent_rows) == 2 * int(repetitions or 0)
                and case_kinds.count("happy") == int(repetitions or 0)
                and case_kinds.count("adversarial") == int(repetitions or 0)
                and (repeated.get(agent_id) or {}).get("all_scenarios_repeatably_passed") is True
            )
            if seed_count:
                seeded = [
                    row
                    for row in agent_rows
                    if (row.get("execution_evidence") or {}).get("artifact_source") == "seed"
                ]
                valid = bool(
                    valid
                    and len(seeded) == 2
                    and {str(row.get("case_kind") or "") for row in seeded}
                    == {"happy", "adversarial"}
                    and all(int(row.get("repetition") or 0) == 1 for row in seeded)
                )
            if not valid:
                errors.append(f"stability:{agent_id}: scenarios are not repeatably complete")
            per_agent[agent_id] = {"passed": valid}
    return errors, per_agent


def _validate_reference(
    *,
    report_path: Path,
    report: dict[str, Any],
    examples_path: Path,
    example_rows: dict[str, dict[str, Any]],
    current_snapshot: dict[str, dict[str, str]],
    now: datetime,
    max_age: timedelta,
    reference_cases_path: Path,
    expected_count: int = EXPECTED_AGENT_COUNT,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    if report.get("schema_version") != SUPPORTED_SCHEMAS["reference"]:
        errors.append("reference: unsupported schema_version")
    errors.extend(_freshness_errors(report, label="reference", now=now, max_age=max_age))
    if report.get("quality_scope") != REFERENCE_SCOPE:
        errors.append("reference: quality scope is unsupported")
    if report.get("network_used") is not False or report.get("credential_used") is not False:
        errors.append("reference: offline replay provenance is invalid")
    if (
        report.get("expected") != expected_count
        or report.get("completed") != expected_count
        or report.get("passed") != expected_count
        or report.get("failed") != 0
        or report.get("safe_fail_closed") != 0
        or report.get("all_passed") is not True
    ):
        errors.append(
            f"reference: all {expected_count} scoped Pack-owned semantic cases must pass"
        )
    if not reference_cases_path.is_file() or report.get("cases_sha256") != sha256_file(reference_cases_path):
        errors.append("reference: cases digest does not match current reference cases")
    source = report.get("source_report")
    source = source if isinstance(source, dict) else {}
    if source.get("sha256") != sha256_file(examples_path):
        errors.append("reference: source report digest does not match examples report")
    rows = report.get("rows")
    rows = rows if isinstance(rows, list) else []
    ids = [str(row.get("agent_id") or "") for row in rows]
    if len(rows) != expected_count or set(ids) != set(current_snapshot) or len(ids) != len(set(ids)):
        errors.append("reference: rows must contain each visible Agent exactly once")
    per_agent: dict[str, dict[str, Any]] = {}
    for row in rows:
        agent_id = str(row.get("agent_id") or "")
        expected_hash = str((example_rows.get(agent_id) or {}).get("response_sha256") or "")
        passed = bool(
            row.get("passed") is True
            and row.get("base_contract_safety_passed") is True
            and row.get("reference_assertions_passed") is True
            and row.get("safe_fail_closed") is False
            and row.get("response_sha256") == expected_hash
        )
        if not passed:
            errors.append(f"reference:{agent_id}: response binding or semantic assertions failed")
        per_agent[agent_id] = {"passed": passed}
    return errors, per_agent


def build_bundle(
    *,
    examples_path: Path,
    adversarial_path: Path,
    reference_path: Path,
    stability_path: Path,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    reference_cases_path: Path = DEFAULT_REFERENCE_CASES,
    max_age_hours: float = 24.0,
    now: datetime | None = None,
    matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    if matrix is None:
        from scripts.corti_parity.build_agent_hub_runtime_matrix import build_matrix

        matrix = build_matrix(agents_dir.resolve())
    current_snapshot = _snapshot_from_agents_dir(agents_dir.resolve())
    external_agents = {
        str(row["agent_id"])
        for row in matrix.get("rows", [])
        if row.get("hub_visible") is True and row.get("external_llm_dependent") is True
    }
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    max_age = timedelta(hours=max_age_hours)
    source_paths = {
        "examples": examples_path.resolve(),
        "adversarial": adversarial_path.resolve(),
        "reference": reference_path.resolve(),
        "stability": stability_path.resolve(),
    }
    common_source_root = Path(
        os.path.commonpath([str(path.parent) for path in source_paths.values()])
    )
    reports: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for label, path in source_paths.items():
        try:
            reports[label] = _read_json(path)
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            reports[label] = {}

    per_source: dict[str, dict[str, dict[str, Any]]] = {}
    for label in ("examples", "adversarial"):
        source_errors, agent_results = _validate_live_report(
            label=label,
            report_path=source_paths[label],
            report=reports[label],
            current_snapshot=current_snapshot,
            external_agents=external_agents,
            now=now,
            max_age=max_age,
        )
        errors.extend(source_errors)
        per_source[label] = agent_results
    trusted_seed_hashes = {
        **{
            (agent_id, "happy"): str(value.get("response_sha256") or "")
            for agent_id, value in per_source.get("examples", {}).items()
        },
        **{
            (agent_id, "adversarial"): str(value.get("response_sha256") or "")
            for agent_id, value in per_source.get("adversarial", {}).items()
        },
    }
    trusted_seed_reports = {
        "happy": {
            "report_path": str(source_paths["examples"]),
            "report_sha256": sha256_file(source_paths["examples"])
            if source_paths["examples"].is_file()
            else "",
        },
        "adversarial": {
            "report_path": str(source_paths["adversarial"]),
            "report_sha256": sha256_file(source_paths["adversarial"])
            if source_paths["adversarial"].is_file()
            else "",
        },
    }
    stability_errors, stability_results = _validate_live_report(
        label="stability",
        report_path=source_paths["stability"],
        report=reports["stability"],
        current_snapshot=current_snapshot,
        external_agents=external_agents,
        now=now,
        max_age=max_age,
        trusted_seed_hashes=trusted_seed_hashes,
        trusted_seed_reports=trusted_seed_reports,
    )
    errors.extend(stability_errors)
    per_source["stability"] = stability_results
    example_rows = {
        agent_id: value
        for agent_id, value in per_source.get("examples", {}).items()
    }
    reference_errors, reference_results = _validate_reference(
        report_path=source_paths["reference"],
        report=reports["reference"],
        examples_path=source_paths["examples"],
        example_rows=example_rows,
        current_snapshot=current_snapshot,
        now=now,
        max_age=max_age,
        reference_cases_path=reference_cases_path.resolve(),
    )
    errors.extend(reference_errors)
    per_source["reference"] = reference_results
    errors = sorted(set(errors))
    agent_results: list[dict[str, Any]] = []
    for agent_id in current_snapshot:
        gates = {
            label: bool((per_source.get(label, {}).get(agent_id) or {}).get("passed"))
            for label in ("examples", "adversarial", "reference", "stability")
        }
        agent_results.append({
            "agent_id": agent_id,
            "gates": gates,
            "semantic_live_e2e_verified": not errors and all(gates.values()),
        })
    bundle: dict[str, Any] = {
        "schema_version": "icoder.agent-hub-semantic-evidence-bundle/v1",
        "generated_at": utc_now_iso() if now is None else now.isoformat(),
        "quality_scope": "synthetic_live_semantic_release_evidence_not_clinical_accuracy_or_corti_parity",
        "max_age_hours": max_age_hours,
        "valid": not errors and len(current_snapshot) == EXPECTED_AGENT_COUNT,
        "errors": errors,
        "summary": {
            "visible_agents": len(current_snapshot),
            "semantic_live_e2e_verified": sum(
                item["semantic_live_e2e_verified"] for item in agent_results
            ),
            "semantic_live_e2e_pending": [
                item["agent_id"]
                for item in agent_results
                if not item["semantic_live_e2e_verified"]
            ],
        },
        "sources": {
            label: {
                "path": str(path),
                "relative_path": str(path.relative_to(common_source_root)),
                "sha256": sha256_file(path) if path.is_file() else "",
                "schema_version": reports[label].get("schema_version"),
                "generated_at": reports[label].get("generated_at"),
            }
            for label, path in source_paths.items()
        },
        "agent_snapshot": current_snapshot,
        "agent_results": agent_results,
        "limitations": [
            "This proves fresh synthetic live semantic, adversarial, and stability gates; it is not an independent clinical-accuracy study.",
            "It does not prove Corti parity, hospital integration, regulatory approval, production SLOs, or clinician acceptance.",
            "Result tokens are HMAC-verified with the same ephemeral/server trust key; CI must keep that key process-scoped and out of artifacts.",
        ],
    }
    digest_payload = copy.deepcopy(bundle)
    bundle["bundle_sha256"] = canonical_sha256(digest_payload)
    return bundle


def verify_bundle_digest(bundle: dict[str, Any]) -> bool:
    declared = str(bundle.get("bundle_sha256") or "")
    payload = copy.deepcopy(bundle)
    payload.pop("bundle_sha256", None)
    return bool(declared) and declared == canonical_sha256(payload)


def validate_bundle_file(
    bundle_path: Path,
    *,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    max_age_hours: float = 24.0,
    now: datetime | None = None,
    matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild a bundle from its source artifacts before trusting its rows."""

    errors: list[str] = []
    try:
        supplied = _read_json(bundle_path.resolve())
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)], "verified_agent_ids": []}
    if supplied.get("schema_version") != "icoder.agent-hub-semantic-evidence-bundle/v1":
        errors.append("bundle: unsupported schema_version")
    if not verify_bundle_digest(supplied):
        errors.append("bundle: canonical digest mismatch")
    if supplied.get("valid") is not True:
        errors.append("bundle: source validation did not pass")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated = _parse_utc(supplied.get("generated_at"))
    if generated is None or generated > now + timedelta(minutes=5):
        errors.append("bundle: generated_at is invalid")
    elif now - generated > timedelta(hours=max_age_hours):
        errors.append("bundle: evidence bundle is stale")
    sources = supplied.get("sources")
    sources = sources if isinstance(sources, dict) else {}
    if set(sources) != set(SUPPORTED_SCHEMAS):
        errors.append("bundle: all four source reports are required")
    if errors:
        return {
            "valid": False,
            "errors": sorted(set(errors)),
            "verified_agent_ids": [],
            "bundle_sha256": str(supplied.get("bundle_sha256") or ""),
        }
    source_paths: dict[str, Path] = {}
    for label in SUPPORTED_SCHEMAS:
        source = sources.get(label) or {}
        original = Path(str(source.get("path") or ""))
        if original.is_file():
            source_paths[label] = original.resolve()
            continue
        relative = Path(str(source.get("relative_path") or ""))
        safe_relative = bool(
            str(relative)
            and not relative.is_absolute()
            and ".." not in relative.parts
        )
        relocated_candidates = (
            (
                bundle_path.resolve().parent / relative,
                bundle_path.resolve().parent.parent / relative,
            )
            if safe_relative
            else ()
        )
        relocated = next(
            (candidate for candidate in relocated_candidates if candidate.is_file()),
            original,
        )
        source_paths[label] = relocated.resolve()
    rebuilt = build_bundle(
        examples_path=source_paths["examples"],
        adversarial_path=source_paths["adversarial"],
        reference_path=source_paths["reference"],
        stability_path=source_paths["stability"],
        agents_dir=agents_dir.resolve(),
        max_age_hours=max_age_hours,
        now=now,
        matrix=matrix,
    )
    if not rebuilt.get("valid"):
        errors.extend(str(item) for item in rebuilt.get("errors") or [])
    if supplied.get("agent_snapshot") != rebuilt.get("agent_snapshot"):
        errors.append("bundle: current Agent snapshot mismatch")
    if supplied.get("agent_results") != rebuilt.get("agent_results"):
        errors.append("bundle: Agent verification rows do not match source artifacts")
    supplied_hashes = {
        label: str((sources.get(label) or {}).get("sha256") or "")
        for label in SUPPORTED_SCHEMAS
    }
    rebuilt_hashes = {
        label: str((rebuilt.get("sources", {}).get(label) or {}).get("sha256") or "")
        for label in SUPPORTED_SCHEMAS
    }
    if supplied_hashes != rebuilt_hashes:
        errors.append("bundle: source artifact digest mismatch")
    verified = [
        str(item["agent_id"])
        for item in rebuilt.get("agent_results", [])
        if item.get("semantic_live_e2e_verified") is True
    ]
    if len(verified) != EXPECTED_AGENT_COUNT:
        errors.append("bundle: all 26 visible Agents must be verified")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "verified_agent_ids": sorted(verified) if not errors else [],
        "bundle_sha256": str(supplied.get("bundle_sha256") or ""),
        "source_hashes": rebuilt_hashes,
    }


def write_bundle(out_dir: Path, bundle: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "agent_hub_semantic_evidence_bundle.json"
    md_path = out_dir / "agent_hub_semantic_evidence_bundle.md"
    json_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = bundle["summary"]
    lines = [
        "# Agent Hub semantic evidence bundle",
        "",
        f"Generated: `{bundle['generated_at']}`",
        "",
        f"Validation: **{'PASS' if bundle['valid'] else 'FAIL'}**",
        "",
        f"Fresh synthetic live semantic evidence: **{summary['semantic_live_e2e_verified']}/{summary['visible_agents']}**",
        "",
        "## Source artifacts",
        "",
    ]
    for label, source in bundle["sources"].items():
        lines.append(f"- {label}: `{source['sha256']}` ({source['schema_version']})")
    if bundle["errors"]:
        lines.extend(["", "## Validation errors", ""])
        lines.extend(f"- {error}" for error in bundle["errors"])
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in bundle["limitations"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--adversarial", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--stability", type=Path, required=True)
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--reference-cases", type=Path, default=DEFAULT_REFERENCE_CASES)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    bundle = build_bundle(
        examples_path=args.examples,
        adversarial_path=args.adversarial,
        reference_path=args.reference,
        stability_path=args.stability,
        agents_dir=args.agents_dir,
        reference_cases_path=args.reference_cases,
        max_age_hours=args.max_age_hours,
    )
    paths = write_bundle(args.out_dir, bundle)
    print(json.dumps(bundle["summary"], ensure_ascii=False))
    print(paths[0])
    print(paths[1])
    return 0 if bundle["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
