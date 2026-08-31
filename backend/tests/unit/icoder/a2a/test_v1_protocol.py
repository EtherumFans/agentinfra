"""A2A v1.0 breaking-shape and fail-closed protocol contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.icoder.agent_runtime.a2a.v1.protocol import (
    A2AV1ProtocolError,
    CanonicalMessage,
    decode_task_cursor,
    encode_task_cursor,
    parse_v1_jsonrpc,
    parse_v1_message,
    project_v0_3_message,
    project_v0_3_task,
    task_row_to_v1,
    validate_v1_version,
)


def test_v1_version_is_separate_and_strict() -> None:
    assert validate_v1_version({"A2A-Version": "1.0"}) == "1.0"
    assert validate_v1_version({"a2a-version": "1.0"}) == "1.0"
    for headers in ({}, {"A2A-Version": ""}, {"A2A-Version": "0.3"}, {"A2A-Version": "1.1"}):
        with pytest.raises(A2AV1ProtocolError) as captured:
            validate_v1_version(headers)
        assert captured.value.reason == "VERSION_NOT_SUPPORTED"
        assert captured.value.jsonrpc_code == -32009


def test_v1_jsonrpc_uses_pascal_case_methods() -> None:
    request_id, method, params = parse_v1_jsonrpc(
        b'{"jsonrpc":"2.0","id":"r1","method":"GetTask","params":{"id":"t1"}}'
    )
    assert (request_id, method, params["id"]) == ("r1", "GetTask", "t1")
    with pytest.raises(A2AV1ProtocolError) as captured:
        parse_v1_jsonrpc(b'{"jsonrpc":"2.0","id":"r1","method":"tasks/get"}')
    assert captured.value.reason == "METHOD_NOT_FOUND"


def test_v1_message_parses_to_protocol_neutral_canonical_shape() -> None:
    canonical, configuration = parse_v1_message({
        "message": {
            "messageId": "m1",
            "contextId": "",
            "role": "ROLE_USER",
            "parts": [
                {"text": "de-identified note", "mediaType": "text/plain"},
                {"data": {"codeSystem": "ICD-10-CN"}, "metadata": {"schema": "icoder/Test/v1"}},
            ],
            "metadata": {"source": "test"},
        },
        "configuration": {"acceptedOutputModes": ["application/json"]},
    })
    assert isinstance(canonical, CanonicalMessage)
    assert canonical.role == "user"
    assert canonical.parts[0].kind == "text"
    assert canonical.parts[1].kind == "data"
    legacy = canonical.to_v0_3_params(configuration)
    assert legacy["message"]["parts"][1] == {
        "kind": "data",
        "data": {"schema": "icoder/Test/v1", "value": {"codeSystem": "ICD-10-CN"}},
    }


@pytest.mark.parametrize("part", [{"raw": "AA=="}, {"url": "https://example.invalid/file"}])
def test_v1_unsupported_part_fails_closed(part: dict) -> None:
    with pytest.raises(A2AV1ProtocolError) as captured:
        parse_v1_message({
            "message": {
                "messageId": "m1",
                "role": "ROLE_USER",
                "parts": [part],
            }
        })
    assert captured.value.reason == "CONTENT_TYPE_NOT_SUPPORTED"
    assert captured.value.jsonrpc_code == -32005


def test_v1_unknown_fields_fail_closed_and_async_config_is_supported() -> None:
    with pytest.raises(A2AV1ProtocolError) as unknown:
        parse_v1_message({
            "message": {
                "messageId": "m1",
                "role": "ROLE_USER",
                "parts": [{"text": "safe", "unexpected": True}],
            }
        })
    assert unknown.value.reason == "INVALID_PARAMS"

    canonical, configuration = parse_v1_message({
        "message": {
            "messageId": "m1",
            "role": "ROLE_USER",
            "parts": [{"text": "safe"}],
        },
        "configuration": {"returnImmediately": True},
    })
    assert canonical.message_id == "m1"
    assert configuration["returnImmediately"] is True

    with pytest.raises(A2AV1ProtocolError) as invalid_type:
        parse_v1_message({
            "message": {
                "messageId": "m1",
                "role": "ROLE_USER",
                "parts": [{"text": "safe"}],
            },
            "configuration": {"returnImmediately": "true"},
        })
    assert invalid_type.value.reason == "INVALID_PARAMS"


def test_v1_send_rejects_server_role_from_client() -> None:
    with pytest.raises(A2AV1ProtocolError) as captured:
        parse_v1_message({
            "message": {
                "messageId": "m1",
                "role": "ROLE_AGENT",
                "parts": [{"text": "safe"}],
            }
        })
    assert captured.value.reason == "INVALID_PARAMS"


def test_v0_3_response_projection_removes_kind_and_uses_proto_enums() -> None:
    message = project_v0_3_message({
        "kind": "message",
        "role": "agent",
        "messageId": "m2",
        "contextId": "c1",
        "parts": [{"kind": "text", "text": "done"}],
        "metadata": {},
    })
    assert "kind" not in message
    assert message["role"] == "ROLE_AGENT"
    assert message["parts"] == [{"text": "done", "mediaType": "text/plain"}]
    task = project_v0_3_task({
        "kind": "task",
        "id": "t1",
        "contextId": "c1",
        "status": {"state": "completed"},
    })
    assert "kind" not in task
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"


@pytest.mark.parametrize(
    ("legacy_state", "v1_state"),
    [
        ("input-required", "TASK_STATE_INPUT_REQUIRED"),
        ("auth-required", "TASK_STATE_AUTH_REQUIRED"),
        ("rejected", "TASK_STATE_REJECTED"),
    ],
)
def test_v1_projection_supports_interrupted_and_rejected_states(
    legacy_state: str, v1_state: str
) -> None:
    projected = project_v0_3_task({
        "kind": "task",
        "id": "t1",
        "contextId": "c1",
        "status": {"state": legacy_state},
    })
    assert projected["status"]["state"] == v1_state


def test_interrupted_task_projection_includes_prompt_but_no_artifact() -> None:
    row = SimpleNamespace(
        task_id="task-input",
        context_id="context-input",
        state="input-required",
        started_at=datetime(2026, 8, 23, 1, 0, tzinfo=timezone.utc),
        completed_at=None,
    )
    prompt = {
        "kind": "message",
        "role": "agent",
        "messageId": "prompt-1",
        "contextId": "context-input",
        "parts": [{"kind": "text", "text": "请确认主要诊断"}],
        "metadata": {},
    }
    projected = task_row_to_v1(row, result_message=prompt, artifacts=[])
    assert projected["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert projected["status"]["message"]["parts"][0]["text"] == "请确认主要诊断"
    assert projected["artifacts"] == []


def test_task_projection_preserves_event_timestamp_and_safe_failure_code() -> None:
    row = SimpleNamespace(
        task_id="task-1",
        context_id="context-1",
        state="failed",
        started_at=datetime(2026, 8, 22, 1, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 22, 1, 2, tzinfo=timezone.utc),
    )
    event_timestamp = datetime(2026, 8, 22, 1, 1, tzinfo=timezone.utc)
    projected = task_row_to_v1(
        row,
        state_override="working",
        status_timestamp=event_timestamp,
        error_code="CONNECTOR_GRAPH_FAILED",
    )
    assert projected["status"] == {
        "state": "TASK_STATE_WORKING",
        "timestamp": "2026-08-22T01:01:00Z",
    }
    assert projected["metadata"] == {"errorCode": "CONNECTOR_GRAPH_FAILED"}
    assert projected["artifacts"] == []


def test_task_cursor_is_signed_and_tamper_evident() -> None:
    token = encode_task_cursor({"v": 1, "o": "org1", "a": "agent1", "ts": "2026-08-21T00:00:00+00:00", "id": "t1"})
    assert decode_task_cursor(token)["id"] == "t1"
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(A2AV1ProtocolError) as captured:
        decode_task_cursor(tampered)
    assert captured.value.reason == "INVALID_PARAMS"

    # A 32-byte signature has a 43-character unpadded Base64URL form. The
    # final character contains two zero padding bits; permissive decoders map
    # three non-canonical aliases to the same bytes. Re-encoding must reject
    # those aliases even though the decoded signature still matches.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    encoded_body, encoded_signature = token.split(".", 1)
    final_index = alphabet.index(encoded_signature[-1])
    assert final_index % 4 == 0
    noncanonical = (
        f"{encoded_body}.{encoded_signature[:-1]}{alphabet[final_index + 1]}"
    )
    with pytest.raises(A2AV1ProtocolError) as noncanonical_error:
        decode_task_cursor(noncanonical)
    assert noncanonical_error.value.reason == "INVALID_PARAMS"


def test_v1_errors_use_proto_any_details() -> None:
    error = A2AV1ProtocolError("TASK_NOT_FOUND", metadata={"taskId": "hidden"})
    body = error.jsonrpc_body("r1")
    assert body["error"]["code"] == -32001
    detail = body["error"]["data"][0]
    assert detail["@type"] == "type.googleapis.com/google.rpc.ErrorInfo"
    assert detail["domain"] == "a2a-protocol.org"
    assert detail["reason"] == "TASK_NOT_FOUND"
