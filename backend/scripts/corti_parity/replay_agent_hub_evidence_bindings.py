"""Offline adversarial replay for exact Agent Hub evidence quote/span bindings."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from icoder_runtime.backends.output_contract_validation import (
    declared_evidence_bindings,
    declared_field_schemas,
    validate_declared_field_schemas,
    validate_evidence_bindings,
    validate_evidence_bindings_definition,
)


DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_OUTPUT_DIR = (
    BACKEND_ROOT.parent / "reports" / "agent_hub" / "evidence_binding_replay_20260815"
)


def _value_for_schema(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return copy.deepcopy(enum[0])
    if kind == "string":
        return "synthetic"
    if kind == "boolean":
        return True
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return float(schema.get("minimum", 0))
    if kind == "array":
        count = max(1, int(schema.get("minItems", 0)))
        return [_value_for_schema(schema["items"]) for _ in range(count)]
    if kind == "object":
        properties = schema.get("properties") or {}
        return {
            name: _value_for_schema(properties[name])
            for name in schema.get("required") or []
        }
    raise ValueError(f"unsupported schema type {kind!r}")


def _set(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = payload
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _get(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        current = current[part]
    return current


def _array_schema(contract: dict[str, Any], path: str) -> tuple[str, dict[str, Any]]:
    parts = path.split(".")
    root = parts[0]
    schema = declared_field_schemas(contract)[root]
    for part in parts[1:]:
        schema = schema["properties"][part]
    return root, schema


def replay(agents_dir: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    definition_errors: list[dict[str, Any]] = []
    binding_agents: set[str] = set()
    binding_count = 0
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        contract = pack.get("output_contract") or {}
        bindings = declared_evidence_bindings(contract)
        if not bindings:
            continue
        agent = pack_path.parent.name
        binding_agents.add(agent)
        errors = validate_evidence_bindings_definition(contract)
        if errors:
            definition_errors.append({"agent": agent, "errors": errors})
            continue
        for binding in bindings:
            binding_count += 1
            array_path = binding["for_each"]
            root_field, array_schema = _array_schema(contract, array_path)
            item = _value_for_schema(array_schema["items"])
            evidence = "synthetic-evidence"
            source = f"prefix:{evidence}:suffix"
            start = len("prefix:")
            end = start + len(evidence)
            _set(item, binding["text_path"], evidence)
            if "span_path" in binding:
                _set(item, binding["span_path"], [start, end])
            else:
                _set(item, binding["start_path"], start)
                _set(item, binding["end_path"], end)
            source_documents = []
            if "document_id_path" in binding:
                _set(item, binding["document_id_path"], "doc-1")
                document = {"document_id": "doc-1", "text": source}
                if "document_version_path" in binding:
                    _set(item, binding["document_version_path"], "v1")
                    document["document_version"] = "v1"
                source_documents.append(document)
            root_schema = declared_field_schemas(contract)[root_field]
            payload: dict[str, Any] = {
                root_field: _value_for_schema(root_schema)
            }
            _set(payload, array_path, [item])
            isolated_contract = {
                "field_schemas": {root_field: root_schema},
                "evidence_bindings": [binding],
            }
            schema_valid = not validate_declared_field_schemas(
                payload, isolated_contract
            )
            baseline_valid = not validate_evidence_bindings(
                payload,
                isolated_contract,
                source,
                source_documents=source_documents,
            )
            mismatch = copy.deepcopy(payload)
            mismatch_item = _get(mismatch, array_path)[0]
            _set(mismatch_item, binding["text_path"], "synthetic-mismatch")
            bounds = copy.deepcopy(payload)
            bounds_item = _get(bounds, array_path)[0]
            if "span_path" in binding:
                _set(
                    bounds_item,
                    binding["span_path"],
                    [start, len(source) + 10],
                )
            else:
                _set(bounds_item, binding["end_path"], len(source) + 10)
            for case_type, adversarial, expected_actual in (
                ("source_text_mismatch", mismatch, "source_text_mismatch"),
                ("out_of_source_bounds", bounds, "out_of_source_bounds"),
            ):
                violations = [
                    item.to_dict()
                    for item in validate_evidence_bindings(
                        adversarial,
                        isolated_contract,
                        source,
                        source_documents=source_documents,
                    )
                ]
                cases.append({
                    "agent": agent,
                    "schema_ref": contract.get("schema_ref"),
                    "binding_id": binding["id"],
                    "case": case_type,
                    "schema_valid": schema_valid,
                    "baseline_valid": baseline_valid,
                    "detected": any(
                        item.get("keyword") == "evidenceBinding"
                        and item.get("expected") == binding["id"]
                        and item.get("actual") == expected_actual
                        for item in violations
                    ),
                    "violations": violations,
                })
    passed = (
        not definition_errors
        and bool(cases)
        and all(case["schema_valid"] for case in cases)
        and all(case["baseline_valid"] for case in cases)
        and all(case["detected"] for case in cases)
    )
    return {
        "schema_version": "icoder.agent-hub-evidence-binding-replay/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "binding_agents": len(binding_agents),
        "bindings": binding_count,
        "adversarial_assertions": len(cases),
        "detected_assertions": sum(case["detected"] for case in cases),
        "definition_errors": definition_errors,
        "cases": cases,
    }


def _render(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Hub evidence binding replay",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Binding Agents: `{report['binding_agents']}`",
        f"- Bindings: `{report['bindings']}`",
        f"- Adversarial assertions: `{report['detected_assertions']}/{report['adversarial_assertions']}`",
        "",
        "| Agent | Binding | Case | Baseline | Detected |",
        "|---|---|---|---|---|",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['agent']} | {case['binding_id']} | {case['case']} | "
            f"{'yes' if case['baseline_valid'] else 'no'} | "
            f"{'yes' if case['detected'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    report = replay(args.agents_dir.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "agent_hub_evidence_binding_replay.json"
    markdown_path = args.output_dir / "agent_hub_evidence_binding_replay.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_render(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "passed", "binding_agents", "bindings", "adversarial_assertions",
        "detected_assertions",
    )}, ensure_ascii=False))
    print(json_path)
    print(markdown_path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
