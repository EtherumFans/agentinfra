"""Validate the observed Corti pre-built Agent catalog against iCoDer Packs.

This is an offline development gate.  It proves catalog mapping and local
engineering readiness only; it deliberately cannot promote clinical-quality
or production-readiness claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.corti_parity.build_agent_hub_runtime_matrix import build_matrix


DEFAULT_CATALOG = Path(__file__).with_name("corti_prebuilt_agent_catalog.json")
DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT.parent / "reports" / "corti_parity"

EXPECTED_CORTI_AGENTS = (
    ("icd-10-index-navigator", "ICD-10 Index Navigator"),
    ("rule-explainer", "Rule Explainer"),
    ("compliance-guardrail", "Compliance Guardrail"),
    ("code-validation", "Code Validation"),
    ("procedure-entity-extractor", "Procedure Entity Extractor"),
    ("diagnostic-entity-extractor", "Diagnostic Entity Extractor"),
    ("surgical-registry-intelligence", "Surgical Registry Intelligence"),
    ("icu-admission-summary", "ICU Admission Summary"),
    ("triage-and-initial-assessment", "Triage and Initial Assessment"),
    ("note-completeness", "Note Completeness"),
    ("medication-reconciliation", "Medication Reconciliation"),
    ("denial-appeals", "Denial Appeals"),
    ("patient-discharge-education", "Patient Discharge Education"),
    ("nursing-shift-handoff", "Nursing Shift Handoff"),
    ("prior-authorization", "Prior Authorization"),
    ("referral-generator", "Referral Generator"),
    ("clinical-education", "Clinical Education"),
    ("medical-coding", "Medical Coding"),
    ("clinical-guidelines", "Clinical Guidelines"),
    (
        "clinical-documentation-improvement",
        "Clinical Documentation Improvement (CDI)",
    ),
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _row_development_errors(
    row: dict[str, Any], required_output_fields: list[str]
) -> list[str]:
    errors: list[str] = []
    declared = set(row["required_output_fields"] + row["optional_output_fields"])
    missing_fields = sorted(set(required_output_fields) - declared)
    if missing_fields:
        errors.append(f"missing required parity output fields: {missing_fields}")
    checks = {
        "Hub-visible": row["hub_visible"],
        "executable": row["pack_status"] == "executable",
        "provider-resolvable": row["provider_resolves"],
        "launch-candidate-ready": row["launch_candidate_ready"],
        "typed output contract complete": row["type_contract_complete"],
        "nested output schema complete": row["nested_schema_contract_complete"],
        "nested-schema example valid": row["nested_schema_valid_example_outputs"] > 0,
        "example input present": row["example_input_count"] > 0,
        "example output present": row["example_output_count"] > 0,
        "immutable contract registered": row["contract_registry_match"],
        "field relations valid": row["field_relations_valid"],
        "evidence bindings valid": row["evidence_bindings_valid"],
        "cross-Agent relations valid": row["cross_agent_relations_valid"],
        "production writeback blocked": row["production_writeback_blocked"],
    }
    errors.extend(label for label, value in checks.items() if not value)
    return errors


def validate_catalog(
    catalog_path: Path = DEFAULT_CATALOG,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
) -> dict[str, Any]:
    catalog = _read_json(catalog_path)
    entries = catalog.get("agents")
    if not isinstance(entries, list):
        entries = []
    matrix = build_matrix(agents_dir)
    rows_by_id = {row["agent_id"]: row for row in matrix["rows"]}

    catalog_errors: list[str] = []
    observed_identity = [
        (entry.get("corti_agent_id"), entry.get("corti_name"))
        for entry in entries
        if isinstance(entry, dict)
    ]
    if tuple(observed_identity) != EXPECTED_CORTI_AGENTS:
        catalog_errors.append(
            "catalog identities/order differ from the authenticated 20-Agent observation"
        )
    if [entry.get("order") for entry in entries if isinstance(entry, dict)] != list(
        range(1, 21)
    ):
        catalog_errors.append("catalog order must be exactly 1..20")

    corti_ids = [
        entry.get("corti_agent_id") for entry in entries if isinstance(entry, dict)
    ]
    icoder_ids = [
        entry.get("icoder_agent_id") for entry in entries if isinstance(entry, dict)
    ]
    if len(corti_ids) != len(set(corti_ids)):
        catalog_errors.append("Corti Agent IDs must be unique")
    if len(icoder_ids) != len(set(icoder_ids)):
        catalog_errors.append("iCoDer mappings must be one-to-one")

    boundaries = catalog.get("verification_boundaries") or {}
    if boundaries.get("clinical_quality_verified") is not False:
        catalog_errors.append("clinical_quality_verified must remain false in this gate")
    if boundaries.get("production_ready_verified") is not False:
        catalog_errors.append("production_ready_verified must remain false in this gate")
    external_gates = boundaries.get("external_gates") or []
    if not isinstance(external_gates, list) or len(external_gates) < 4:
        catalog_errors.append("at least four explicit external release gates are required")

    results: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            catalog_errors.append("every catalog entry must be an object")
            continue
        agent_id = str(entry.get("icoder_agent_id") or "")
        row = rows_by_id.get(agent_id)
        mapping_errors: list[str] = []
        development_errors: list[str] = []
        china_errors: list[str] = []
        if row is None:
            mapping_errors.append(f"mapped iCoDer Agent not found: {agent_id or '<empty>'}")
        else:
            required_fields = entry.get("required_output_fields") or []
            if not isinstance(required_fields, list) or not required_fields:
                development_errors.append("required_output_fields must be a non-empty list")
                required_fields = []
            development_errors.extend(_row_development_errors(row, required_fields))

            pack_path = agents_dir / row["agent_id"] / "agent_pack.json"
            # Directory names are not required to equal Agent IDs, so locate by ref
            # when the conventional path does not exist.
            if not pack_path.exists():
                pack_path = next(
                    (
                        path
                        for path in agents_dir.glob("*/agent_pack.json")
                        if _read_json(path).get("agent_ref", "").rsplit("/", 1)[-1]
                        .split("@", 1)[0]
                        == agent_id
                    ),
                    pack_path,
                )
            if not pack_path.exists():
                mapping_errors.append(f"Pack source not found for {agent_id}")
            else:
                pack = _read_json(pack_path)
                searchable = json.dumps(pack, ensure_ascii=False)
                adaptation = entry.get("china_adaptation") or {}
                markers = adaptation.get("required_markers") or []
                if not adaptation.get("profile"):
                    china_errors.append("China adaptation profile is missing")
                if not isinstance(markers, list) or not markers:
                    china_errors.append("China adaptation markers must be non-empty")
                else:
                    china_errors.extend(
                        f"China adaptation marker not found: {marker}"
                        for marker in markers
                        if not isinstance(marker, str) or marker not in searchable
                    )

        gap = entry.get("remaining_capability_gap")
        if not isinstance(gap, str) or not gap.strip():
            development_errors.append("remaining_capability_gap must be explicit")
        catalog_mapped = not mapping_errors
        development_verified = catalog_mapped and not development_errors
        china_profile_declared = catalog_mapped and not china_errors
        results.append(
            {
                "order": entry.get("order"),
                "corti_agent_id": entry.get("corti_agent_id"),
                "corti_name": entry.get("corti_name"),
                "icoder_agent_id": agent_id,
                "catalog_mapped": catalog_mapped,
                "development_verified": development_verified,
                "china_profile_declared": china_profile_declared,
                "clinical_quality_verified": False,
                "production_ready_verified": False,
                "remaining_capability_gap": gap,
                "errors": mapping_errors + development_errors + china_errors,
            }
        )

    summary = {
        "expected_corti_agents": len(EXPECTED_CORTI_AGENTS),
        "catalog_entries": len(entries),
        "catalog_mapped": sum(item["catalog_mapped"] for item in results),
        "development_verified": sum(item["development_verified"] for item in results),
        "china_profile_declared": sum(item["china_profile_declared"] for item in results),
        "clinical_quality_verified": 0,
        "production_ready_verified": 0,
    }
    failed_agents = [
        item["corti_agent_id"]
        for item in results
        if not (
            item["catalog_mapped"]
            and item["development_verified"]
            and item["china_profile_declared"]
        )
    ]
    passed = (
        not catalog_errors
        and not failed_agents
        and summary["catalog_entries"] == len(EXPECTED_CORTI_AGENTS)
    )
    return {
        "schema_version": "icoder.corti-prebuilt-agent-parity-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_development_gate",
        "catalog_source": str(catalog_path),
        "agents_source": str(agents_dir),
        "passed": passed,
        "catalog_errors": catalog_errors,
        "failed_agents": failed_agents,
        "summary": summary,
        "verification_boundaries": boundaries,
        "agents": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Corti pre-built Agent parity gate",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        f"Gate result: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "## Verified scope",
        "",
        f"- Catalog mapped: {summary['catalog_mapped']}/{summary['expected_corti_agents']}",
        f"- Development verified: {summary['development_verified']}/{summary['expected_corti_agents']}",
        f"- China profile declared: {summary['china_profile_declared']}/{summary['expected_corti_agents']}",
        "- Clinical quality verified: 0/20 (external gate)",
        "- Production ready verified: 0/20 (external gate)",
        "",
        "> PASS means offline catalog mapping and development engineering gates pass. It does not mean clinical-quality parity or production approval.",
        "",
        "## Per-Agent result",
        "",
        "| # | Corti Agent | iCoDer Agent | Mapped | Dev | China | Remaining gap |",
        "|---:|---|---|:---:|:---:|:---:|---|",
    ]
    for item in report["agents"]:
        yes = lambda value: "yes" if value else "no"
        lines.append(
            "| {order} | {corti} | `{icoder}` | {mapped} | {dev} | {china} | {gap} |".format(
                order=item["order"],
                corti=str(item["corti_name"]).replace("|", "\\|"),
                icoder=item["icoder_agent_id"],
                mapped=yes(item["catalog_mapped"]),
                dev=yes(item["development_verified"]),
                china=yes(item["china_profile_declared"]),
                gap=str(item["remaining_capability_gap"]).replace("|", "\\|"),
            )
        )
    if report["catalog_errors"] or report["failed_agents"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {error}" for error in report["catalog_errors"])
        for item in report["agents"]:
            lines.extend(
                f"- {item['corti_agent_id']}: {error}" for error in item["errors"]
            )
    lines.extend(["", "## External gates", ""])
    lines.extend(
        f"- {gate}"
        for gate in report["verification_boundaries"].get("external_gates", [])
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--assert-pass", action="store_true")
    args = parser.parse_args()

    report = validate_catalog(args.catalog.resolve(), args.agents_dir.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "corti_prebuilt_agent_parity.json"
    md_path = args.output_dir / "corti_prebuilt_agent_parity.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], **report["summary"]}, ensure_ascii=False))
    print(json_path)
    print(md_path)
    return 1 if args.assert_pass and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
