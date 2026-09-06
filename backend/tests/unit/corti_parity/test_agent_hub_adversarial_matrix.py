from __future__ import annotations

import importlib.util
import json
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND.parent
SCRIPT = BACKEND / "scripts" / "corti_parity" / "run_agent_hub_adversarial_e2e.py"
CASES = BACKEND / "scripts" / "corti_parity" / "agent_hub_adversarial_cases.json"
SPEC = importlib.util.spec_from_file_location("agent_hub_adversarial_e2e", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_adversarial_matrix_has_exactly_one_case_per_visible_agent() -> None:
    document = json.loads(CASES.read_text(encoding="utf-8"))
    cases = document["cases"]
    case_ids = [case["agent_id"] for case in cases]
    packs = MODULE._visible_packs(BACKEND / "official_agents")
    visible_ids = [MODULE._agent_id(pack) for pack in packs]

    assert len(cases) == len(visible_ids) == 26
    assert len(case_ids) == len(set(case_ids))
    assert set(case_ids) == set(visible_ids)
    assert all(case.get("assertions") for case in cases)


def test_semantic_assertion_operators_are_fail_closed() -> None:
    result = {"flag": True, "items": [], "score": 0.4, "note": "未提供"}
    assert MODULE._check_assertion(result, {"path": "flag", "op": "is_true"})["passed"]
    assert MODULE._check_assertion(result, {"path": "items", "op": "empty"})["passed"]
    assert MODULE._check_assertion(result, {"path": "score", "op": "number_lt", "value": 1})["passed"]
    assert MODULE._check_assertion(result, {"path": "note", "op": "contains_any", "value": ["未提供"]})["passed"]
    assert not MODULE._check_assertion(result, {"path": "missing", "op": "empty"})["passed"]


def test_adversarial_provider_failure_is_safe_but_not_semantic_pass() -> None:
    pack = {
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"human_review": "required"},
        "permissions": {"production_writeback_blocked": True},
        "output_contract": {
            "schema_ref": "test/v1",
            "required_fields": ["policy_unavailable"],
            "field_types": {"policy_unavailable": "boolean"},
            "field_schemas": {"policy_unavailable": {"type": "boolean"}},
        },
    }
    case = {
        "input_text": "未提供政策",
        "assertions": [{"path": "policy_unavailable", "op": "is_true"}],
    }
    response = {
        "_http_status": 200,
        "error": True,
        "error_reason": "provider_unavailable",
        "run_id": "run-safe-failure",
        "trace_id": "trace-safe-failure",
        "manual_review_required": True,
        "evidence": [],
        "result": {"contract_output_suppressed": True},
    }

    evaluation = MODULE._evaluate_case(pack, case, response)

    assert evaluation["semantic_capability_passed"] is False
    assert evaluation["safe_fail_closed"] is True
    assert evaluation["safety_passed"] is True
    assert evaluation["outcome"] == "safe_fail_closed"


def test_live_agent_hub_ci_is_credential_gated_and_failure_blocking() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "ci-integration.yml"
    ).read_text(encoding="utf-8")
    job = workflow.split("  agent-hub-live-e2e:", 1)[1].split("  ci-evidence:", 1)[0]

    assert "ICODER_CREDENTIAL_LLM" in job
    assert "DATABASE_URL: postgresql+asyncpg://" in job
    assert "ICODER_DATABASE_URL" not in job
    assert "needs: agent-hub-offline" in job
    assert "if: needs.agent-hub-offline.outputs.live_enabled == 'true'" in job
    assert "Record explicit live-E2E skip" not in job
    assert "run_agent_hub_examples_e2e.py" in job
    assert "run_agent_hub_adversarial_e2e.py" in job
    assert "run_agent_hub_stability_benchmark.py" in job
    assert "--repetitions 2" in job
    assert "--happy-seed-dir" in job
    assert "--adversarial-seed-dir" in job
    assert job.count("--allow-self-register") == 3
    assert "python -m alembic upgrade head" in job
    assert job.count("--force") >= 2
    assert "continue-on-error" not in job
    assert "if: always()" in job
