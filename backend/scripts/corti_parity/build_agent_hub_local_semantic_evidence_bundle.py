"""Build fresh semantic evidence for the locally runnable Hub Agents.

This is deliberately separate from the strict 26-Agent live-provider bundle.
It may prove only Agents whose authoritative runtime matrix declares either a
deterministic local execution path or a governed local baseline. It can never
mark an external-model-dependent Agent verified or satisfy the full release
gate.
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
    sha256_file,
)
from scripts.corti_parity.build_agent_hub_runtime_matrix import (  # noqa: E402
    build_matrix,
)
from scripts.corti_parity.build_agent_hub_semantic_evidence_bundle import (  # noqa: E402
    DEFAULT_AGENTS_DIR,
    DEFAULT_REFERENCE_CASES,
    SUPPORTED_SCHEMAS,
    _freshness_errors,
    _read_json,
    _snapshot_from_agents_dir,
    _validate_live_report,
    _validate_reference,
    verify_bundle_digest,
)


LOCAL_EXECUTION_EXPECTATIONS = frozenset({
    "local_deterministic_execution",
    "local_baseline_with_optional_external_provider",
})
EXPECTED_LOCAL_AGENT_COUNT = 24
LOCAL_QUALITY_SCOPE = (
    "fresh_local_http_semantic_safety_stability_not_external_model_or_clinical_accuracy"
)
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "agent_hub" / "local_semantic_evidence"


def _local_agent_ids(
    agents_dir: Path,
    *,
    matrix: dict[str, Any] | None = None,
) -> list[str]:
    matrix = matrix or build_matrix(agents_dir.resolve())
    agent_ids = sorted(
        str(row["agent_id"])
        for row in matrix.get("rows", [])
        if row.get("hub_visible") is True
        and row.get("offline_execution_expectation") in LOCAL_EXECUTION_EXPECTATIONS
    )
    if len(agent_ids) != EXPECTED_LOCAL_AGENT_COUNT:
        raise ValueError(
            "authoritative runtime matrix must expose exactly twenty-four local-baseline Agents"
        )
    return agent_ids


def _scoped_snapshot(
    agents_dir: Path,
    *,
    agent_ids: list[str],
) -> dict[str, dict[str, str]]:
    full = _snapshot_from_agents_dir(agents_dir.resolve())
    if not set(agent_ids).issubset(full):
        raise ValueError("local Agent scope is not contained in the visible Pack snapshot")
    return {agent_id: full[agent_id] for agent_id in agent_ids}


def build_local_bundle(
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
    agents_dir = agents_dir.resolve()
    matrix = matrix or build_matrix(agents_dir)
    agent_ids = _local_agent_ids(agents_dir, matrix=matrix)
    snapshot = _scoped_snapshot(agents_dir, agent_ids=agent_ids)
    expected_count = len(agent_ids)
    visible_agent_count = len(_snapshot_from_agents_dir(agents_dir))
    external_agent_count = visible_agent_count - expected_count
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
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
            current_snapshot=snapshot,
            external_agents=set(),
            now=current,
            max_age=max_age,
            expected_count=expected_count,
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
        current_snapshot=snapshot,
        external_agents=set(),
        now=current,
        max_age=max_age,
        expected_count=expected_count,
        trusted_seed_hashes=trusted_seed_hashes,
        trusted_seed_reports=trusted_seed_reports,
    )
    errors.extend(stability_errors)
    per_source["stability"] = stability_results
    reference_errors, reference_results = _validate_reference(
        report_path=source_paths["reference"],
        report=reports["reference"],
        examples_path=source_paths["examples"],
        example_rows=per_source.get("examples", {}),
        current_snapshot=snapshot,
        now=current,
        max_age=max_age,
        reference_cases_path=reference_cases_path.resolve(),
        expected_count=expected_count,
    )
    errors.extend(reference_errors)
    per_source["reference"] = reference_results
    errors = sorted(set(errors))
    agent_results = [
        {
            "agent_id": agent_id,
            "gates": {
                label: bool((per_source.get(label, {}).get(agent_id) or {}).get("passed"))
                for label in ("examples", "adversarial", "reference", "stability")
            },
        }
        for agent_id in agent_ids
    ]
    for item in agent_results:
        item["local_semantic_e2e_verified"] = bool(
            not errors and all(item["gates"].values())
        )

    bundle: dict[str, Any] = {
        "schema_version": "icoder.agent-hub-local-semantic-evidence-bundle/v1",
        "generated_at": current.isoformat(),
        "quality_scope": LOCAL_QUALITY_SCOPE,
        "max_age_hours": max_age_hours,
        "valid": not errors and expected_count == EXPECTED_LOCAL_AGENT_COUNT,
        "errors": errors,
        "summary": {
            "visible_agents": visible_agent_count,
            "local_agents_expected": expected_count,
            "local_semantic_e2e_verified": sum(
                bool(item["local_semantic_e2e_verified"])
                for item in agent_results
            ),
            "external_model_agents_not_evaluated": external_agent_count,
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
        "agent_snapshot": snapshot,
        "agent_results": agent_results,
        "limitations": [
            "This proves twenty-four local deterministic or governed-baseline Agents over fresh loopback HTTP; it is not the strict 26-Agent live-provider gate.",
            f"{external_agent_count} external-model-dependent Agents were not evaluated and remain semantic-live pending.",
            "Pack-owned synthetic cases are not independent clinical gold, Corti parity, hospital acceptance, or production approval.",
        ],
    }
    digest_payload = copy.deepcopy(bundle)
    bundle["bundle_sha256"] = canonical_sha256(digest_payload)
    return bundle


def validate_local_bundle_file(
    bundle_path: Path,
    *,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    max_age_hours: float = 24.0,
    now: datetime | None = None,
    matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        supplied = _read_json(bundle_path.resolve())
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)], "verified_agent_ids": []}
    if supplied.get("schema_version") != (
        "icoder.agent-hub-local-semantic-evidence-bundle/v1"
    ):
        errors.append("bundle: unsupported schema_version")
    if supplied.get("quality_scope") != LOCAL_QUALITY_SCOPE:
        errors.append("bundle: local quality scope is missing")
    if not verify_bundle_digest(supplied):
        errors.append("bundle: canonical digest mismatch")
    if supplied.get("valid") is not True:
        errors.append("bundle: source validation did not pass")

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors.extend(
        _freshness_errors(
            supplied,
            label="bundle",
            now=current,
            max_age=timedelta(hours=max_age_hours),
        )
    )
    sources = supplied.get("sources")
    sources = sources if isinstance(sources, dict) else {}
    source_paths: dict[str, Path] = {}
    for label in SUPPORTED_SCHEMAS:
        source = sources.get(label)
        source = source if isinstance(source, dict) else {}
        path = Path(str(source.get("path") or ""))
        if not path.is_file():
            relative = Path(str(source.get("relative_path") or ""))
            candidate = bundle_path.resolve().parent.parent / relative
            if candidate.is_file():
                path = candidate
        source_paths[label] = path.resolve()

    rebuilt = build_local_bundle(
        examples_path=source_paths["examples"],
        adversarial_path=source_paths["adversarial"],
        reference_path=source_paths["reference"],
        stability_path=source_paths["stability"],
        agents_dir=agents_dir.resolve(),
        max_age_hours=max_age_hours,
        now=current,
        matrix=matrix,
    )
    if not rebuilt.get("valid"):
        errors.extend(str(item) for item in rebuilt.get("errors") or [])
    if supplied.get("agent_snapshot") != rebuilt.get("agent_snapshot"):
        errors.append("bundle: current local Agent snapshot mismatch")
    if supplied.get("agent_results") != rebuilt.get("agent_results"):
        errors.append("bundle: local Agent verification rows do not match sources")
    if {
        label: str((sources.get(label) or {}).get("sha256") or "")
        for label in SUPPORTED_SCHEMAS
    } != {
        label: str((rebuilt.get("sources", {}).get(label) or {}).get("sha256") or "")
        for label in SUPPORTED_SCHEMAS
    }:
        errors.append("bundle: source artifact digest mismatch")
    verified = sorted(
        str(item["agent_id"])
        for item in rebuilt.get("agent_results", [])
        if item.get("local_semantic_e2e_verified") is True
    )
    if len(verified) != EXPECTED_LOCAL_AGENT_COUNT:
        errors.append("bundle: all twenty-four authoritative local Agents must be verified")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "verified_agent_ids": verified if not errors else [],
        "bundle_sha256": str(supplied.get("bundle_sha256") or ""),
    }


def write_bundle(out_dir: Path, bundle: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "agent_hub_local_semantic_evidence_bundle.json"
    md_path = out_dir / "agent_hub_local_semantic_evidence_bundle.md"
    json_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = bundle["summary"]
    lines = [
        "# Agent Hub local semantic evidence bundle",
        "",
        f"Generated: `{bundle['generated_at']}`",
        "",
        f"Validation: **{'PASS' if bundle['valid'] else 'FAIL'}**",
        "",
        f"Fresh local HTTP semantic evidence: **{summary['local_semantic_e2e_verified']}/{summary['local_agents_expected']}**",
        "",
        "This bundle cannot satisfy or replace the strict 26-Agent live-provider gate.",
        "",
        "## Limitations",
        "",
    ]
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
    bundle = build_local_bundle(
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
