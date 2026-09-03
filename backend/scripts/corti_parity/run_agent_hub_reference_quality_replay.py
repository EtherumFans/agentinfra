"""Replay all visible Agent responses against Pack-owned reference semantics.

This is a development quality gate between schema-only E2E checks and an
independent clinical benchmark.  The assertions are authored against the
synthetic Pack examples and therefore must never be reported as clinician
gold, Corti parity, or production accuracy.

The replay is deliberately offline: a separate controlled live-E2E runner
captures responses, then this command scores those immutable artifacts.  No
credential, Authorization header, prompt, response body, or clinical text is
copied into the report; actual assertion values are represented by hashes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.corti_parity.run_agent_hub_examples_e2e import (  # noqa: E402
    DEFAULT_AGENTS_DIR,
    _agent_id,
    _evaluate,
    _visible_packs,
)


DEFAULT_CASES = Path(__file__).with_name(
    "agent_hub_reference_quality_cases.json"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT / "reports" / "agent_hub" / "reference_quality_replay"
)
_SUPPORTED_OPS = frozenset({
    "contains_all",
    "contains_any",
    "empty",
    "equals",
    "is_false",
    "is_true",
    "nonempty",
    "not_equals",
})
_SEMANTIC_OPS = frozenset({
    "contains_all", "contains_any", "equals", "not_equals"
})
_NON_SEMANTIC_PATHS = frozenset({"manual_review_required"})


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _lookup(payload: Any, path: str) -> tuple[bool, Any]:
    value = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def evaluate_assertion(
    result: dict[str, Any], assertion: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate one bounded assertion without copying actual content out."""

    path = str(assertion.get("path") or "")
    op = str(assertion.get("op") or "")
    expected = assertion.get("value")
    exists, actual = _lookup(result, path)
    passed = False
    if exists:
        if op == "is_true":
            passed = actual is True
        elif op == "is_false":
            passed = actual is False
        elif op == "nonempty":
            passed = _is_nonempty(actual)
        elif op == "empty":
            passed = not _is_nonempty(actual)
        elif op == "equals":
            passed = actual == expected
        elif op == "not_equals":
            passed = actual != expected
        elif op in {"contains_any", "contains_all"}:
            text = json.dumps(actual, ensure_ascii=False, default=str)
            values = [str(item) for item in (expected or [])]
            passed = bool(values) and (
                any(item in text for item in values)
                if op == "contains_any"
                else all(item in text for item in values)
            )
    return {
        "path": path,
        "op": op,
        "expected": expected,
        "exists": exists,
        "actual_type": type(actual).__name__ if exists else None,
        "actual_nonempty": _is_nonempty(actual) if exists else False,
        "actual_sha256": _sha256(actual) if exists else None,
        "passed": passed,
    }


def load_reference_cases(
    cases_path: Path,
    packs: list[dict[str, Any]],
    *,
    allow_case_superset: bool = False,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    document = json.loads(cases_path.read_text(encoding="utf-8"))
    if document.get("schema_version") != (
        "icoder.agent-hub-reference-quality-cases/v1"
    ):
        raise ValueError("reference case schema_version is unsupported")
    if document.get("scope") != (
        "pack_owned_synthetic_reference_semantics_not_independent_clinical_gold"
    ):
        raise ValueError("reference case scope must retain the non-gold boundary")

    pack_by_id = {_agent_id(pack): pack for pack in packs}
    cases = list(document.get("cases") or [])
    if allow_case_superset:
        cases = [
            case for case in cases
            if str(case.get("agent_id") or "") in pack_by_id
        ]
    case_ids = [str(case.get("agent_id") or "") for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("each visible Agent must have exactly one reference case")
    if set(case_ids) != set(pack_by_id):
        raise ValueError(
            "reference/visible Pack mismatch "
            f"missing={sorted(set(pack_by_id) - set(case_ids))} "
            f"extra={sorted(set(case_ids) - set(pack_by_id))}"
        )

    case_by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        agent_id = str(case["agent_id"])
        pack = pack_by_id[agent_id]
        example_index = case.get("example_index")
        if isinstance(example_index, bool) or not isinstance(example_index, int):
            raise ValueError(f"{agent_id}: example_index must be an integer")
        examples = list(pack.get("example_inputs") or [])
        references = list(pack.get("example_outputs") or [])
        if not 0 <= example_index < len(examples):
            raise ValueError(f"{agent_id}: example_index has no Pack input")
        if example_index >= len(references):
            raise ValueError(f"{agent_id}: example_index has no Pack reference output")
        assertions = list(case.get("assertions") or [])
        if len(assertions) < 3:
            raise ValueError(f"{agent_id}: at least three assertions are required")
        semantic_count = 0
        for assertion in assertions:
            path = str(assertion.get("path") or "")
            op = str(assertion.get("op") or "")
            if not path or op not in _SUPPORTED_OPS:
                raise ValueError(f"{agent_id}: unsupported assertion {assertion!r}")
            if op in {"contains_any", "contains_all"} and not isinstance(
                assertion.get("value"), list
            ):
                raise ValueError(f"{agent_id}: {op} requires a value list")
            if op in _SEMANTIC_OPS and path not in _NON_SEMANTIC_PATHS:
                semantic_count += 1
        if semantic_count < 1:
            raise ValueError(
                f"{agent_id}: at least one semantic discriminator is required"
            )
        case_by_id[agent_id] = case
    return document, case_by_id


def evaluate_reference_output(
    reference: dict[str, Any], case: dict[str, Any]
) -> dict[str, Any]:
    assertions = [
        evaluate_assertion(reference, assertion)
        for assertion in case["assertions"]
    ]
    return {
        "assertions": assertions,
        "assertions_passed": bool(assertions)
        and all(item["passed"] for item in assertions),
    }


def _load_source_report(
    source_report: Path | None,
    *,
    expected_agent_ids: set[str],
) -> dict[str, Any] | None:
    if source_report is None:
        return None
    report = json.loads(source_report.read_text(encoding="utf-8"))
    rows = list(report.get("rows") or [])
    expected_count = len(expected_agent_ids)
    if report.get("total") != expected_count or len(rows) != expected_count:
        raise ValueError(
            f"source report must contain all {expected_count} scoped Agents"
        )
    if report.get("passed") != expected_count or report.get("failed") != 0:
        raise ValueError(
            f"source report must prove a {expected_count}/{expected_count} "
            "successful base E2E run"
        )
    row_agent_ids = [str(row.get("agent_id") or "") for row in rows]
    if len(row_agent_ids) != len(set(row_agent_ids)):
        raise ValueError("source report Agent IDs must be unique")
    if set(row_agent_ids) != expected_agent_ids:
        raise ValueError("source report Agent IDs must match the visible Pack set")
    if any((row.get("evaluation") or {}).get("passed") is not True for row in rows):
        raise ValueError("every source report row must pass contract/safety evaluation")
    return {
        "path": str(source_report),
        "schema_version": report.get("schema_version"),
        "generated_at": report.get("generated_at"),
        "total": report.get("total"),
        "passed": report.get("passed"),
        "failed": report.get("failed"),
        "sha256": hashlib.sha256(source_report.read_bytes()).hexdigest(),
    }


def replay(
    *,
    agents_dir: Path,
    cases_path: Path,
    responses_dir: Path,
    source_report: Path | None = None,
    selected_agent_ids: set[str] | None = None,
) -> dict[str, Any]:
    packs = _visible_packs(agents_dir.resolve())
    selected = selected_agent_ids or set()
    if selected:
        available = {_agent_id(pack) for pack in packs}
        unknown = selected - available
        if unknown:
            raise ValueError(f"unknown selected Agent IDs: {sorted(unknown)}")
        packs = [pack for pack in packs if _agent_id(pack) in selected]
    document, cases = load_reference_cases(
        cases_path.resolve(),
        packs,
        allow_case_superset=bool(selected),
    )
    rows: list[dict[str, Any]] = []
    for pack in sorted(packs, key=_agent_id):
        agent_id = _agent_id(pack)
        case = cases[agent_id]
        response_path = responses_dir.resolve() / f"{agent_id}.json"
        if not response_path.is_file():
            raise ValueError(f"{agent_id}: response artifact is missing")
        response = json.loads(response_path.read_text(encoding="utf-8"))
        scenario_pack = copy.deepcopy(pack)
        example_index = int(case["example_index"])
        scenario_pack["example_inputs"] = [
            (pack.get("example_inputs") or [])[example_index]
        ]
        base = _evaluate(scenario_pack, response)
        result = response.get("result")
        result = result if isinstance(result, dict) else {}
        reference_evaluation = evaluate_reference_output(result, case)
        passed = bool(base.get("passed")) and reference_evaluation[
            "assertions_passed"
        ]
        safe_fail_closed = bool(base.get("safe_fail_closed"))
        rows.append({
            "agent_id": agent_id,
            "example_index": example_index,
            "input_sha256": _sha256(
                (pack.get("example_inputs") or [])[example_index]
            ),
            "pack_reference_sha256": _sha256(
                (pack.get("example_outputs") or [])[example_index]
            ),
            "response_sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
            "base_contract_safety_passed": bool(base.get("passed")),
            "reference_assertions_passed": reference_evaluation[
                "assertions_passed"
            ],
            "passed": passed,
            "safe_fail_closed": safe_fail_closed,
            "outcome": (
                "pack_reference_semantics_passed"
                if passed
                else "safe_fail_closed"
                if safe_fail_closed
                else "reference_or_contract_failed"
            ),
            "assertions": reference_evaluation["assertions"],
        })

    passed = sum(bool(row["passed"]) for row in rows)
    safe_fail_closed = sum(
        bool(row["safe_fail_closed"]) and not bool(row["passed"])
        for row in rows
    )
    return {
        "schema_version": "icoder.agent-hub-reference-quality-replay/v1",
        "quality_scope": document["scope"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network_used": False,
        "credential_used": False,
        "cases_path": str(cases_path.resolve()),
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "responses_dir": str(responses_dir.resolve()),
        "source_report": _load_source_report(
            source_report,
            expected_agent_ids=set(cases),
        ),
        "expected": len(packs),
        "completed": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "safe_fail_closed": safe_fail_closed,
        "all_passed": bool(rows) and passed == len(rows),
        "rows": rows,
        "limitations": [
            "Assertions are maintained against synthetic Pack examples, not independent clinician gold.",
            "Offline replay does not prove current Provider availability, latency, cost, stability, or Corti parity.",
            "A fresh live run must be captured separately with a new temporary credential before release evidence can be current.",
        ],
    }


def write_report(out_dir: Path, report: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "agent_hub_reference_quality_replay.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Agent Hub Pack reference quality replay",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "Scope: Pack-owned synthetic reference semantics; not independent clinical gold.",
        "",
        f"Result: **{report['passed']}/{report['completed']} passed; "
        f"expected {report['expected']}**",
        "",
        "| Agent | Contract/safety | Reference semantics | Outcome |",
        "|---|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['agent_id']} | "
            f"{'yes' if row['base_contract_safety_passed'] else 'no'} | "
            f"{'yes' if row['reference_assertions_passed'] else 'no'} | "
            f"{row['outcome']} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    (out_dir / "agent_hub_reference_quality_replay.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--responses-dir", type=Path, required=True)
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--agent-ids", default="")
    args = parser.parse_args()
    report = replay(
        agents_dir=args.agents_dir,
        cases_path=args.cases,
        responses_dir=args.responses_dir,
        source_report=args.source_report,
        selected_agent_ids={
            item.strip() for item in args.agent_ids.split(",") if item.strip()
        },
    )
    write_report(args.out_dir, report)
    print(json.dumps({
        "passed": report["passed"],
        "failed": report["failed"],
        "all_passed": report["all_passed"],
        "quality_scope": report["quality_scope"],
    }, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
