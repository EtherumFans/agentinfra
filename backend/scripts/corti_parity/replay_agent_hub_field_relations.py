"""Adversarially replay every declared Agent Hub cross-field relation.

The command is offline and deterministic. It activates each relation against a
checked-in example, proves the consistent form is accepted, then violates each
``must`` predicate independently and requires a PHI-safe ``fieldRelation``
failure naming the owning stable relation id.
"""

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
    declared_field_relations,
    declared_field_schemas,
    validate_declared_field_schemas,
    validate_field_relations_definition,
)


DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_OUTPUT_DIR = (
    BACKEND_ROOT.parent
    / "reports"
    / "agent_hub"
    / "field_relation_replay_20260815"
)
_MISSING = object()


def _schema_at(
    contract: dict[str, Any],
    path: str,
    scope_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parts = path.split(".")
    if scope_schema is None:
        schema = declared_field_schemas(contract)[parts[0]]
        parts = parts[1:]
    else:
        schema = scope_schema
    for part in parts:
        schema = schema["properties"][part]
    return schema


def _get(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _set(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: dict[str, Any] = payload
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _delete(payload: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    current: Any = payload
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _value_for_schema(schema: dict[str, Any], *, non_empty: bool = False) -> Any:
    kind = schema.get("type")
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return copy.deepcopy(enum[0])
    if kind == "string":
        return "synthetic" if non_empty else ""
    if kind == "boolean":
        return True
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return float(schema.get("minimum", 0))
    if kind == "array":
        if non_empty:
            count = max(1, int(schema.get("minItems", 0)))
            return [
                _value_for_schema(schema["items"], non_empty=True)
                for _ in range(count)
            ]
        return []
    if kind == "object":
        properties = schema.get("properties") or {}
        return {
            name: _value_for_schema(properties[name], non_empty=True)
            for name in schema.get("required") or []
        }
    raise ValueError(f"unsupported schema type {kind!r}")


def _empty_for_schema(schema: dict[str, Any]) -> Any:
    return {"string": "", "array": [], "object": {}}[str(schema.get("type"))]


def _different_value(schema: dict[str, Any], current: Any) -> Any:
    kind = schema.get("type")
    if kind == "boolean":
        return not bool(current)
    if kind == "string":
        enum = schema.get("enum")
        if isinstance(enum, list):
            for item in enum:
                if item != current:
                    return item
        return "synthetic-alternative" if current != "synthetic-alternative" else "synthetic"
    if kind == "integer":
        return int(current) + 1
    if kind == "number":
        return float(current) + 0.1
    if kind == "array":
        return list(current) + [_value_for_schema(schema["items"], non_empty=True)]
    if kind == "object":
        return _value_for_schema(schema, non_empty=True)
    raise ValueError(f"unsupported schema type {kind!r}")


def _numeric_value(
    schema: dict[str, Any], threshold: float | int, *, matches: bool, operator: str
) -> float | int:
    step: float | int = 1 if schema.get("type") == "integer" else 0.01
    candidates = {
        "gt": threshold + step if matches else threshold,
        "gte": threshold if matches else threshold - step,
        "lt": threshold - step if matches else threshold,
        "lte": threshold if matches else threshold + step,
    }
    value = candidates[operator]
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, (int, float)):
        value = max(value, minimum)
    if isinstance(maximum, (int, float)):
        value = min(value, maximum)
    return int(value) if schema.get("type") == "integer" else float(value)


def _value_outside(schema: dict[str, Any], excluded: list[Any]) -> Any:
    kind = schema.get("type")
    candidates: list[Any]
    if kind == "string":
        candidates = ["synthetic-outside-relation", "synthetic-alternative"]
    elif kind == "boolean":
        candidates = [False, True]
    elif kind == "integer":
        candidates = [int(schema.get("minimum", 0)), int(schema.get("maximum", 100))]
    elif kind == "number":
        candidates = [float(schema.get("minimum", 0)), float(schema.get("maximum", 1))]
    else:
        candidates = [_different_value(schema, excluded[0])]
    for candidate in candidates:
        if candidate not in excluded:
            return candidate
    raise ValueError("relation value set exhausts the declared scalar domain")


def _same_json_value(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _predicate_matches(payload: dict[str, Any], predicate: dict[str, Any]) -> bool:
    value = _get(payload, predicate["path"])
    operator = predicate["operator"]
    if operator == "present":
        return value is not _MISSING
    if operator == "absent":
        return value is _MISSING
    if value is _MISSING:
        return False
    if operator == "equals":
        return _same_json_value(value, predicate.get("value"))
    if operator == "not_equals":
        return not _same_json_value(value, predicate.get("value"))
    if operator == "in":
        return any(_same_json_value(value, item) for item in predicate.get("value", []))
    if operator == "not_in":
        return not any(
            _same_json_value(value, item) for item in predicate.get("value", [])
        )
    if operator == "empty":
        return value in ("", [], {})
    if operator == "non_empty":
        return value not in ("", [], {})
    if operator in {"gt", "gte", "lt", "lte"}:
        threshold = predicate["value"]
        return {
            "gt": value > threshold,
            "gte": value >= threshold,
            "lt": value < threshold,
            "lte": value <= threshold,
        }[operator]
    if operator in {"equals_path", "not_equals_path"}:
        other = _get(payload, predicate["other_path"])
        matched = other is not _MISSING and _same_json_value(value, other)
        return matched if operator == "equals_path" else not matched
    if operator == "length_equals":
        other = _get(payload, predicate["other_path"])
        return isinstance(value, list) and len(value) == other
    return False


def _array_item_schema(contract: dict[str, Any], path: str) -> dict[str, Any]:
    return _schema_at(contract, path)["items"]


def _satisfy(
    payload: dict[str, Any],
    contract: dict[str, Any],
    predicate: dict[str, Any],
    scope_schema: dict[str, Any] | None = None,
) -> None:
    path = predicate["path"]
    operator = predicate["operator"]
    schema = _schema_at(contract, path, scope_schema)
    if operator == "equals":
        _set(payload, path, copy.deepcopy(predicate["value"]))
    elif operator == "not_equals":
        _set(payload, path, _different_value(schema, predicate["value"]))
    elif operator == "in":
        _set(payload, path, copy.deepcopy(predicate["value"][0]))
    elif operator == "not_in":
        _set(payload, path, _value_outside(schema, predicate["value"]))
    elif operator in {"gt", "gte", "lt", "lte"}:
        _set(
            payload,
            path,
            _numeric_value(schema, predicate["value"], matches=True, operator=operator),
        )
    elif operator == "count_where_equals":
        collection = _get(payload, path)
        if not isinstance(collection, list):
            collection = []
            _set(payload, path, collection)
        item_schema = _array_item_schema(contract, path)
        where = predicate["where"]
        target = predicate["value"]
        matching = [
            item for item in collection
            if isinstance(item, dict)
            and all(_predicate_matches(item, child) for child in where)
        ]
        while len(matching) < target:
            item = _value_for_schema(item_schema, non_empty=True)
            for child in where:
                _satisfy(item, contract, child, item_schema)
            collection.append(item)
            matching.append(item)
        for item in matching[target:]:
            _violate(item, contract, where[0], item_schema)
    elif operator == "contains_field_equals_path":
        collection = _get(payload, path)
        if not isinstance(collection, list):
            collection = []
            _set(payload, path, collection)
        item_schema = _array_item_schema(contract, path)
        where = predicate.get("where", [])
        target = _get(payload, predicate["other_path"])
        matches = [
            item for item in collection
            if isinstance(item, dict)
            and all(_predicate_matches(item, child) for child in where)
            and _same_json_value(_get(item, predicate["item_path"]), target)
        ]
        if not matches:
            eligible = [
                item for item in collection
                if isinstance(item, dict)
                and all(_predicate_matches(item, child) for child in where)
            ]
            item = (
                eligible[0]
                if eligible
                else _value_for_schema(item_schema, non_empty=True)
            )
            if not eligible:
                for child in where:
                    _satisfy(item, contract, child, item_schema)
                collection.append(item)
            _set(item, predicate["item_path"], copy.deepcopy(target))
    elif operator == "disjoint_fields":
        left = _get(payload, path)
        right = _get(payload, predicate["other_path"])
        if not isinstance(left, list):
            _set(payload, path, [])
        if not isinstance(right, list):
            _set(payload, predicate["other_path"], [])
        elif isinstance(left, list):
            excluded = [
                _get(item, predicate["item_path"])
                for item in left if isinstance(item, dict)
            ]
            right_item_schema = _array_item_schema(contract, predicate["other_path"])
            right_field_schema = _schema_at(
                contract, predicate["other_item_path"], right_item_schema
            )
            for item in right:
                if not isinstance(item, dict):
                    continue
                value = _get(item, predicate["other_item_path"])
                if value in excluded:
                    _set(
                        item,
                        predicate["other_item_path"],
                        _value_outside(right_field_schema, excluded),
                    )
    elif operator == "present":
        if _get(payload, path) is _MISSING:
            _set(payload, path, _value_for_schema(schema))
    elif operator == "absent":
        _delete(payload, path)
    elif operator == "empty":
        _set(payload, path, _empty_for_schema(schema))
    elif operator == "non_empty":
        value = _get(payload, path)
        if value is _MISSING or value in ("", [], {}):
            _set(payload, path, _value_for_schema(schema, non_empty=True))
    elif operator in {"equals_path", "not_equals_path"}:
        other = _get(payload, predicate["other_path"])
        if operator == "equals_path":
            _set(payload, path, copy.deepcopy(other))
        else:
            _set(payload, path, _different_value(schema, other))
    elif operator == "length_equals":
        value = _get(payload, path)
        _set(payload, predicate["other_path"], len(value))
    else:
        raise ValueError(f"unsupported operator {operator!r}")


def _violate(
    payload: dict[str, Any],
    contract: dict[str, Any],
    predicate: dict[str, Any],
    scope_schema: dict[str, Any] | None = None,
) -> None:
    path = predicate["path"]
    operator = predicate["operator"]
    schema = _schema_at(contract, path, scope_schema)
    if operator == "equals":
        _set(payload, path, _different_value(schema, predicate["value"]))
    elif operator == "not_equals":
        _set(payload, path, copy.deepcopy(predicate["value"]))
    elif operator == "in":
        _set(payload, path, _value_outside(schema, predicate["value"]))
    elif operator == "not_in":
        _set(payload, path, copy.deepcopy(predicate["value"][0]))
    elif operator in {"gt", "gte", "lt", "lte"}:
        _set(
            payload,
            path,
            _numeric_value(schema, predicate["value"], matches=False, operator=operator),
        )
    elif operator == "count_where_equals":
        collection = _get(payload, path)
        item_schema = _array_item_schema(contract, path)
        item = _value_for_schema(item_schema, non_empty=True)
        for child in predicate["where"]:
            _satisfy(item, contract, child, item_schema)
        collection.append(item)
    elif operator == "contains_field_equals_path":
        collection = _get(payload, path)
        item_schema = _array_item_schema(contract, path)
        field_schema = _schema_at(contract, predicate["item_path"], item_schema)
        values = [
            _get(item, predicate["item_path"])
            for item in collection if isinstance(item, dict)
        ]
        other_schema = _schema_at(contract, predicate["other_path"])
        _set(
            payload,
            predicate["other_path"],
            _value_outside(other_schema, values),
        )
    elif operator == "disjoint_fields":
        left = _get(payload, path)
        right = _get(payload, predicate["other_path"])
        left_item_schema = _array_item_schema(contract, path)
        right_item_schema = _array_item_schema(contract, predicate["other_path"])
        if not left:
            left.append(_value_for_schema(left_item_schema, non_empty=True))
        if not right:
            right.append(_value_for_schema(right_item_schema, non_empty=True))
        shared = _get(left[0], predicate["item_path"])
        _set(right[0], predicate["other_item_path"], copy.deepcopy(shared))
    elif operator == "present":
        _delete(payload, path)
    elif operator == "absent":
        _set(payload, path, _value_for_schema(schema))
    elif operator == "empty":
        _set(payload, path, _value_for_schema(schema, non_empty=True))
    elif operator == "non_empty":
        _set(payload, path, _empty_for_schema(schema))
    elif operator == "equals_path":
        other = _get(payload, predicate["other_path"])
        _set(payload, path, _different_value(schema, other))
    elif operator == "not_equals_path":
        _set(payload, path, copy.deepcopy(_get(payload, predicate["other_path"])))
    elif operator == "length_equals":
        value = _get(payload, path)
        _set(payload, predicate["other_path"], len(value) + 1)
    else:
        raise ValueError(f"unsupported operator {operator!r}")


def _satisfy_active_relations(
    payload: dict[str, Any],
    contract: dict[str, Any],
    relations: list[dict[str, Any]],
) -> None:
    """Keep unrelated active invariants valid after a targeted activation."""
    for _ in range(3):
        for relation in relations:
            for_each = relation.get("for_each")
            if isinstance(for_each, str):
                collection = _get(payload, for_each)
                if not isinstance(collection, list):
                    continue
                scopes = [item for item in collection if isinstance(item, dict)]
                scope_schema = _array_item_schema(contract, for_each)
            else:
                scopes = [payload]
                scope_schema = None
            for scope in scopes:
                if not all(
                    _predicate_matches(scope, predicate)
                    for predicate in relation["when"]
                ):
                    continue
                for predicate in relation["must"]:
                    _satisfy(scope, contract, predicate, scope_schema)


def replay(agents_dir: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    relation_count = 0
    relation_agents: set[str] = set()
    definition_errors: list[dict[str, Any]] = []
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        contract = pack.get("output_contract") or {}
        relations = declared_field_relations(contract)
        if not relations:
            continue
        agent = pack_path.parent.name
        relation_agents.add(agent)
        errors = validate_field_relations_definition(contract)
        if errors:
            definition_errors.append({"agent": agent, "errors": errors})
            continue
        examples = [item for item in pack.get("example_outputs") or [] if isinstance(item, dict)]
        if not examples:
            definition_errors.append({"agent": agent, "errors": ["missing example output"]})
            continue
        for relation in relations:
            relation_count += 1
            baseline = copy.deepcopy(examples[0])
            scope_schema = None
            for_each = relation.get("for_each")
            if isinstance(for_each, str):
                array_schema = _schema_at(contract, for_each)
                scope_schema = array_schema["items"]
                collection = _get(baseline, for_each)
                if not isinstance(collection, list):
                    collection = []
                    _set(baseline, for_each, collection)
                if not collection:
                    collection.append(_value_for_schema(scope_schema, non_empty=True))
                scope = collection[0]
            else:
                scope = baseline
            for predicate in relation["when"] + relation["must"]:
                _satisfy(scope, contract, predicate, scope_schema)
            _satisfy_active_relations(baseline, contract, relations)
            baseline_violations = [
                item.to_dict()
                for item in validate_declared_field_schemas(baseline, contract)
            ]
            for must_index, predicate in enumerate(relation["must"]):
                adversarial = copy.deepcopy(baseline)
                if isinstance(for_each, str):
                    adversarial_scope = _get(adversarial, for_each)[0]
                else:
                    adversarial_scope = adversarial
                _violate(
                    adversarial_scope,
                    contract,
                    predicate,
                    scope_schema,
                )
                violations = [
                    item.to_dict()
                    for item in validate_declared_field_schemas(adversarial, contract)
                ]
                expected = relation["id"]
                detected = any(
                    item.get("keyword") == "fieldRelation"
                    and item.get("expected") == expected
                    for item in violations
                )
                cases.append({
                    "agent": agent,
                    "schema_ref": contract.get("schema_ref"),
                    "relation_id": expected,
                    "must_index": must_index,
                    "operator": predicate.get("operator"),
                    "baseline_valid": not baseline_violations,
                    "relation_violation_detected": detected,
                    "violations": violations,
                })
    passed = (
        not definition_errors
        and bool(cases)
        and all(case["baseline_valid"] for case in cases)
        and all(case["relation_violation_detected"] for case in cases)
    )
    return {
        "schema_version": "icoder.agent-hub-field-relation-replay/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "relation_agents": len(relation_agents),
        "relations": relation_count,
        "adversarial_assertions": len(cases),
        "detected_assertions": sum(
            case["relation_violation_detected"] for case in cases
        ),
        "definition_errors": definition_errors,
        "cases": cases,
    }


def _render(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Hub cross-field relation replay",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Relation Agents: `{report['relation_agents']}`",
        f"- Relations: `{report['relations']}`",
        f"- Adversarial assertions: `{report['detected_assertions']}/{report['adversarial_assertions']}`",
        "",
        "| Agent | Relation | Must # | Operator | Baseline | Detected |",
        "|---|---|---:|---|---|---|",
    ]
    for case in report["cases"]:
        lines.append(
            "| {agent} | {relation_id} | {must_index} | {operator} | {baseline} | {detected} |".format(
                **case,
                baseline="yes" if case["baseline_valid"] else "no",
                detected="yes" if case["relation_violation_detected"] else "no",
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    report = replay(args.agents_dir.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "agent_hub_field_relation_replay.json"
    markdown_path = args.output_dir / "agent_hub_field_relation_replay.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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
