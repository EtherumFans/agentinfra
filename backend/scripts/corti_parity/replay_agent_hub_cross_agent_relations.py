"""Offline adversarial replay for declared Agent Hub cross-Agent relations."""

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
    declared_cross_agent_relations,
    declared_field_schemas,
    validate_cross_agent_relations,
    validate_cross_agent_relations_definition,
    validate_declared_field_schemas,
)


DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_OUTPUT_DIR = (
    BACKEND_ROOT.parent / "reports" / "agent_hub" / "cross_agent_replay_20260815"
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


def _item_with(path: str, value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    _set(result, path, value)
    return result


def replay(agents_dir: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    definition_errors: list[dict[str, Any]] = []
    relation_agents: set[str] = set()
    relation_count = 0
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        contract = pack.get("output_contract") or {}
        relations = declared_cross_agent_relations(contract)
        if not relations:
            continue
        agent = pack_path.parent.name
        relation_agents.add(agent)
        errors = validate_cross_agent_relations_definition(contract)
        if errors:
            definition_errors.append({"agent": agent, "errors": errors})
            continue
        schemas = declared_field_schemas(contract)
        for relation in relations:
            relation_count += 1
            root = relation["local_path"].split(".", 1)[0]
            root_schema = schemas[root]
            payload = {root: _value_for_schema(root_schema)}
            local_code = "I21.0"
            operator = relation["operator"]
            if operator.startswith("local_items_"):
                local_collection = _get(payload, relation["local_path"])
                if not isinstance(local_collection, list) or not local_collection:
                    local_collection = [{}]
                    _set(payload, relation["local_path"], local_collection)
                _set(local_collection[0], relation["local_item_path"], local_code)
            else:
                _set(payload, relation["local_path"], local_code)

            upstream_result: dict[str, Any] = {}
            if operator == "equals_upstream":
                _set(upstream_result, relation["upstream_path"], local_code)
            elif operator == "local_items_subset_upstream_values":
                for source in relation["upstream_sources"]:
                    if source.get("item_path"):
                        _set(
                            upstream_result,
                            source["path"],
                            [_item_with(source["item_path"], "ｉ２１．０")],
                        )
                    else:
                        _set(upstream_result, source["path"], "ｉ２１．０")
            else:
                _set(
                    upstream_result,
                    relation["upstream_path"],
                    [_item_with(relation["upstream_item_path"], "ｉ２１．０")],
                )
            upstream = [{
                "agent_id": relation["upstream_agent_id"],
                "result": upstream_result,
            }]
            isolated_contract = {
                "field_schemas": {root: root_schema},
                "cross_agent_relations": [relation],
            }
            schema_valid = not validate_declared_field_schemas(
                payload, isolated_contract
            )
            baseline_valid = not validate_cross_agent_relations(
                payload, isolated_contract, upstream
            )
            conflict = copy.deepcopy(payload)
            if operator.startswith("local_items_"):
                _set(
                    _get(conflict, relation["local_path"])[0],
                    relation["local_item_path"],
                    "J18.9",
                )
            else:
                _set(conflict, relation["local_path"], "J18.9")
            adversarial_cases = [
                ("value_conflict", conflict, f"{operator}_violated"),
                (
                    "ambiguous_upstream",
                    payload,
                    "upstream_result_ambiguous",
                ),
            ]
            for case_type, candidate, expected_actual in adversarial_cases:
                candidate_upstream = (
                    upstream + copy.deepcopy(upstream)
                    if case_type == "ambiguous_upstream" else upstream
                )
                violations = [
                    item.to_dict()
                    for item in validate_cross_agent_relations(
                        candidate,
                        isolated_contract,
                        candidate_upstream,
                    )
                ]
                cases.append({
                    "agent": agent,
                    "schema_ref": contract.get("schema_ref"),
                    "relation_id": relation["id"],
                    "case": case_type,
                    "schema_valid": schema_valid,
                    "baseline_valid": baseline_valid,
                    "detected": any(
                        item.get("keyword") == "crossAgentRelation"
                        and item.get("expected") == relation["id"]
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
        "schema_version": "icoder.agent-hub-cross-agent-replay/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "relation_agents": len(relation_agents),
        "relations": relation_count,
        "adversarial_assertions": len(cases),
        "detected_assertions": sum(case["detected"] for case in cases),
        "definition_errors": definition_errors,
        "cases": cases,
    }


def _render(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Hub cross-Agent relation replay",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Relation Agents: `{report['relation_agents']}`",
        f"- Relations: `{report['relations']}`",
        f"- Adversarial assertions: `{report['detected_assertions']}/{report['adversarial_assertions']}`",
        "",
        "| Agent | Relation | Case | Baseline | Detected |",
        "|---|---|---|---|---|",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['agent']} | {case['relation_id']} | {case['case']} | "
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
    json_path = args.output_dir / "agent_hub_cross_agent_replay.json"
    markdown_path = args.output_dir / "agent_hub_cross_agent_replay.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_render(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "passed", "relation_agents", "relations", "adversarial_assertions",
        "detected_assertions",
    )}, ensure_ascii=False))
    print(json_path)
    print(markdown_path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
