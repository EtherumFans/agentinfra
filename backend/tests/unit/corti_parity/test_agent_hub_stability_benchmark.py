from __future__ import annotations

import importlib.util
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[3]
SCRIPT = BACKEND / "scripts" / "corti_parity" / "run_agent_hub_stability_benchmark.py"
SPEC = importlib.util.spec_from_file_location("agent_hub_stability_benchmark", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _evaluation(passed: bool = True) -> dict:
    return {
        "passed": passed,
        "checks": {
            "provider_completed": passed,
            "required_fields_complete": passed,
            "structured_extraction_valid": passed,
            "content_safety": passed,
            "clinical_quantities_grounded": passed,
        },
    }


def _row(agent: str, kind: str, repetition: int, elapsed: float, passed: bool = True) -> dict:
    return {
        "agent_id": agent,
        "case_kind": kind,
        "case_id": "case-1",
        "repetition": repetition,
        "elapsed_seconds": elapsed,
        "evaluation": _evaluation(passed),
    }


def test_scenario_matrix_covers_two_cases_for_all_visible_agents() -> None:
    scenarios = MODULE._load_scenarios(
        BACKEND / "official_agents",
        BACKEND / "scripts" / "corti_parity" / "agent_hub_adversarial_cases.json",
    )
    assert len(scenarios) == 52
    assert {scenario["case_kind"] for scenario in scenarios} == {"happy", "adversarial"}
    assert len({scenario["agent_id"] for scenario in scenarios}) == 26


def test_nearest_rank_is_deterministic_for_small_samples() -> None:
    assert MODULE._nearest_rank([4.0, 1.0, 3.0, 2.0], 0.50) == 2.0
    assert MODULE._nearest_rank([4.0, 1.0, 3.0, 2.0], 0.95) == 4.0
    assert MODULE._nearest_rank([], 0.95) is None


def test_cost_extraction_distinguishes_explicit_zero_from_unknown() -> None:
    assert MODULE._extract_cost({"cost": {"amount": 0, "currency": "CNY"}}) == {
        "cost_known": True,
        "cost_amount": 0.0,
        "cost_currency": "CNY",
    }
    assert MODULE._extract_cost({"cost": {}})["cost_known"] is False
    assert MODULE._extract_cost({})["cost_known"] is False


def test_summary_reports_latency_error_and_repeatability() -> None:
    rows = [
        {**_row("agent-a", "happy", 1, 1.0), "cost_known": True, "cost_amount": 0.1, "cost_currency": "CNY"},
        {**_row("agent-a", "happy", 2, 2.0), "cost_known": True, "cost_amount": 0.2, "cost_currency": "CNY"},
        {**_row("agent-a", "adversarial", 1, 3.0), "case_id": "case-2", "cost_known": False},
        {**_row("agent-a", "adversarial", 2, 4.0), "case_id": "case-2", "cost_known": True, "cost_amount": 0.3, "cost_currency": "CNY"},
    ]
    summary = MODULE._build_summary(
        rows,
        expected=4,
        repetitions=2,
        min_pass_rate=1.0,
        max_p95_seconds=5.0,
    )
    assert summary["complete"] is True
    assert summary["pass_rate"] == 1.0
    assert summary["error_rate"] == 0.0
    assert summary["p50_seconds"] == 2.0
    assert summary["p95_seconds"] == 4.0
    assert summary["cost_coverage_rate"] == 0.75
    assert summary["cost_unknown_runs"] == 1
    assert summary["costs_by_currency"]["CNY"]["total"] == 0.6
    assert summary["per_agent"][0]["cost_coverage_rate"] == 0.75
    assert summary["per_agent"][0]["cost_totals"] == {"CNY": 0.6}
    assert all(summary["gates"].values())
    assert summary["per_agent"][0]["all_scenarios_repeatably_passed"] is True


def test_summary_fails_closed_on_partial_or_failed_run() -> None:
    rows = [
        _row("agent-a", "happy", 1, 1.0),
        _row("agent-a", "happy", 2, 2.0, passed=False),
    ]
    summary = MODULE._build_summary(
        rows,
        expected=4,
        repetitions=2,
        min_pass_rate=1.0,
        max_p95_seconds=1.5,
    )
    assert summary["quality_scope"] == "contract_safety_reliability_not_clinical_accuracy"
    assert summary["gates"] == {
        "complete": False,
        "pass_rate": False,
        "latency": False,
        "per_agent_latency": True,
        "all_passed": False,
    }
    assert summary["per_agent"][0]["all_scenarios_repeatably_passed"] is False


def test_single_complete_scenario_is_not_misreported_as_agent_stability() -> None:
    rows = [
        _row("agent-a", "happy", 1, 1.0),
        _row("agent-a", "happy", 2, 1.1),
    ]
    summary = MODULE._build_summary(
        rows,
        expected=4,
        repetitions=2,
        min_pass_rate=1.0,
        max_p95_seconds=0,
    )
    assert summary["per_agent"][0]["all_scenarios_repeatably_passed"] is False


def test_per_agent_p95_budget_fails_even_when_global_latency_gate_is_disabled() -> None:
    rows = [
        _row("clinical-documentation-improvement-agent", "happy", 1, 20.0),
        _row("clinical-documentation-improvement-agent", "happy", 2, 31.0),
        {
            **_row(
                "clinical-documentation-improvement-agent",
                "adversarial",
                1,
                22.0,
            ),
            "case_id": "case-2",
        },
        {
            **_row(
                "clinical-documentation-improvement-agent",
                "adversarial",
                2,
                28.0,
            ),
            "case_id": "case-2",
        },
    ]

    summary = MODULE._build_summary(
        rows,
        expected=4,
        repetitions=2,
        min_pass_rate=1.0,
        max_p95_seconds=0,
        agent_p95_budgets={
            "clinical-documentation-improvement-agent": 30.0,
        },
    )

    assert summary["gates"]["latency"] is True
    assert summary["gates"]["per_agent_latency"] is False
    assert summary["per_agent"][0]["p95_budget_seconds"] == 30.0
    assert summary["per_agent"][0]["latency_budget_passed"] is False
