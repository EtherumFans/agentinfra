"""Repeat both Agent Hub live-E2E cases and report reliability statistics.

This runner measures transport/runtime/contract/safety repeatability, latency,
and error rate.  It deliberately does *not* score clinical correctness or
claim semantic equivalence with Corti.  Runs are serial and resumable to avoid
loading the native Windows stacks that have previously crashed this machine.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.corti_parity.run_agent_hub_adversarial_e2e import (
    DEFAULT_CASES,
    _evaluate_case,
)
from scripts.corti_parity.run_agent_hub_examples_e2e import (
    DEFAULT_AGENTS_DIR,
    _agent_id,
    _assert_native_stacks_not_loaded,
    _evaluate,
    _login,
    _visible_packs,
)
from scripts.corti_parity.agent_hub_live_evidence import (
    capture_trace_artifact,
    execution_provenance,
    pack_snapshot,
    row_execution_evidence,
    sha256_file,
    utc_now_iso,
)


DEFAULT_OUT_DIR = (
    BACKEND_ROOT.parent / "reports" / "agent_hub" / "stability_benchmark"
)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    """Return the nearest-rank percentile, suitable for small live samples."""
    if not values:
        return None
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _load_scenarios(
    agents_dir: Path,
    cases_path: Path,
    selected: set[str] | None = None,
) -> list[dict[str, Any]]:
    packs = _visible_packs(agents_dir.resolve())
    pack_by_id = {_agent_id(pack): pack for pack in packs}
    case_doc = json.loads(cases_path.resolve().read_text(encoding="utf-8"))
    suffix = str(case_doc.get("shared_untrusted_suffix") or "")
    adversarial_by_id = {
        str(case["agent_id"]): case for case in (case_doc.get("cases") or [])
    }
    if set(adversarial_by_id) != set(pack_by_id):
        raise RuntimeError(
            "adversarial/visible Pack mismatch "
            f"missing={sorted(set(pack_by_id) - set(adversarial_by_id))} "
            f"extra={sorted(set(adversarial_by_id) - set(pack_by_id))}"
        )

    scenarios: list[dict[str, Any]] = []
    for agent_id in sorted(pack_by_id):
        if selected and agent_id not in selected:
            continue
        pack = pack_by_id[agent_id]
        example = (pack.get("example_inputs") or [{}])[0]
        scenarios.append({
            "agent_id": agent_id,
            "case_kind": "happy",
            "case_id": "example-1",
            "pack": pack,
            "input_text": str(example.get("input_text") or example.get("text") or ""),
            "extra": example.get("extra") or {},
        })
        raw_case = copy.deepcopy(adversarial_by_id[agent_id])
        raw_case["input_text"] = str(raw_case["input_text"]) + suffix
        scenarios.append({
            "agent_id": agent_id,
            "case_kind": "adversarial",
            "case_id": str(raw_case["case_id"]),
            "pack": pack,
            "case": raw_case,
            "input_text": raw_case["input_text"],
            "extra": raw_case.get("extra") or {},
        })
    return scenarios


def _evaluate_scenario(
    scenario: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    if scenario["case_kind"] == "adversarial":
        return _evaluate_case(scenario["pack"], scenario["case"], response)
    return _evaluate(scenario["pack"], response)


def _base_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    return evaluation.get("base") or evaluation


def _row_passed(evaluation: dict[str, Any]) -> bool:
    return evaluation.get("passed") is True


def _extract_cost(response: dict[str, Any]) -> dict[str, Any]:
    """Preserve explicit zero cost while treating absent/malformed cost as unknown."""
    cost = response.get("cost")
    if not isinstance(cost, dict):
        return {"cost_known": False, "cost_amount": None, "cost_currency": None}
    amount = cost.get("amount")
    currency = str(cost.get("currency") or "").strip()
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or float(amount) < 0
        or not currency
    ):
        return {"cost_known": False, "cost_amount": None, "cost_currency": None}
    return {
        "cost_known": True,
        "cost_amount": round(float(amount), 8),
        "cost_currency": currency,
    }


def _build_summary(
    rows: list[dict[str, Any]],
    *,
    expected: int,
    repetitions: int,
    min_pass_rate: float,
    max_p95_seconds: float,
    agent_p95_budgets: dict[str, float] | None = None,
    base_url: str = "",
    session_started_at: str = "",
    agent_snapshot: dict[str, dict[str, str]] | None = None,
    seed_sources: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scenario_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["agent_id"])].append(row)
        scenario_groups[(
            str(row["agent_id"]),
            str(row["case_kind"]),
            str(row["case_id"]),
        )].append(row)

    latencies = [
        float(row["elapsed_seconds"])
        for row in rows
        if isinstance(row.get("elapsed_seconds"), (int, float))
        and float(row["elapsed_seconds"]) >= 0
    ]
    passed = sum(_row_passed(row["evaluation"]) for row in rows)
    pass_rate = passed / len(rows) if rows else 0.0
    per_agent: list[dict[str, Any]] = []
    for agent_id, agent_rows in sorted(grouped.items()):
        agent_latencies = [
            float(row["elapsed_seconds"])
            for row in agent_rows
            if isinstance(row.get("elapsed_seconds"), (int, float))
            and float(row["elapsed_seconds"]) >= 0
        ]
        agent_passed = sum(_row_passed(row["evaluation"]) for row in agent_rows)
        agent_scenario_groups = [
            scenario_rows
            for key, scenario_rows in scenario_groups.items()
            if key[0] == agent_id
        ]
        agent_known_cost_rows = [
            row for row in agent_rows if row.get("cost_known") is True
        ]
        agent_cost_totals: dict[str, float] = defaultdict(float)
        for row in agent_known_cost_rows:
            agent_cost_totals[str(row["cost_currency"])] += float(
                row["cost_amount"]
            )
        agent_p95 = _nearest_rank(agent_latencies, 0.95)
        agent_budget = (agent_p95_budgets or {}).get(agent_id)
        per_agent.append({
            "agent_id": agent_id,
            "completed": len(agent_rows),
            "passed": agent_passed,
            "pass_rate": round(agent_passed / len(agent_rows), 4),
            "error_rate": round(1 - (agent_passed / len(agent_rows)), 4),
            "p50_seconds": _nearest_rank(agent_latencies, 0.50),
            "p95_seconds": agent_p95,
            "p95_budget_seconds": agent_budget,
            "latency_budget_passed": bool(
                agent_budget is None
                or (agent_p95 is not None and agent_p95 <= agent_budget)
            ),
            "cost_coverage_rate": round(
                len(agent_known_cost_rows) / len(agent_rows), 4
            ),
            "cost_totals": {
                currency: round(amount, 8)
                for currency, amount in sorted(agent_cost_totals.items())
            },
            "all_scenarios_repeatably_passed": bool(
                len(agent_scenario_groups) == 2
                and all(
                    len(scenario_rows) == repetitions
                    and all(
                        _row_passed(row["evaluation"])
                        for row in scenario_rows
                    )
                    for scenario_rows in agent_scenario_groups
                )
            ),
        })

    base_evaluations = [_base_evaluation(row["evaluation"]) for row in rows]
    provider_completed = sum(
        bool((evaluation.get("checks") or {}).get("provider_completed"))
        for evaluation in base_evaluations
    )
    contract_passed = sum(
        bool((evaluation.get("checks") or {}).get("required_fields_complete"))
        and bool((evaluation.get("checks") or {}).get("structured_extraction_valid"))
        for evaluation in base_evaluations
    )
    safety_passed = sum(
        bool((evaluation.get("checks") or {}).get("content_safety"))
        and bool((evaluation.get("checks") or {}).get("clinical_quantities_grounded"))
        for evaluation in base_evaluations
    )
    p95 = _nearest_rank(latencies, 0.95)
    known_cost_rows = [row for row in rows if row.get("cost_known") is True]
    costs_by_currency: dict[str, list[float]] = defaultdict(list)
    for row in known_cost_rows:
        costs_by_currency[str(row["cost_currency"])].append(
            float(row["cost_amount"])
        )
    cost_summary = {
        currency: {
            "runs": len(amounts),
            "total": round(sum(amounts), 8),
            "average": round(sum(amounts) / len(amounts), 8),
            "p50": _nearest_rank(amounts, 0.50),
            "p95": _nearest_rank(amounts, 0.95),
        }
        for currency, amounts in sorted(costs_by_currency.items())
    }
    complete = len(rows) == expected
    latency_gate_passed = bool(
        max_p95_seconds <= 0 or (p95 is not None and p95 <= max_p95_seconds)
    )
    per_agent_latency_gate_passed = all(
        item["latency_budget_passed"] for item in per_agent
    )
    return {
        "schema_version": "icoder.agent-hub-stability-benchmark/v2",
        "quality_scope": "contract_safety_reliability_not_clinical_accuracy",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repetitions": repetitions,
        "expected": expected,
        "completed": len(rows),
        "complete": complete,
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": round(pass_rate, 4),
        "error_rate": round(1 - pass_rate, 4),
        "provider_completion_rate": round(provider_completed / len(rows), 4) if rows else 0.0,
        "contract_pass_rate": round(contract_passed / len(rows), 4) if rows else 0.0,
        "safety_pass_rate": round(safety_passed / len(rows), 4) if rows else 0.0,
        "p50_seconds": _nearest_rank(latencies, 0.50),
        "p95_seconds": p95,
        "cost_coverage_rate": round(len(known_cost_rows) / len(rows), 4) if rows else 0.0,
        "cost_unknown_runs": len(rows) - len(known_cost_rows),
        "costs_by_currency": cost_summary,
        "thresholds": {
            "min_pass_rate": min_pass_rate,
            "max_p95_seconds": max_p95_seconds,
            "agent_p95_budgets": dict(sorted((agent_p95_budgets or {}).items())),
        },
        "gates": {
            "complete": complete,
            "pass_rate": pass_rate >= min_pass_rate,
            "latency": latency_gate_passed,
            "per_agent_latency": per_agent_latency_gate_passed,
            "all_passed": bool(rows) and passed == len(rows),
        },
        "execution_provenance": execution_provenance(
            rows,
            base_url=base_url,
            session_started_at=session_started_at,
        ),
        "agent_snapshot": agent_snapshot or {},
        "seed_sources": seed_sources or {},
        "per_agent": per_agent,
        "rows": rows,
    }


def _write_summary(out_dir: Path, summary: dict[str, Any]) -> None:
    (out_dir / "agent_hub_stability_benchmark.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Agent Hub stability benchmark",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.",
        "",
        f"Result: **{summary['passed']}/{summary['completed']} passed; "
        f"expected {summary['expected']}**",
        "",
        f"Pass rate: `{summary['pass_rate']}`; error rate: `{summary['error_rate']}`; "
        f"P50: `{summary['p50_seconds']}s`; P95: `{summary['p95_seconds']}s`.",
        "",
        f"Cost coverage: `{summary['cost_coverage_rate']}`; unknown-cost runs: "
        f"`{summary['cost_unknown_runs']}`; totals by currency: "
        f"`{json.dumps(summary['costs_by_currency'], ensure_ascii=False, sort_keys=True)}`.",
        "",
        "| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for item in summary["per_agent"]:
        lines.append(
            f"| {item['agent_id']} | {item['completed']} | {item['pass_rate']} | "
            f"{item['error_rate']} | {item['p50_seconds']} | {item['p95_seconds']} | "
            f"{item['cost_coverage_rate']} | "
            f"{json.dumps(item['cost_totals'], ensure_ascii=False, sort_keys=True)} | "
            f"{'yes' if item['all_scenarios_repeatably_passed'] else 'no'} |"
        )
    lines.append("")
    (out_dir / "agent_hub_stability_benchmark.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def _response_name(scenario: dict[str, Any], repetition: int) -> str:
    case_id = _SAFE_NAME.sub("-", str(scenario["case_id"])).strip("-")
    return (
        f"{scenario['agent_id']}__{scenario['case_kind']}-{case_id}"
        f"__r{repetition:03d}.json"
    )


def _seed_path(
    scenario: dict[str, Any],
    repetition: int,
    happy_seed_dir: Path | None,
    adversarial_seed_dir: Path | None,
) -> Path | None:
    if repetition != 1:
        return None
    if scenario["case_kind"] == "happy" and happy_seed_dir:
        return happy_seed_dir / "responses" / f"{scenario['agent_id']}.json"
    if scenario["case_kind"] == "adversarial" and adversarial_seed_dir:
        return (
            adversarial_seed_dir
            / "responses"
            / f"{scenario['agent_id']}__{scenario['case_id']}.json"
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("ICODER_BACKEND", "http://127.0.0.1:8000"))
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--happy-seed-dir", type=Path)
    parser.add_argument("--adversarial-seed-dir", type=Path)
    parser.add_argument("--agent-ids", default="")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=150.0)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--max-p95-seconds", type=float, default=0.0)
    parser.add_argument(
        "--agent-p95-budget",
        action="append",
        default=[],
        metavar="AGENT_ID=SECONDS",
        help="Repeatable development P95 budget for selected high-latency agents.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--allow-self-register",
        action="store_true",
        help="Create a random tenant principal; use only with an isolated development database.",
    )
    args = parser.parse_args()

    if args.repetitions < 2:
        parser.error("--repetitions must be at least 2")
    if not 0 <= args.min_pass_rate <= 1:
        parser.error("--min-pass-rate must be between 0 and 1")
    agent_p95_budgets: dict[str, float] = {}
    for item in args.agent_p95_budget:
        agent_id, separator, raw_seconds = str(item).partition("=")
        try:
            seconds = float(raw_seconds)
        except (TypeError, ValueError):
            seconds = 0.0
        if (
            not separator
            or not agent_id.strip()
            or not math.isfinite(seconds)
            or seconds <= 0
        ):
            parser.error(
                "--agent-p95-budget must use AGENT_ID=positive-seconds"
            )
        agent_p95_budgets[agent_id.strip()] = seconds
    _assert_native_stacks_not_loaded()
    selected = {item.strip() for item in args.agent_ids.split(",") if item.strip()}
    scenarios = _load_scenarios(args.agents_dir, args.cases, selected or None)
    if not scenarios:
        raise RuntimeError("no visible Agent scenarios selected")
    expected = len(scenarios) * args.repetitions
    args.out_dir.mkdir(parents=True, exist_ok=True)
    response_dir = args.out_dir / "responses"
    response_dir.mkdir(exist_ok=True)
    trace_dir = args.out_dir / "traces"
    trace_dir.mkdir(exist_ok=True)
    rows: list[dict[str, Any]] = []
    headers: dict[str, str] | None = None
    run_index = 0
    session_started_at = utc_now_iso()
    agent_snapshot = pack_snapshot([
        scenario["pack"]
        for scenario in scenarios
        if scenario["case_kind"] == "happy"
    ])
    seed_sources: dict[str, dict[str, str]] = {}
    for label, directory, filename in (
        ("happy", args.happy_seed_dir, "agent_hub_examples_e2e.json"),
        ("adversarial", args.adversarial_seed_dir, "agent_hub_adversarial_e2e.json"),
    ):
        if directory is not None:
            report_path = (directory / filename).resolve()
            seed_sources[label] = {
                "report_path": str(report_path),
                "report_sha256": sha256_file(report_path) if report_path.is_file() else "",
            }

    for scenario in scenarios:
        for repetition in range(1, args.repetitions + 1):
            run_index += 1
            _assert_native_stacks_not_loaded()
            response_path = response_dir / _response_name(scenario, repetition)
            trace_evidence: dict[str, Any] | None = None
            run_started_at = utc_now_iso()
            seed_path = _seed_path(
                scenario,
                repetition,
                args.happy_seed_dir,
                args.adversarial_seed_dir,
            )
            if response_path.exists() and not args.force:
                response = json.loads(response_path.read_text(encoding="utf-8"))
                action = "resume"
            elif seed_path and seed_path.exists() and not args.force:
                response = json.loads(seed_path.read_text(encoding="utf-8"))
                response_path.write_text(
                    json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                action = "seed"
            else:
                if headers is None:
                    token = _login(
                        args.base_url.rstrip("/"),
                        allow_self_register=args.allow_self_register,
                    )
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                started = time.perf_counter()
                try:
                    raw = requests.post(
                        f"{args.base_url.rstrip('/')}/api/v1/agents/{scenario['agent_id']}/run",
                        headers=headers,
                        json={
                            "input": {
                                "text": scenario["input_text"],
                                "extra": scenario["extra"],
                            },
                            "include_trace": True,
                            "include_evidence": True,
                        },
                        timeout=args.timeout,
                    )
                    try:
                        response = raw.json()
                    except ValueError:
                        response = {
                            "error": True,
                            "error_reason": "non_json_response",
                            "body": raw.text[:1000],
                        }
                    response["_http_status"] = raw.status_code
                except requests.RequestException as exc:
                    response = {
                        "_http_status": 0,
                        "error": True,
                        "error_reason": type(exc).__name__,
                    }
                response["_elapsed_seconds"] = round(
                    time.perf_counter() - started, 3
                )
                response_path.write_text(
                    json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                action = "run"
                trace_evidence = capture_trace_artifact(
                    base_url=args.base_url,
                    headers=headers,
                    response=response,
                    trace_path=trace_dir / _response_name(scenario, repetition),
                    timeout=args.timeout,
                )

            evaluation = _evaluate_scenario(scenario, response)
            run_completed_at = utc_now_iso()
            row = {
                "agent_id": scenario["agent_id"],
                "case_kind": scenario["case_kind"],
                "case_id": scenario["case_id"],
                "repetition": repetition,
                "http_status": response.get("_http_status", 0),
                "elapsed_seconds": response.get("_elapsed_seconds", 0),
                "evaluation": evaluation,
                "response_path": str(response_path.resolve()),
                "execution_evidence": row_execution_evidence(
                    action=action,
                    response=response,
                    response_path=response_path,
                    pack=scenario["pack"],
                    trace_evidence=trace_evidence,
                    started_at=run_started_at,
                    completed_at=run_completed_at,
                ),
                **_extract_cost(response),
            }
            rows.append(row)
            summary = _build_summary(
                rows,
                expected=expected,
                repetitions=args.repetitions,
                min_pass_rate=args.min_pass_rate,
                max_p95_seconds=args.max_p95_seconds,
                agent_p95_budgets=agent_p95_budgets,
                base_url=args.base_url,
                session_started_at=session_started_at,
                agent_snapshot=agent_snapshot,
                seed_sources=seed_sources,
            )
            _write_summary(args.out_dir, summary)
            print(
                f"[{run_index:03d}/{expected}] {scenario['agent_id']}/"
                f"{scenario['case_kind']}/r{repetition}: "
                f"{'PASS' if _row_passed(evaluation) else 'FAIL'} ({action})",
                flush=True,
            )
            if run_index < expected and args.delay > 0:
                time.sleep(args.delay)

    gates = summary["gates"] if rows else {}
    return 0 if gates and all(gates.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
