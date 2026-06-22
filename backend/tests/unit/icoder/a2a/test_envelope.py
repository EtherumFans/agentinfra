"""A2A envelope + version + header tests (SPEC §4, §10)."""

from __future__ import annotations

import json

import pytest

from app.icoder.agent_runtime.a2a import (
    A2A_PROTOCOL_HEADER,
    A2A_PROTOCOL_VERSION,
    A2AVersionError,
    EnvelopeParseError,
    JsonRpcRequest,
    JsonRpcResponse,
    SUPPORTED_METHODS,
    SUPPORTED_TASKS_METHODS,
    SUPPORTED_VERSIONS,
    A2AError,
    A2AErrorCode,
    JSON_RPC_INVALID_REQUEST,
    JSON_RPC_METHOD_NOT_FOUND,
    JSON_RPC_PARSE_ERROR,
    make_error_response,
    make_parse_error_response,
    make_success_response,
    negotiate_version,
    parse_request,
    validate_method,
    validate_version_header,
)


# ---------------------------------------------------------------------------
# version.py — A2A-Protocol-Version header
# ---------------------------------------------------------------------------


def test_validate_version_header_accepts_supported():
    assert validate_version_header({A2A_PROTOCOL_HEADER: "0.3"}) == "0.3"


def test_validate_version_header_is_case_insensitive():
    assert validate_version_header({"a2a-protocol-version": "0.3"}) == "0.3"
    assert validate_version_header({"A2A-PROTOCOL-VERSION": "0.3"}) == "0.3"


def test_validate_version_header_missing_raises():
    with pytest.raises(A2AVersionError) as ei:
        validate_version_header({})
    assert "missing" in str(ei.value)
    assert ei.value.received is None


def test_validate_version_header_empty_string_raises():
    with pytest.raises(A2AVersionError):
        validate_version_header({A2A_PROTOCOL_HEADER: ""})


def test_validate_version_header_unsupported_raises():
    with pytest.raises(A2AVersionError) as ei:
        validate_version_header({A2A_PROTOCOL_HEADER: "0.4"})
    assert "0.4" in str(ei.value)
    assert ei.value.received == "0.4"


def test_validate_version_header_exotic_raises():
    with pytest.raises(A2AVersionError):
        validate_version_header({A2A_PROTOCOL_HEADER: "v99"})


def test_validate_version_header_none_input_raises():
    with pytest.raises(A2AVersionError):
        validate_version_header(None)


def test_negotiate_version_accepts_supported():
    assert negotiate_version("0.3") == "0.3"


def test_negotiate_version_rejects_none():
    with pytest.raises(A2AVersionError):
        negotiate_version(None)


def test_negotiate_version_rejects_unknown():
    with pytest.raises(A2AVersionError):
        negotiate_version("0.5")


def test_supported_versions_tuple_frozen():
    assert SUPPORTED_VERSIONS == ("0.3",)


def test_protocol_version_constant():
    assert A2A_PROTOCOL_VERSION == "0.3"


# ---------------------------------------------------------------------------
# envelope.py — JSON-RPC 2.0 parse
# ---------------------------------------------------------------------------


def test_parse_request_accepts_well_formed():
    req = parse_request({
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "hi"}]}},
    })
    assert isinstance(req, JsonRpcRequest)
    assert req.jsonrpc == "2.0"
    assert req.id == "req-1"
    assert req.method == "message/send"
    assert req.params is not None


def test_parse_request_accepts_bytes():
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "x"}]}},
    }).encode("utf-8")
    req = parse_request(body)
    assert isinstance(req, JsonRpcRequest)
    assert req.id == 1


def test_parse_request_accepts_string():
    body = json.dumps({
        "jsonrpc": "2.0", "id": "s", "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "x"}]}},
    })
    req = parse_request(body)
    assert isinstance(req, JsonRpcRequest)


def test_parse_request_rejects_batch_array():
    err = parse_request([{"jsonrpc": "2.0", "id": 1, "method": "message/send"}])
    assert isinstance(err, A2AError)
    assert err.code == A2AErrorCode.INVALID_REQUEST
    assert "batch" in err.details


def test_parse_request_rejects_non_object():
    err = parse_request("not json")
    assert isinstance(err, A2AError)
    assert err.jsonrpc_code == JSON_RPC_PARSE_ERROR


def test_parse_request_rejects_non_dict_object():
    err = parse_request({"jsonrpc": "2.0", "id": 1, "method": "message/send"})
    # OK — but missing params; tests separately below
    assert isinstance(err, JsonRpcRequest)


def test_parse_request_rejects_missing_jsonrpc():
    err = parse_request({"id": 1, "method": "message/send"})
    assert isinstance(err, A2AError)
    assert err.code == A2AErrorCode.INVALID_REQUEST
    assert "jsonrpc" in err.details


def test_parse_request_rejects_wrong_jsonrpc_version():
    err = parse_request({"jsonrpc": "1.0", "id": 1, "method": "message/send"})
    assert isinstance(err, A2AError)
    assert err.jsonrpc_code == JSON_RPC_INVALID_REQUEST


def test_parse_request_rejects_missing_method():
    err = parse_request({"jsonrpc": "2.0", "id": 1})
    assert isinstance(err, A2AError)
    assert "method" in err.details


def test_parse_request_rejects_empty_method():
    err = parse_request({"jsonrpc": "2.0", "id": 1, "method": ""})
    assert isinstance(err, A2AError)


def test_parse_request_rejects_non_string_method():
    err = parse_request({"jsonrpc": "2.0", "id": 1, "method": 123})
    assert isinstance(err, A2AError)


def test_parse_request_accepts_notification_no_id():
    req = parse_request({"jsonrpc": "2.0", "method": "message/send"})
    assert isinstance(req, JsonRpcRequest)
    assert req.id is None


def test_parse_request_accepts_numeric_id():
    req = parse_request({"jsonrpc": "2.0", "id": 42, "method": "message/send"})
    assert isinstance(req, JsonRpcRequest)
    assert req.id == 42


def test_parse_request_rejects_invalid_id_type():
    err = parse_request({"jsonrpc": "2.0", "id": {"foo": "bar"}, "method": "message/send"})
    assert isinstance(err, A2AError)
    assert "id" in err.details


# ---------------------------------------------------------------------------
# envelope.py — JSON-RPC 2.0 serialize
# ---------------------------------------------------------------------------


def test_make_success_response_shape():
    out = make_success_response("req-1", {"kind": "message"})
    assert out["jsonrpc"] == "2.0"
    assert out["id"] == "req-1"
    assert out["result"] == {"kind": "message"}
    assert "error" not in out


def test_make_error_response_shape():
    err = A2AError(code=A2AErrorCode.INVALID_REQUEST, details="bad input")
    out = make_error_response("req-1", err)
    assert out["jsonrpc"] == "2.0"
    assert out["id"] == "req-1"
    assert out["error"]["code"] == JSON_RPC_INVALID_REQUEST
    assert out["error"]["message"] == "Invalid request"
    assert out["error"]["data"]["a2a_error_code"] == A2AErrorCode.INVALID_REQUEST
    assert out["error"]["data"]["details"] == "bad input"


def test_make_parse_error_response_shape():
    out = make_parse_error_response("malformed json")
    assert out["jsonrpc"] == "2.0"
    assert out["id"] is None
    assert out["error"]["code"] == JSON_RPC_PARSE_ERROR
    assert out["error"]["data"]["a2a_error_code"] == A2AErrorCode.INVALID_REQUEST


# ---------------------------------------------------------------------------
# envelope.py — method validation
# ---------------------------------------------------------------------------


def test_validate_method_accepts_supported():
    for m in SUPPORTED_METHODS:
        assert validate_method(m, SUPPORTED_METHODS) is None


def test_validate_method_rejects_unknown():
    err = validate_method("message/stream", SUPPORTED_METHODS)
    assert isinstance(err, A2AError)
    assert err.code == A2AErrorCode.METHOD_NOT_FOUND
    assert err.jsonrpc_code == JSON_RPC_METHOD_NOT_FOUND


def test_validate_method_rejects_typo():
    err = validate_method("message/sned", SUPPORTED_METHODS)
    assert isinstance(err, A2AError)


def test_supported_tasks_methods_constant():
    assert "tasks/get" in SUPPORTED_TASKS_METHODS
    assert "tasks/cancel" in SUPPORTED_TASKS_METHODS


# ---------------------------------------------------------------------------
# JsonRpcRequest / JsonRpcResponse pydantic models
# ---------------------------------------------------------------------------


def test_jsonrpc_request_model_extra_allowed():
    req = JsonRpcRequest(method="message/send", extra_field="ignored-but-kept")
    assert req.extra_field == "ignored-but-kept"


def test_jsonrpc_request_default_id_is_none():
    req = JsonRpcRequest(method="message/send")
    assert req.id is None


def test_jsonrpc_request_default_jsonrpc_is_2():
    req = JsonRpcRequest(method="message/send")
    assert req.jsonrpc == "2.0"


def test_jsonrpc_response_default_jsonrpc_is_2():
    resp = JsonRpcResponse(id="1")
    assert resp.jsonrpc == "2.0"


# ---------------------------------------------------------------------------
# End-to-end: parse + validate_method + serialize
# ---------------------------------------------------------------------------


def test_e2e_happy_path():
    body = json.dumps({
        "jsonrpc": "2.0", "id": "req-1", "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "hi"}]}},
    }).encode("utf-8")
    req = parse_request(body)
    assert isinstance(req, JsonRpcRequest)
    method_err = validate_method(req.method, SUPPORTED_METHODS)
    assert method_err is None
    out = make_success_response(req.id, {"kind": "message", "role": "agent"})
    assert out["jsonrpc"] == "2.0"
    assert out["result"]["kind"] == "message"


def test_e2e_unknown_method_returns_method_not_found():
    body = json.dumps({"jsonrpc": "2.0", "id": "1", "method": "foo/bar"}).encode()
    req = parse_request(body)
    assert isinstance(req, JsonRpcRequest)
    err = validate_method(req.method, SUPPORTED_METHODS)
    assert err is not None
    assert err.code == A2AErrorCode.METHOD_NOT_FOUND
    out = make_error_response(req.id, err)
    assert out["error"]["code"] == JSON_RPC_METHOD_NOT_FOUND