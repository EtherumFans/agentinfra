"""Promote validated Agent Hub E2E responses into Pack example outputs.

The source report must prove the public response passed runtime, Pack
contract, review and content-safety checks. Only Pack-declared output fields
are copied; transport/provider metadata is never promoted into examples.
Runtime correlation identifiers are replaced with stable sample values.

This is an explicit release-maintenance command, not application startup.
It is dry-run by default and writes only with ``--write``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from icoder_runtime.backends.structured_output_projector import project
from icoder_runtime.backends.output_contract_validation import (
    apply_declared_constants,
)


REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"
DEFAULT_REPORT = (
    REPO_ROOT
    / "reports"
    / "agent_hub"
    / "examples_e2e_20260815_compliance_cross_agent"
    / "agent_hub_examples_e2e.json"
)
DEFAULT_REFERENCE_CASES = (
    BACKEND_ROOT
    / "scripts"
    / "corti_parity"
    / "agent_hub_reference_quality_cases.json"
)
REQUIRED_SOURCE_CHECKS = (
    "http_contract_success",
    "runtime_success",
    "provider_completed",
    "content_safety",
    "clinical_quantities_grounded",
    "required_fields_complete",
    "structured_extraction_valid",
    "declared_field_schemas_valid",
    "manual_review_enforced",
    "manual_review_consistent",
    "production_writeback_blocked",
)
INTEGRITY_EXCLUDED_FIELDS = {
    "integrity",
    "downloads",
    "published_at",
    "loaded_at",
    "_pack_mtime_iso",
}


def _agent_id(pack: dict[str, Any]) -> str:
    return str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]


def _stable_runtime_refs(value: Any) -> Any:
    if isinstance(value, list):
        return [_stable_runtime_refs(item) for item in value]
    if not isinstance(value, dict):
        return value
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key == "run_id":
            clean[key] = "sample-run"
        elif key == "trace_id":
            clean[key] = "sample-trace"
        elif key == "context_id":
            clean[key] = "sample-context"
        else:
            clean[key] = _stable_runtime_refs(item)
    return clean


def _domain_result(
    response: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    """Replay current normalization over captured provider markdown."""
    result = response.get("result") or {}
    merged = dict(result) if isinstance(result, dict) else {}
    markdown = merged.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return merged
    agent_id = _agent_id(pack)
    contract = str((pack.get("output_contract") or {}).get("schema_ref") or "")
    projection = project(markdown, contract, agent_id)
    merged.update(projection.result)
    output_contract = pack.get("output_contract") or {}
    declared = set(output_contract.get("required_fields") or []) | set(
        output_contract.get("optional_fields") or []
    )
    if (
        str((pack.get("manifest") or {}).get("human_review") or "") == "required"
        and "manual_review_required" in declared
    ):
        merged["manual_review_required"] = True
    return apply_declared_constants(merged, output_contract)


def _visible_pack_paths(agents_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        paths[_agent_id(pack)] = pack_path
    return paths


def _canonical_pack_sha256(pack: dict[str, Any]) -> str:
    clean = {
        key: value
        for key, value in pack.items()
        if key not in INTEGRITY_EXCLUDED_FIELDS
    }
    payload = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sync_examples(
    agents_dir: Path,
    report_path: Path,
    *,
    write: bool,
    reference_cases_path: Path | None = DEFAULT_REFERENCE_CASES,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("total") != 26 or report.get("passed") != 26 or report.get("failed") != 0:
        raise ValueError("source report must prove a complete 26/26 passing run")
    rows = {str(row.get("agent_id")): row for row in report.get("rows") or []}
    visible_paths = _visible_pack_paths(agents_dir)
    reference_cases: dict[str, dict[str, Any]] = {}
    if reference_cases_path is not None:
        from scripts.corti_parity.run_agent_hub_reference_quality_replay import (
            load_reference_cases,
        )

        packs = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in visible_paths.values()
        ]
        _document, reference_cases = load_reference_cases(
            reference_cases_path.resolve(),
            packs,
        )
    changed: list[str] = []
    errors: list[str] = []
    pending_writes: list[tuple[Path, dict[str, Any]]] = []

    for agent_id, pack_path in visible_paths.items():
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        row = rows.get(agent_id)
        if row is None:
            errors.append(f"{agent_id}: missing E2E row")
            continue
        evaluation = row.get("evaluation") or {}
        checks = evaluation.get("checks") or {}
        failed_checks = [name for name in REQUIRED_SOURCE_CHECKS if checks.get(name) is not True]
        if evaluation.get("passed") is not True or failed_checks:
            errors.append(f"{agent_id}: source evidence failed {failed_checks}")
            continue

        response_path = report_path.parent / "responses" / f"{agent_id}.json"
        response = json.loads(response_path.read_text(encoding="utf-8"))
        result = _domain_result(response, pack)
        case = reference_cases.get(agent_id)
        if case is not None:
            from scripts.corti_parity.run_agent_hub_reference_quality_replay import (
                evaluate_reference_output,
            )

            semantic = evaluate_reference_output(result, case)
            if not semantic["assertions_passed"]:
                failed_paths = [
                    item["path"]
                    for item in semantic["assertions"]
                    if not item["passed"]
                ]
                errors.append(
                    f"{agent_id}: source evidence failed Pack-owned reference "
                    f"semantics {failed_paths}"
                )
                continue
        required = list((pack.get("output_contract") or {}).get("required_fields") or [])
        optional = list((pack.get("output_contract") or {}).get("optional_fields") or [])
        missing = [field for field in required if field not in result]
        if missing:
            errors.append(f"{agent_id}: response missing Pack fields {missing}")
            continue
        example = {
            field: _stable_runtime_refs(result[field])
            for field in required + optional
            if field in result
        }
        if pack.get("example_outputs") != [example]:
            changed.append(agent_id)
            if write:
                pack["example_outputs"] = [example]
                if isinstance(pack.get("integrity"), dict):
                    pack["integrity"]["sha256"] = _canonical_pack_sha256(pack)
                pending_writes.append((pack_path, pack))

    if set(rows) != set(visible_paths):
        errors.append(
            "source/Pack agent sets differ: "
            f"missing={sorted(set(visible_paths) - set(rows))}, "
            f"extra={sorted(set(rows) - set(visible_paths))}"
        )
    if errors:
        raise ValueError("; ".join(errors))
    for pack_path, pack in pending_writes:
        pack_path.write_text(
            json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return {
        "visible_agents": len(visible_paths),
        "changed_agents": changed,
        "write": write,
        "source_report": str(report_path),
        "reference_cases": (
            str(reference_cases_path) if reference_cases_path is not None else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--reference-cases",
        type=Path,
        default=DEFAULT_REFERENCE_CASES,
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = sync_examples(
        args.agents_dir.resolve(),
        args.report.resolve(),
        write=args.write,
        reference_cases_path=args.reference_cases.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
