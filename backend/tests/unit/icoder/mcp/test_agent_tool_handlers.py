"""Phase 3-D2 Task 3 — MCP agent tool handlers unit tests.

Verifies the 3 MCP handlers (validate_codes / evaluate_compliance /
check_documentation_gaps) wrap their corresponding agent.run() SSOT
correctly: invoke → return the agent's output dict.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest

from app.icoder.mcp.handlers.validate_codes import handle as _validate
from app.icoder.mcp.handlers.evaluate_compliance import handle as _compliance
from app.icoder.mcp.handlers.check_documentation_gaps import handle as _docs


def _fake_request(*, run_id: str = "test-run-1") -> SimpleNamespace:
    """Build a lightweight request-like object for handler tests."""
    state = SimpleNamespace()
    state.run_id = run_id
    state.context_id = "test-ctx-1"
    state.auth_header = None
    req = SimpleNamespace()
    req.state = state
    req.app = SimpleNamespace()
    req.app.state = SimpleNamespace()
    req.app.state.phi_redactor = None
    return req


def _coding_set_json() -> str:
    return json.dumps({
        "primary_diagnosis": {
            "code": "I50.9",
            "description": "心力衰竭",
            "confidence": 0.95,
            "category": "primary",
            "evidence": ["患者出现呼吸困难"],
        },
        "secondary_diagnoses": [],
        "procedures": [],
    })


# ── validate_codes ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_codes_handler_invokes_agent_run():
    """validate_codes handler builds input_text + calls agent_legacy.run_legacy().

    Phase 4-C: validate_codes now delegates to ``agent_legacy.run_legacy()``
    (the deterministic RuleEngine) to preserve the v1 output shape for
    existing MCP consumers. The new LLM-based ``agent.run()`` produces
    v2 shape and is invoked directly by the agent hub, not via the
    validate_codes MCP tool.
    """
    fake_result = {
        "review_conclusion": "PASS",
        "issues_found": [],
        "manual_review_required": False,
        "rule_set": "medical_coding",
        "fired_rules": ["R001", "MC-R-M80-001"],
    }
    async def _fake_run(input_text, *, run_id=""):
        # Verify the handler built input_text from coding_set + encounter_text
        assert "I50.9" in input_text
        assert run_id == "test-run-1"
        return fake_result

    with patch(
        "official_agents.code_validation.agent_legacy.run_legacy",
        new=_fake_run,
    ):
        result = await _validate(
            {"coding_set": json.loads(_coding_set_json()), "encounter_text": "胸痛"},
            _fake_request(),
        )
    assert result == fake_result
    assert result["review_conclusion"] == "PASS"


# ── evaluate_compliance ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_compliance_handler_invokes_agent_run():
    """evaluate_compliance handler builds input_text + calls agent.run()."""
    fake_result = {
        "risk_conclusion": "LOW_RISK",
        "drg_dip_sensitive_items": [],
        "compliance_checks": [],
        "risk_level": "low",
        "audit_advice": "",
    }
    async def _fake_run(input_text, *, run_id=""):
        assert "I50.9" in input_text
        assert run_id == "test-run-1"
        return fake_result

    with patch(
        "official_agents.compliance_guardrail.agent.run",
        new=_fake_run,
    ):
        result = await _compliance(
            {"coding_set": json.loads(_coding_set_json())},
            _fake_request(),
        )
    assert result == fake_result
    assert result["risk_conclusion"] == "LOW_RISK"


# ── check_documentation_gaps ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_documentation_gaps_handler_invokes_agent_run():
    """check_documentation_gaps handler passes encounter_text through."""
    fake_result = {
        "completeness_score": 0.65,
        "missing_sections": ["主诉", "查体"],
        "present_sections": ["现病史"],
        "supplement_suggestions": [],
    }
    async def _fake_run(input_text, *, run_id=""):
        assert "主诉胸痛" in input_text
        assert run_id == "test-run-1"
        return fake_result

    with patch(
        "official_agents.note_completeness.agent.run",
        new=_fake_run,
    ):
        result = await _docs(
            {"encounter_text": "主诉胸痛, 现病史..."},
            _fake_request(),
        )
    assert result == fake_result
    assert result["completeness_score"] == 0.65
