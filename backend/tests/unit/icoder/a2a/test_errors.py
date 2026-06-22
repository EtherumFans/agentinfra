"""A2A Error code tests (SPEC §6).

8 A2A v0.3 business codes + 5 JSON-RPC 2.0 standard codes.

Each business code is tested for:
- Default message populated
- Default http_status populated
- Default jsonrpc_code populated
- Envelope serialization (code, message, data.a2a_error_code)
- spec_ref (when applicable)
"""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.a2a import (
    ALL_A2A_ERROR_CODES,
    A2AError,
    A2AErrorCode,
    JSON_RPC_INTERNAL_ERROR,
    JSON_RPC_INVALID_PARAMS,
    JSON_RPC_INVALID_REQUEST,
    JSON_RPC_METHOD_NOT_FOUND,
    JSON_RPC_PARSE_ERROR,
    agent_not_found,
    context_invalid,
    internal_error,
    invalid_params,
    invalid_request,
    method_not_found,
    phi_redaction_failed,
    production_writeback_blocked,
    task_not_cancelable,
    task_not_found,
    unsupported_operation,
)


# ---------------------------------------------------------------------------
# JSON-RPC standard codes
# ---------------------------------------------------------------------------


def test_jsonrpc_parse_error_constant():
    assert JSON_RPC_PARSE_ERROR == -32700


def test_jsonrpc_invalid_request_constant():
    assert JSON_RPC_INVALID_REQUEST == -32600


def test_jsonrpc_method_not_found_constant():
    assert JSON_RPC_METHOD_NOT_FOUND == -32601


def test_jsonrpc_invalid_params_constant():
    assert JSON_RPC_INVALID_PARAMS == -32602


def test_jsonrpc_internal_error_constant():
    assert JSON_RPC_INTERNAL_ERROR == -32603


# ---------------------------------------------------------------------------
# A2AError construction + defaults
# ---------------------------------------------------------------------------


def test_a2a_error_rejects_unknown_code():
    with pytest.raises(ValueError) as ei:
        A2AError(code="UNKNOWN_CODE")
    assert "UNKNOWN_CODE" in str(ei.value)


def test_a2a_error_known_code_populates_defaults():
    e = A2AError(code=A2AErrorCode.INVALID_REQUEST)
    assert e.message == "Invalid request"
    assert e.http_status == 400
    assert e.jsonrpc_code == JSON_RPC_INVALID_REQUEST


def test_a2a_error_custom_message_overrides_default():
    e = A2AError(code=A2AErrorCode.INVALID_REQUEST, message="custom")
    assert e.message == "custom"


def test_a2a_error_custom_http_status_overrides():
    e = A2AError(code=A2AErrorCode.INTERNAL_ERROR, http_status=503)
    assert e.http_status == 503


def test_a2a_error_custom_jsonrpc_code_overrides():
    e = A2AError(code=A2AErrorCode.INTERNAL_ERROR, jsonrpc_code=-32099)
    assert e.jsonrpc_code == -32099


def test_a2a_error_is_exception():
    # A2AError must be raisable so parse_part / parse_message can raise.
    e = A2AError(code=A2AErrorCode.INVALID_PARAMS)
    assert isinstance(e, Exception)


# ---------------------------------------------------------------------------
# All 8 business codes — default mapping
# ---------------------------------------------------------------------------


def _check_business_code(code: str, expected_http: int, expected_jsonrpc: int):
    e = A2AError(code=code)
    assert e.http_status == expected_http, f"{code} HTTP mismatch"
    assert e.jsonrpc_code == expected_jsonrpc, f"{code} JSONRPC mismatch"
    assert e.message != "", f"{code} missing default message"


def test_invalid_request_mapping():
    _check_business_code(A2AErrorCode.INVALID_REQUEST, 400, JSON_RPC_INVALID_REQUEST)


def test_method_not_found_mapping():
    _check_business_code(A2AErrorCode.METHOD_NOT_FOUND, 404, JSON_RPC_METHOD_NOT_FOUND)


def test_invalid_params_mapping():
    _check_business_code(A2AErrorCode.INVALID_PARAMS, 400, JSON_RPC_INVALID_PARAMS)


def test_internal_error_mapping():
    _check_business_code(A2AErrorCode.INTERNAL_ERROR, 500, JSON_RPC_INTERNAL_ERROR)


def test_agent_not_found_mapping():
    _check_business_code(A2AErrorCode.AGENT_NOT_FOUND, 404, JSON_RPC_METHOD_NOT_FOUND)


def test_context_invalid_mapping():
    _check_business_code(A2AErrorCode.CONTEXT_INVALID, 400, JSON_RPC_INVALID_REQUEST)


def test_task_not_found_mapping():
    _check_business_code(A2AErrorCode.TASK_NOT_FOUND, 404, JSON_RPC_METHOD_NOT_FOUND)


def test_task_not_cancelable_mapping():
    _check_business_code(A2AErrorCode.TASK_NOT_CANCELABLE, 409, JSON_RPC_INVALID_REQUEST)


def test_unsupported_operation_mapping():
    _check_business_code(
        A2AErrorCode.UNSUPPORTED_OPERATION, 501, JSON_RPC_METHOD_NOT_FOUND
    )


def test_phi_redaction_failed_mapping():
    _check_business_code(
        A2AErrorCode.PHI_REDACTION_FAILED, 500, JSON_RPC_INTERNAL_ERROR
    )


def test_production_writeback_blocked_mapping():
    _check_business_code(
        A2AErrorCode.PRODUCTION_WRITEBACK_BLOCKED, 403, JSON_RPC_INVALID_REQUEST
    )


def test_planning_failed_mapping():
    _check_business_code(
        A2AErrorCode.PLANNING_FAILED, 500, JSON_RPC_INTERNAL_ERROR
    )


def test_expert_failed_mapping():
    _check_business_code(
        A2AErrorCode.EXPERT_FAILED, 502, JSON_RPC_INTERNAL_ERROR
    )


def test_aggregation_failed_mapping():
    _check_business_code(
        A2AErrorCode.AGGREGATION_FAILED, 500, JSON_RPC_INTERNAL_ERROR
    )


# ---------------------------------------------------------------------------
# to_envelope_data / to_envelope_error
# ---------------------------------------------------------------------------


def test_to_envelope_data_minimum():
    e = A2AError(code=A2AErrorCode.INVALID_REQUEST)
    d = e.to_envelope_data()
    assert d == {"a2a_error_code": "INVALID_REQUEST"}


def test_to_envelope_data_with_details():
    e = A2AError(code=A2AErrorCode.INVALID_REQUEST, details="bad input")
    d = e.to_envelope_data()
    assert d == {"a2a_error_code": "INVALID_REQUEST", "details": "bad input"}


def test_to_envelope_data_with_spec_ref():
    e = A2AError(
        code=A2AErrorCode.METHOD_NOT_FOUND,
        spec_ref="https://a2a-protocol.org/v0.3/spec#methods",
    )
    d = e.to_envelope_data()
    assert "spec_ref" in d


def test_to_envelope_data_with_extra():
    e = A2AError(
        code=A2AErrorCode.AGENT_NOT_FOUND,
        details="ghost",
        extra={"agent_id": "ghost"},
    )
    d = e.to_envelope_data()
    assert d["agent_id"] == "ghost"
    assert d["a2a_error_code"] == "AGENT_NOT_FOUND"
    assert d["details"] == "ghost"


def test_to_envelope_error_full_shape():
    e = A2AError(code=A2AErrorCode.INVALID_PARAMS, details="bad")
    out = e.to_envelope_error()
    assert out == {
        "code": JSON_RPC_INVALID_PARAMS,
        "message": "Invalid params",
        "data": {"a2a_error_code": "INVALID_PARAMS", "details": "bad"},
    }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def test_invalid_request_factory():
    e = invalid_request(details="x")
    assert e.code == A2AErrorCode.INVALID_REQUEST
    assert e.details == "x"


def test_invalid_params_factory():
    e = invalid_params(details="y")
    assert e.code == A2AErrorCode.INVALID_PARAMS


def test_method_not_found_factory():
    e = method_not_found(method="message/foo")
    assert e.code == A2AErrorCode.METHOD_NOT_FOUND
    assert "message/foo" in e.details
    assert "spec_ref" in e.to_envelope_data()


def test_method_not_found_factory_no_method():
    e = method_not_found()
    assert e.code == A2AErrorCode.METHOD_NOT_FOUND
    assert e.details == ""


def test_internal_error_factory():
    e = internal_error(details="boom")
    assert e.code == A2AErrorCode.INTERNAL_ERROR
    assert e.details == "boom"


def test_agent_not_found_factory():
    e = agent_not_found(agent_id="ghost")
    assert e.code == A2AErrorCode.AGENT_NOT_FOUND
    assert "ghost" in e.details


def test_context_invalid_factory():
    e = context_invalid(details="expired")
    assert e.code == A2AErrorCode.CONTEXT_INVALID
    assert e.details == "expired"


def test_task_not_found_factory():
    e = task_not_found(task_id="t1")
    assert e.code == A2AErrorCode.TASK_NOT_FOUND
    assert "t1" in e.details


def test_task_not_cancelable_factory():
    e = task_not_cancelable(task_id="t2")
    assert e.code == A2AErrorCode.TASK_NOT_CANCELABLE
    assert "t2" in e.details


def test_unsupported_operation_factory_default_message():
    e = unsupported_operation()
    assert e.code == A2AErrorCode.UNSUPPORTED_OPERATION
    assert "Phase 1" in e.details


def test_unsupported_operation_factory_custom():
    e = unsupported_operation(details="SSE not implemented")
    assert e.details == "SSE not implemented"


def test_phi_redaction_failed_factory():
    e = phi_redaction_failed(details="regex error")
    assert e.code == A2AErrorCode.PHI_REDACTION_FAILED


def test_production_writeback_blocked_factory():
    e = production_writeback_blocked(details="writeback attempted")
    assert e.code == A2AErrorCode.PRODUCTION_WRITEBACK_BLOCKED


# ---------------------------------------------------------------------------
# All error codes enumerated
# ---------------------------------------------------------------------------


def test_all_a2a_error_codes_is_tuple():
    assert isinstance(ALL_A2A_ERROR_CODES, tuple)


def test_all_factory_codes_in_all_codes():
    """Every code covered by a factory must appear in ALL_A2A_ERROR_CODES."""
    for code in [
        A2AErrorCode.INVALID_REQUEST,
        A2AErrorCode.METHOD_NOT_FOUND,
        A2AErrorCode.INVALID_PARAMS,
        A2AErrorCode.INTERNAL_ERROR,
        A2AErrorCode.AGENT_NOT_FOUND,
        A2AErrorCode.CONTEXT_INVALID,
        A2AErrorCode.TASK_NOT_FOUND,
        A2AErrorCode.TASK_NOT_CANCELABLE,
        A2AErrorCode.UNSUPPORTED_OPERATION,
        A2AErrorCode.PHI_REDACTION_FAILED,
        A2AErrorCode.PRODUCTION_WRITEBACK_BLOCKED,
    ]:
        assert code in ALL_A2A_ERROR_CODES


def test_8_business_codes_plus_reserved():
    """8 codes listed in spec §6.2, plus 4 iCoDer extensions + 2 reserved."""
    # SPEC §6.2 lists 8 directly:
    spec_8 = {
        A2AErrorCode.INVALID_REQUEST,
        A2AErrorCode.METHOD_NOT_FOUND,
        A2AErrorCode.INVALID_PARAMS,
        A2AErrorCode.INTERNAL_ERROR,
        A2AErrorCode.AGENT_NOT_FOUND,
        A2AErrorCode.CONTEXT_INVALID,
        A2AErrorCode.TASK_NOT_FOUND,
        A2AErrorCode.TASK_NOT_CANCELABLE,
    }
    assert spec_8.issubset(set(ALL_A2A_ERROR_CODES))


# ---------------------------------------------------------------------------
# error re-raise round-trip
# ---------------------------------------------------------------------------


def test_a2a_error_can_be_raised_and_caught():
    with pytest.raises(A2AError) as ei:
        raise A2AError(code=A2AErrorCode.INVALID_REQUEST, details="boom")
    assert ei.value.code == A2AErrorCode.INVALID_REQUEST
    assert ei.value.details == "boom"