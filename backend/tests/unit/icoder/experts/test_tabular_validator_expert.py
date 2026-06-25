"""TabularValidatorExpert tests (~10 cases).

Covers:
  - Metadata (EXPERT_ID / EXPERT_NAME)
  - Shape: passed / issues / manual_review_required / rule_set / expert_id
  - Empty structured output → R001 critical issue (primary missing)
  - Valid output → passed=True
  - manual_review_required triggered by critical|high severity
  - Quality flags surface from engine
  - __call__ alias matches invoke_sync
  - JSON payload parsing in invoke_sync
  - Error translation on hard failure
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.icoder.agent_runtime.experts.tabular_validator_expert import (
    TabularValidatorExpert,
)
from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)
from compliance_services.rule_engine import RuleEngine, RuleIssue, RuleValidationResult


# ── Metadata ──


class TestMetadata:
    def test_expert_id(self):
        assert TabularValidatorExpert.EXPERT_ID == "tabular-validator"

    def test_expert_name(self):
        assert "Stage 5" in TabularValidatorExpert.EXPERT_NAME


# ── Helpers ──


def _issue(severity: str, rule_id: str, message: str = "msg", suggestion: str = "fix"):
    return RuleIssue(severity=severity, rule_id=rule_id, message=message, suggestion=suggestion)


def _mock_engine(issues=None, passed=True, quality=None, fired=None):
    engine = MagicMock(spec=RuleEngine)
    engine.validate.return_value = RuleValidationResult(
        passed=passed,
        rule_set="medical_coding",
        rules_fired=fired or [],
        issues=issues or [],
        quality_flags=quality or {},
        manual_review_required=any(
            i.severity in {"critical", "high"} for i in (issues or [])
        ),
    )
    return engine


def _empty_invocation(payload: dict | None = None) -> ExpertInvocation:
    return ExpertInvocation(
        expert_id="tabular-validator",
        subtask_input=json.dumps(payload) if payload is not None else "",
        context={},
        attempt=1,
    )


# ── Shape ──


class TestShape:
    @pytest.mark.asyncio
    async def test_returns_required_fields(self):
        engine = _mock_engine()
        exp = TabularValidatorExpert(rule_engine=engine)
        result = await exp.invoke_async({"primary_diagnosis": {"code": "I50.900"}})
        assert "passed" in result
        assert "issues" in result
        assert "manual_review_required" in result
        assert "rule_set" in result
        assert "expert_id" in result
        assert result["expert_id"] == "tabular-validator"
        assert result["rule_set"] == "medical_coding"

    def test_invoke_sync_returns_required_fields(self):
        engine = _mock_engine()
        exp = TabularValidatorExpert(rule_engine=engine)
        result = exp.invoke_sync(_empty_invocation({"primary_diagnosis": {"code": "I50.900"}}))
        assert "passed" in result
        assert result["rule_set"] == "medical_coding"

    def test_callable_equals_invoke_sync(self):
        engine = _mock_engine()
        exp = TabularValidatorExpert(rule_engine=engine)
        inv = _empty_invocation({})
        assert exp(inv) == exp.invoke_sync(inv)


# ── Rule mapping ──


class TestRuleMapping:
    @pytest.mark.asyncio
    async def test_critical_issue_triggers_manual_review(self):
        engine = _mock_engine(
            issues=[_issue("critical", "R001", "Primary missing", "Add code")],
            passed=False,
        )
        exp = TabularValidatorExpert(rule_engine=engine)
        result = await exp.invoke_async({})
        assert result["passed"] is False
        assert result["manual_review_required"] is True
        assert len(result["issues"]) == 1
        assert result["issues"][0]["severity"] == "critical"
        assert result["issues"][0]["code"] == "R001"

    @pytest.mark.asyncio
    async def test_high_issue_triggers_manual_review(self):
        engine = _mock_engine(
            issues=[_issue("high", "R002", "Bad format", "Use ICD-10")],
        )
        exp = TabularValidatorExpert(rule_engine=engine)
        result = await exp.invoke_async({})
        assert result["manual_review_required"] is True

    @pytest.mark.asyncio
    async def test_medium_issue_does_not_trigger_manual_review(self):
        engine = _mock_engine(
            issues=[_issue("medium", "R003", "Duplicate", "Remove dup")],
        )
        exp = TabularValidatorExpert(rule_engine=engine)
        result = await exp.invoke_async({})
        assert result["manual_review_required"] is False
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_valid_output_passes(self):
        engine = _mock_engine(passed=True, fired=["R001", "R002"], quality={
            "invalid_code_format": False,
            "duplicate_codes": False,
        })
        exp = TabularValidatorExpert(rule_engine=engine)
        result = await exp.invoke_async({"primary_diagnosis": {"code": "I50.900"}})
        assert result["passed"] is True
        assert result["issues"] == []
        assert result["fired_rules"] == ["R001", "R002"]
        assert result["quality_flags"]["duplicate_codes"] is False

    @pytest.mark.asyncio
    async def test_empty_structured_output_uses_engine(self):
        engine = _mock_engine(
            issues=[_issue("critical", "R001")],
            passed=False,
        )
        exp = TabularValidatorExpert(rule_engine=engine)
        result = await exp.invoke_async({})
        # Engine was called with empty dict
        engine.validate.assert_called_once()
        called_args = engine.validate.call_args
        assert called_args[0][0] == "medical_coding"
        assert called_args[0][1] == {}
        assert result["passed"] is False


# ── Engine call args ──


class TestEngineCall:
    @pytest.mark.asyncio
    async def test_ctx_overrides_rule_set(self):
        engine = _mock_engine()
        exp = TabularValidatorExpert(rule_engine=engine, rule_set="medical_coding")
        await exp.invoke_async({}, ctx={"rule_set": "drg_dip"})
        engine.validate.assert_called_once()
        called_args = engine.validate.call_args
        assert called_args[0][0] == "drg_dip"

    @pytest.mark.asyncio
    async def test_engine_called_with_structured_output(self):
        engine = _mock_engine()
        exp = TabularValidatorExpert(rule_engine=engine)
        output = {
            "primary_diagnosis": {"code": "I50.900", "name": "心衰"},
            "secondary_diagnoses": [],
            "procedures": [],
            "confidence": 0.85,
        }
        await exp.invoke_async(output)
        engine.validate.assert_called_once()
        called_args = engine.validate.call_args
        assert called_args[0][1] == output


# ── invoke_sync JSON parsing ──


class TestInvokeSyncJSON:
    def test_invalid_json_falls_back_to_empty(self):
        engine = _mock_engine(
            issues=[_issue("critical", "R001")],
            passed=False,
        )
        exp = TabularValidatorExpert(rule_engine=engine)
        inv = ExpertInvocation(
            expert_id="tabular-validator",
            subtask_input="not valid json {",
            context={},
            attempt=1,
        )
        result = exp.invoke_sync(inv)
        # Empty dict still goes through engine
        engine.validate.assert_called_once()
        assert result["passed"] is False
        assert result["manual_review_required"] is True


# ── Error handling ──


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_unexpected_error_translated(self):
        engine = MagicMock()
        engine.validate.side_effect = RuntimeError("engine crashed")
        exp = TabularValidatorExpert(rule_engine=engine)
        with pytest.raises(ExpertInvocationError) as exc_info:
            await exp.invoke_async({})
        assert "validation failed" in str(exc_info.value)
        assert exc_info.value.stage == "validating"