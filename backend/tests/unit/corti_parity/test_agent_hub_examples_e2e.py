from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "corti_parity" / "run_agent_hub_examples_e2e.py"
SPEC = importlib.util.spec_from_file_location("agent_hub_examples_e2e", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _clear_e2e_credentials(monkeypatch) -> None:
    for name in (
        "ICODER_E2E_BEARER",
        "ICODER_BEARER",
        "ICODER_E2E_USERNAME",
        "ICODER_E2E_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def test_login_prefers_environment_bearer_without_network(monkeypatch) -> None:
    _clear_e2e_credentials(monkeypatch)
    monkeypatch.setenv("ICODER_E2E_BEARER", "tenant-bound-token")
    monkeypatch.setattr(
        MODULE.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called")),
    )
    assert MODULE._login("http://127.0.0.1:8000") == "tenant-bound-token"


def test_login_uses_only_explicit_environment_credentials(monkeypatch) -> None:
    _clear_e2e_credentials(monkeypatch)
    monkeypatch.setenv("ICODER_E2E_USERNAME", "isolated-user")
    monkeypatch.setenv("ICODER_E2E_PASSWORD", "isolated-password")
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "explicit-token"}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(MODULE.requests, "post", post)
    assert MODULE._login("http://service") == "explicit-token"
    assert calls == [
        (
            "http://service/api/auth/login",
            {
                "json": {
                    "username": "isolated-user",
                    "password": "isolated-password",
                },
                "timeout": 15,
            },
        )
    ]


def test_login_rejects_partial_or_missing_credentials_without_network(monkeypatch) -> None:
    _clear_e2e_credentials(monkeypatch)
    monkeypatch.setenv("ICODER_E2E_USERNAME", "only-user")
    monkeypatch.setattr(
        MODULE.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called")),
    )
    with pytest.raises(RuntimeError, match="must be set together"):
        MODULE._login("http://service")

    monkeypatch.delenv("ICODER_E2E_USERNAME")
    with pytest.raises(RuntimeError, match="authentication is not configured"):
        MODULE._login("http://service")


def test_login_self_registers_only_when_explicitly_allowed(monkeypatch) -> None:
    _clear_e2e_credentials(monkeypatch)
    captured = {}

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"access_token": "registered-token"}

    def post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(MODULE.requests, "post", post)
    assert MODULE._login("http://127.0.0.1:8000", allow_self_register=True) == "registered-token"
    assert captured["url"] == "http://127.0.0.1:8000/api/auth/register"
    assert captured["json"]["username"].startswith("agent-e2e-")
    assert captured["json"]["email"].endswith("@example.com")
    assert len(captured["json"]["password"]) >= 32


def test_login_never_self_registers_against_a_non_loopback_service(monkeypatch) -> None:
    _clear_e2e_credentials(monkeypatch)
    monkeypatch.setattr(
        MODULE.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called")),
    )

    with pytest.raises(RuntimeError, match="restricted to a loopback"):
        MODULE._login("https://api.example.cn", allow_self_register=True)


def test_runner_source_contains_no_development_password_fallbacks() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Gate7!2026" not in source
    assert '"password": "admin"' not in source
    assert '"password": "admin123"' not in source


def test_content_safety_rejects_triage_specific_treatment() -> None:
    findings = MODULE._content_safety_findings(
        "triage",
        {"result": {"immediate_actions": ["立即给予阿司匹林并安排PCI"]}},
    )
    assert "unsupported_reperfusion" in findings


def test_content_safety_allows_triage_escalation_only() -> None:
    findings = MODULE._content_safety_findings(
        "triage",
        {"result": {"immediate_actions": ["进入抢救流程", "按医院批准路径处置"]}},
    )
    assert findings == []


def test_content_safety_rejects_completed_nursing_fact() -> None:
    findings = MODULE._content_safety_findings(
        "nursing-handoff",
        {"result": {"pending_tasks": ["腕带已核验"]}},
    )
    assert "invented_identity_check" in findings


def test_content_safety_allows_explicit_unknown_or_pending_facts() -> None:
    assert MODULE._content_safety_findings(
        "icu-summary",
        {"result": {"conflicts": ["不能推断为器官功能改善"]}},
    ) == []
    assert MODULE._content_safety_findings(
        "nursing-handoff",
        {"result": {"pending_tasks": ["管路通畅性待接班护士核验"]}},
    ) == []
    assert MODULE._content_safety_findings(
        "prior-auth",
        {"result": {"payer_requirements": "未提供支付方规则，无法确定具体材料要求"}},
    ) == []


def test_content_safety_rejects_invented_icu_interpretation_and_advice() -> None:
    findings = MODULE._content_safety_findings(
        "icu-summary",
        {
            "result": {
                "summary": "SOFA评分：8；乳酸偏高；建议调整剂量。",
            }
        },
    )

    assert {
        "invented_clinical_score",
        "invented_abnormality_interpretation",
        "invented_medication_advice",
    }.issubset(findings)


def test_evaluate_rejects_incomplete_and_tool_error() -> None:
    pack = {
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"human_review": "required"},
        "permissions": {"production_writeback_blocked": True},
        "output_contract": {"schema_ref": "test/v1", "required_fields": ["value"]},
    }
    response = {
        "_http_status": 200,
        "error": False,
        "run_id": "run-1",
        "trace_id": "trace-1",
        "manual_review_required": True,
        "result": {
            "value": [],
            "finish_state": "incomplete",
            "tool_calls": [{"tool_name": "search_icd", "error": "failed"}],
        },
    }

    evaluation = MODULE._evaluate(pack, response)
    assert evaluation["checks"]["provider_completed"] is False
    assert evaluation["checks"]["tool_calls_successful"] is False
    assert evaluation["passed"] is False


def test_evaluate_accepts_pack_declared_nested_cdi_human_review() -> None:
    pack = {
        "agent_ref": "icoder/clinical-documentation-improvement-agent@1.0.0",
        "manifest": {"human_review": "required"},
        "permissions": {"production_writeback_blocked": True},
        "output_contract": {
            "schema_ref": "icoder/CDIAgentOutputV1/test",
            "required_fields": ["human_review"],
            "field_types": {"human_review": "object"},
            "field_schemas": {
                "human_review": {
                    "type": "object",
                    "properties": {
                        "cdi_specialist_review_required": {"type": "boolean"},
                        "clinician_response_required": {"type": "boolean"},
                    },
                    "required": [
                        "cdi_specialist_review_required",
                        "clinician_response_required",
                    ],
                    "additionalProperties": False,
                }
            },
        },
        "example_inputs": [{"input_text": "去标识化合成病历"}],
    }
    response = {
        "_http_status": 200,
        "error": False,
        "run_id": "run-cdi-review",
        "trace_id": "trace-cdi-review",
        "manual_review_required": True,
        "result": {
            "human_review": {
                "cdi_specialist_review_required": True,
                "clinician_response_required": True,
            }
        },
    }

    evaluation = MODULE._evaluate(pack, response)

    assert evaluation["checks"]["manual_review_enforced"] is True
    assert evaluation["checks"]["manual_review_consistent"] is True
    assert evaluation["passed"] is True


def test_evaluate_separates_safe_fail_closed_from_capability_pass() -> None:
    pack = {
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"human_review": "required"},
        "permissions": {"production_writeback_blocked": True},
        "output_contract": {
            "schema_ref": "test/v1",
            "required_fields": ["decision"],
            "field_types": {"decision": "string"},
            "field_schemas": {"decision": {"type": "string"}},
        },
        "example_inputs": [{"input_text": "去标识输入"}],
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

    evaluation = MODULE._evaluate(pack, response)

    assert evaluation["passed"] is False
    assert evaluation["capability_passed"] is False
    assert evaluation["safe_fail_closed"] is True
    assert evaluation["outcome"] == "safe_fail_closed"


def test_safe_fail_closed_rejects_optimistic_domain_payload() -> None:
    checks = MODULE._safe_fail_closed_checks(
        {
            "_http_status": 200,
            "error": True,
            "error_reason": "schema_returned_error",
            "run_id": "run-unsafe-failure",
            "trace_id": "trace-unsafe-failure",
            "manual_review_required": True,
            "evidence": [],
            "result": {
                "contract_output_suppressed": True,
                "review_conclusion": "PASS",
            },
        },
        safety_findings=[],
        ungrounded_quantities=[],
    )

    assert checks["failure_metadata_only"] is False
    assert all(checks.values()) is False


def test_cached_summary_does_not_require_login(tmp_path, monkeypatch) -> None:
    native_modules_before = MODULE._loaded_native_stack_modules()
    agents = tmp_path / "agents" / "sample"
    agents.mkdir(parents=True)
    pack = {
        "agent_ref": "icoder/sample@1.0.0",
        "manifest": {"hidden_from_hub": False, "human_review": "required"},
        "permissions": {"production_writeback_blocked": True},
        "output_contract": {
            "schema_ref": "sample/v1",
            "required_fields": ["value"],
            "field_types": {"value": "array"},
            "field_schemas": {
                "value": {"type": "array", "items": {"type": "string"}},
            },
        },
        "example_inputs": [{"input_text": "test"}],
    }
    (agents / "agent_pack.json").write_text(__import__("json").dumps(pack), encoding="utf-8")
    out = tmp_path / "out"
    responses = out / "responses"
    responses.mkdir(parents=True)
    cached = {
        "_http_status": 200,
        "error": False,
        "run_id": "run-1",
        "trace_id": "trace-1",
        "manual_review_required": True,
        "result": {
            "value": [],
            "finish_state": "completed",
            "tool_calls": [],
            "manual_review_required": True,
            "structured_extraction": {
                "contract": "sample/v1",
                "valid": True,
                "missing_required_fields": [],
                "invalid_field_types": [],
                "invalid_field_schemas": [],
                "undeclared_output_fields": [],
            },
        },
    }
    (responses / "sample.json").write_text(__import__("json").dumps(cached), encoding="utf-8")
    monkeypatch.setattr(MODULE, "_login", lambda _url: (_ for _ in ()).throw(AssertionError("login called")))
    # This unit test may share a process with unrelated legacy tests that have
    # already imported Torch. Keep the production runner's strict clean-process
    # guard intact, while proving this cache-only path adds no native modules.
    monkeypatch.setattr(MODULE, "_assert_native_stacks_not_loaded", lambda: None)
    monkeypatch.setattr(
        __import__("sys"),
        "argv",
        ["runner", "--agents-dir", str(tmp_path / "agents"), "--out-dir", str(out), "--delay", "0"],
    )

    assert MODULE.main() == 0
    assert MODULE._loaded_native_stack_modules() == native_modules_before


def test_native_stack_guard_rejects_preloaded_native_module(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "pyarrow.icoder_guard_probe", object())
    with __import__("pytest").raises(RuntimeError, match="unsafe native modules already loaded"):
        MODULE._assert_native_stacks_not_loaded()


def test_evaluate_rejects_declared_field_type_violation() -> None:
    pack = {
        "agent_ref": "icoder/test@1.0.0",
        "manifest": {"human_review": "required"},
        "permissions": {"production_writeback_blocked": True},
        "output_contract": {"schema_ref": "test/v1", "required_fields": ["value"]},
    }
    response = {
        "_http_status": 200,
        "error": False,
        "run_id": "run-1",
        "trace_id": "trace-1",
        "manual_review_required": True,
        "result": {
            "value": [],
            "manual_review_required": True,
            "finish_state": "completed",
            "structured_extraction": {
                "contract": "test/v1",
                "valid": False,
                "missing_required_fields": [],
                "invalid_field_types": [
                    {"field": "value", "expected": "string", "actual": "array"}
                ],
                "invalid_field_schemas": [],
                "undeclared_output_fields": [],
            },
        },
    }

    evaluation = MODULE._evaluate(pack, response)
    assert evaluation["checks"]["structured_extraction_valid"] is False
    assert evaluation["checks"]["declared_field_types_valid"] is False
    assert evaluation["passed"] is False


def test_clinical_quantity_grounding_accepts_input_and_rejects_invention() -> None:
    pack = {
        "agent_ref": "icoder/triage@1.0.0",
        "output_contract": {"required_fields": ["red_flags", "actions"]},
        "example_inputs": [{"input_text": "血压88/56 mmHg，胸痛40分钟"}],
    }
    grounded = {
        "result": {
            "red_flags": ["血压88/56 mmHg", "胸痛40分钟"],
            "actions": ["立即评估"],
        }
    }
    invented = {
        "result": {
            "red_flags": ["血压88/56 mmHg"],
            "actions": ["30分钟后复查"],
        }
    }

    assert MODULE._ungrounded_clinical_quantities(pack, grounded) == []
    assert MODULE._ungrounded_clinical_quantities(pack, invented) == ["30分钟"]


def test_clinical_quantity_grounding_accepts_successful_tool_result() -> None:
    pack = {
        "agent_ref": "icoder/test@1.0.0",
        "output_contract": {"required_fields": ["summary"]},
        "example_inputs": [{"input_text": "病例"}],
    }
    response = {
        "result": {
            "summary": "目录结果置信度95%",
            "tool_calls": [{"tool_name": "lookup", "error": None, "result": {"score": "95%"}}],
        }
    }

    assert MODULE._ungrounded_clinical_quantities(pack, response) == []


def test_clinical_quantity_grounding_accepts_timestamp_arithmetic() -> None:
    pack = {
        "agent_ref": "icoder/clinical-guidelines@1.0.0",
        "output_contract": {"required_fields": ["criteria_checked", "deviations"]},
        "example_inputs": [{
            "input_text": (
                "要求入院24小时内完成。患者8月1日10:00入院，"
                "8月2日16:00完成评估。"
            ),
        }],
    }
    response = {
        "result": {
            "criteria_checked": ["间隔30小时"],
            "deviations": ["超过时限6小时"],
        }
    }

    assert MODULE._ungrounded_clinical_quantities(pack, response) == []


def test_clinical_quantity_grounding_accepts_iso_timestamp_arithmetic() -> None:
    pack = {
        "agent_ref": "icoder/clinical-guidelines@1.1.0",
        "output_contract": {"required_fields": ["criteria_checked", "deviations"]},
        "example_inputs": [{
            "input_text": (
                "要求入院24小时内完成。入院时间=2026-08-01 10:00，"
                "完成时间=2026-08-02 16:00。"
            ),
        }],
    }
    response = {
        "result": {
            "criteria_checked": ["间隔30小时"],
            "deviations": ["超过时限6小时"],
        }
    }

    assert MODULE._ungrounded_clinical_quantities(pack, response) == []


def test_clinical_quantity_grounding_accepts_unit_propagation_in_range() -> None:
    pack = {
        "agent_ref": "icoder/icu-summary@1.0.0",
        "output_contract": {"required_fields": ["key_trends"]},
        "example_inputs": [{"input_text": "乳酸由4.2降至2.1mmol/L"}],
    }
    response = {
        "result": {
            "key_trends": [{"from": "4.2 mmol/L", "to": "2.1 mmol/L"}],
        }
    }

    assert MODULE._ungrounded_clinical_quantities(pack, response) == []


def test_clinical_quantity_grounding_still_rejects_unrelated_threshold() -> None:
    pack = {
        "agent_ref": "icoder/clinical-guidelines@1.0.0",
        "output_contract": {"required_fields": ["criteria_checked"]},
        "example_inputs": [{"input_text": "患者8月1日10:00入院，8月2日16:00完成评估。"}],
    }
    response = {"result": {"criteria_checked": ["应在12小时内完成"]}}

    assert MODULE._ungrounded_clinical_quantities(pack, response) == ["12小时"]
