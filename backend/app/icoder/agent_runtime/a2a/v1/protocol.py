"""Normative A2A v1.0 wire adapters and protocol-safe cursor helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final, Literal

from app.config import settings


A2A_V1_HEADER: Final[str] = "A2A-Version"
A2A_V1_VERSION: Final[str] = "1.0"
SUPPORTED_V1_METHODS: Final[tuple[str, ...]] = (
    "SendMessage",
    "SendStreamingMessage",
    "GetTask",
    "ListTasks",
    "CancelTask",
    "SubscribeToTask",
)
MAX_V1_BODY_BYTES: Final[int] = 1024 * 1024
MAX_V1_PARTS: Final[int] = 64
MAX_CURSOR_BYTES: Final[int] = 2048


_ERRORS: Final[dict[str, tuple[int, int, str]]] = {
    "JSON_PARSE_ERROR": (-32700, 400, "Invalid JSON payload"),
    "INVALID_REQUEST": (-32600, 400, "Request payload validation error"),
    "METHOD_NOT_FOUND": (-32601, 404, "Method not found"),
    "INVALID_PARAMS": (-32602, 400, "Invalid parameters"),
    "INTERNAL": (-32603, 500, "Internal error"),
    "TASK_NOT_FOUND": (-32001, 404, "Task not found"),
    "TASK_NOT_CANCELABLE": (-32002, 400, "Task not cancelable"),
    "UNSUPPORTED_OPERATION": (-32004, 400, "Unsupported operation"),
    "CONTENT_TYPE_NOT_SUPPORTED": (-32005, 400, "Content type not supported"),
    "VERSION_NOT_SUPPORTED": (-32009, 400, "A2A version not supported"),
}


@dataclass(slots=True)
class A2AV1ProtocolError(Exception):
    """Binding-neutral v1 error projected to JSON-RPC or google.rpc.Status."""

    reason: str
    detail: str = ""
    field_name: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.reason not in _ERRORS:
            raise ValueError(f"unknown A2A v1 error reason: {self.reason}")
        Exception.__init__(self, self.detail or self.message)

    @property
    def jsonrpc_code(self) -> int:
        return _ERRORS[self.reason][0]

    @property
    def http_status(self) -> int:
        return _ERRORS[self.reason][1]

    @property
    def message(self) -> str:
        return _ERRORS[self.reason][2]

    def _details(self) -> list[dict[str, Any]]:
        if self.reason in {
            "TASK_NOT_FOUND",
            "TASK_NOT_CANCELABLE",
            "UNSUPPORTED_OPERATION",
            "CONTENT_TYPE_NOT_SUPPORTED",
            "VERSION_NOT_SUPPORTED",
        }:
            detail: dict[str, Any] = {
                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                "reason": self.reason,
                "domain": "a2a-protocol.org",
            }
            if self.metadata:
                detail["metadata"] = self.metadata
            return [detail]
        if self.field_name or self.detail:
            return [{
                "@type": "type.googleapis.com/google.rpc.BadRequest",
                "fieldViolations": [{
                    "field": self.field_name or "request",
                    "description": self.detail or self.message,
                }],
            }]
        return []

    def jsonrpc_body(self, request_id: str | int | None) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": self.jsonrpc_code,
                "message": self.message,
                "data": self._details(),
            },
        }

    def http_body(self) -> dict[str, Any]:
        statuses = {
            400: "INVALID_ARGUMENT",
            404: "NOT_FOUND",
            500: "INTERNAL",
        }
        return {"error": {
            "code": self.http_status,
            "status": statuses.get(self.http_status, "UNKNOWN"),
            "message": self.message,
            "details": self._details(),
        }}


@dataclass(frozen=True, slots=True)
class CanonicalPart:
    kind: Literal["text", "data"]
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    media_type: str = ""

    def to_v0_3(self) -> dict[str, Any]:
        if self.kind == "text":
            return {"kind": "text", "text": self.value}
        schema = str(self.metadata.get("schema") or "icoder/A2AV1Data/v1")
        return {
            "kind": "data",
            "data": {"schema": schema, "value": self.value},
        }


@dataclass(frozen=True, slots=True)
class CanonicalMessage:
    role: Literal["user", "agent"]
    message_id: str
    context_id: str
    task_id: str
    parts: tuple[CanonicalPart, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    extensions: tuple[str, ...] = ()
    reference_task_ids: tuple[str, ...] = ()

    def to_v0_3_params(self, configuration: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = dict(self.metadata)
        if self.extensions:
            metadata["a2a_v1_extensions"] = list(self.extensions)
        if self.reference_task_ids:
            metadata["a2a_v1_reference_task_ids"] = list(self.reference_task_ids)
        return {
            "message": {
                "role": self.role,
                "messageId": self.message_id,
                "contextId": self.context_id,
                "parts": [part.to_v0_3() for part in self.parts],
                "metadata": metadata,
            },
            "configuration": configuration or {},
        }


def validate_v1_version(headers: dict[str, str] | None) -> str:
    """Require v1 on the v1 interface.

    The v1 specification interprets a missing value as v0.3.  Because this
    interface does not implement v0.3 semantics, the interpreted value is
    rejected with VersionNotSupportedError rather than silently upgraded.
    """

    raw: str | None = None
    for key, value in (headers or {}).items():
        if key.lower() == A2A_V1_HEADER.lower():
            raw = value.strip()
            break
    interpreted = raw or "0.3"
    if interpreted != A2A_V1_VERSION:
        raise A2AV1ProtocolError(
            "VERSION_NOT_SUPPORTED",
            detail=f"requested A2A version {interpreted!r} is not supported by this interface",
            metadata={"requestedVersion": interpreted, "supportedVersion": A2A_V1_VERSION},
        )
    return interpreted


def parse_v1_jsonrpc(raw: bytes) -> tuple[str | int | None, str, dict[str, Any]]:
    if len(raw) > MAX_V1_BODY_BYTES:
        raise A2AV1ProtocolError("INVALID_REQUEST", "request body exceeds 1 MiB", "request")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A2AV1ProtocolError("JSON_PARSE_ERROR", str(exc), "request") from exc
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        raise A2AV1ProtocolError("INVALID_REQUEST", "jsonrpc must equal '2.0'", "jsonrpc")
    request_id = body.get("id")
    if request_id is not None and not isinstance(request_id, (str, int)):
        raise A2AV1ProtocolError("INVALID_REQUEST", "id must be a string, number, or null", "id")
    method = body.get("method")
    if not isinstance(method, str) or method not in SUPPORTED_V1_METHODS:
        raise A2AV1ProtocolError("METHOD_NOT_FOUND", f"unsupported method {method!r}", "method")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise A2AV1ProtocolError("INVALID_PARAMS", "params must be an object", "params")
    return request_id, method, params


def parse_v1_message(params: dict[str, Any]) -> tuple[CanonicalMessage, dict[str, Any]]:
    allowed_params = {"tenant", "message", "configuration", "metadata"}
    unknown_params = set(params) - allowed_params
    if unknown_params:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            f"unknown SendMessageRequest fields: {', '.join(sorted(unknown_params))}",
            "params",
        )
    tenant = params.get("tenant") or ""
    if not isinstance(tenant, str):
        raise A2AV1ProtocolError("INVALID_PARAMS", "tenant must be a string", "tenant")
    if tenant:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "this interface derives tenant scope from authenticated organization and does not declare an AgentInterface tenant",
            "tenant",
        )
    obj = params.get("message")
    if not isinstance(obj, dict):
        raise A2AV1ProtocolError("INVALID_PARAMS", "message is required", "message")
    allowed_message_fields = {
        "messageId", "contextId", "taskId", "role", "parts", "metadata",
        "extensions", "referenceTaskIds",
    }
    unknown_message_fields = set(obj) - allowed_message_fields
    if unknown_message_fields:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            f"unknown Message fields: {', '.join(sorted(unknown_message_fields))}",
            "message",
        )
    role_value = obj.get("role")
    role_map = {"ROLE_USER": "user"}
    if role_value not in role_map:
        raise A2AV1ProtocolError("INVALID_PARAMS", "SendMessage client role must be ROLE_USER", "message.role")
    message_id = obj.get("messageId")
    if not isinstance(message_id, str) or not message_id or len(message_id) > 128:
        raise A2AV1ProtocolError("INVALID_PARAMS", "messageId must be a non-empty string up to 128 characters", "message.messageId")
    context_id = obj.get("contextId") or ""
    task_id = obj.get("taskId") or ""
    if not isinstance(context_id, str) or not isinstance(task_id, str):
        raise A2AV1ProtocolError("INVALID_PARAMS", "contextId and taskId must be strings", "message")
    raw_parts = obj.get("parts")
    if not isinstance(raw_parts, list) or not 1 <= len(raw_parts) <= MAX_V1_PARTS:
        raise A2AV1ProtocolError("INVALID_PARAMS", f"parts must contain 1 to {MAX_V1_PARTS} entries", "message.parts")
    parts: list[CanonicalPart] = []
    for index, raw_part in enumerate(raw_parts):
        if not isinstance(raw_part, dict):
            raise A2AV1ProtocolError("INVALID_PARAMS", "part must be an object", f"message.parts[{index}]")
        allowed_part_fields = {"text", "data", "raw", "url", "metadata", "filename", "mediaType"}
        unknown_part_fields = set(raw_part) - allowed_part_fields
        if unknown_part_fields:
            raise A2AV1ProtocolError(
                "INVALID_PARAMS",
                f"unknown Part fields: {', '.join(sorted(unknown_part_fields))}",
                f"message.parts[{index}]",
            )
        content_fields = [key for key in ("text", "data", "raw", "url") if key in raw_part]
        if len(content_fields) != 1:
            raise A2AV1ProtocolError("INVALID_PARAMS", "part must contain exactly one content field", f"message.parts[{index}]")
        content = content_fields[0]
        metadata = raw_part.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise A2AV1ProtocolError("INVALID_PARAMS", "part metadata must be an object", f"message.parts[{index}].metadata")
        if content == "text":
            if not isinstance(raw_part[content], str):
                raise A2AV1ProtocolError("INVALID_PARAMS", "text must be a string", f"message.parts[{index}].text")
            parts.append(CanonicalPart("text", raw_part[content], metadata, str(raw_part.get("mediaType") or "text/plain")))
        elif content == "data":
            parts.append(CanonicalPart("data", raw_part[content], metadata, str(raw_part.get("mediaType") or "application/json")))
        else:
            raise A2AV1ProtocolError(
                "CONTENT_TYPE_NOT_SUPPORTED",
                f"{content} parts are not supported by this Agent interface",
                metadata={"contentField": content},
            )
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise A2AV1ProtocolError("INVALID_PARAMS", "message metadata must be an object", "message.metadata")
    request_metadata = params.get("metadata") or {}
    if not isinstance(request_metadata, dict):
        raise A2AV1ProtocolError("INVALID_PARAMS", "request metadata must be an object", "metadata")
    metadata = dict(metadata)
    if request_metadata:
        metadata["a2a_v1_request_metadata"] = request_metadata

    extensions = obj.get("extensions") or []
    reference_task_ids = obj.get("referenceTaskIds") or []
    if (
        not isinstance(extensions, list)
        or len(extensions) > 32
        or any(not isinstance(value, str) or not value or len(value) > 1024 for value in extensions)
    ):
        raise A2AV1ProtocolError("INVALID_PARAMS", "extensions must contain at most 32 non-empty URI strings", "message.extensions")
    if (
        not isinstance(reference_task_ids, list)
        or len(reference_task_ids) > 64
        or any(not isinstance(value, str) or not value or len(value) > 128 for value in reference_task_ids)
    ):
        raise A2AV1ProtocolError("INVALID_PARAMS", "referenceTaskIds must contain at most 64 task IDs", "message.referenceTaskIds")

    configuration = params.get("configuration") or {}
    if not isinstance(configuration, dict):
        raise A2AV1ProtocolError("INVALID_PARAMS", "configuration must be an object", "configuration")
    allowed_configuration = {
        "acceptedOutputModes", "taskPushNotificationConfig", "historyLength", "returnImmediately",
    }
    unknown_configuration = set(configuration) - allowed_configuration
    if unknown_configuration:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            f"unknown SendMessageConfiguration fields: {', '.join(sorted(unknown_configuration))}",
            "configuration",
        )
    output_modes = configuration.get("acceptedOutputModes") or []
    if not isinstance(output_modes, list) or any(not isinstance(value, str) or not value for value in output_modes):
        raise A2AV1ProtocolError("INVALID_PARAMS", "acceptedOutputModes must be an array of strings", "configuration.acceptedOutputModes")
    history_length = configuration.get("historyLength")
    if history_length is not None and (
        isinstance(history_length, bool)
        or not isinstance(history_length, int)
        or not 0 <= history_length <= 100
    ):
        raise A2AV1ProtocolError("INVALID_PARAMS", "historyLength must be between 0 and 100", "configuration.historyLength")
    return_immediately = configuration.get("returnImmediately", False)
    if not isinstance(return_immediately, bool):
        raise A2AV1ProtocolError("INVALID_PARAMS", "returnImmediately must be boolean", "configuration.returnImmediately")
    if configuration.get("taskPushNotificationConfig"):
        raise A2AV1ProtocolError(
            "UNSUPPORTED_OPERATION",
            "task push notification configuration is not supported by this Agent Card",
            metadata={"operation": "taskPushNotificationConfig"},
        )
    canonical = CanonicalMessage(
        role=role_map[role_value],
        message_id=message_id,
        context_id=context_id,
        task_id=task_id,
        parts=tuple(parts),
        metadata=metadata,
        extensions=tuple(extensions),
        reference_task_ids=tuple(reference_task_ids),
    )
    return canonical, configuration


def _project_part(part: dict[str, Any]) -> dict[str, Any]:
    kind = part.get("kind")
    if kind == "text":
        return {"text": str(part.get("text") or ""), "mediaType": "text/plain"}
    if kind == "data":
        data = part.get("data")
        if isinstance(data, dict) and "value" in data:
            projected: dict[str, Any] = {"data": data.get("value"), "mediaType": "application/json"}
            schema = data.get("schema")
            if isinstance(schema, str) and schema:
                projected["metadata"] = {"schema": schema}
            return projected
        return {"data": data, "mediaType": "application/json"}
    raise A2AV1ProtocolError("CONTENT_TYPE_NOT_SUPPORTED", f"cannot project legacy part kind {kind!r}")


def project_v0_3_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "messageId": str(message.get("messageId") or ""),
        "contextId": str(message.get("contextId") or ""),
        "role": "ROLE_AGENT" if message.get("role") == "agent" else "ROLE_USER",
        "parts": [_project_part(part) for part in message.get("parts") or [] if isinstance(part, dict)],
        "metadata": message.get("metadata") if isinstance(message.get("metadata"), dict) else {},
    }


_TASK_STATE_TO_V1: Final[dict[str, str]] = {
    "submitted": "TASK_STATE_SUBMITTED",
    "working": "TASK_STATE_WORKING",
    "completed": "TASK_STATE_COMPLETED",
    "failed": "TASK_STATE_FAILED",
    "canceled": "TASK_STATE_CANCELED",
    "rejected": "TASK_STATE_REJECTED",
    "input-required": "TASK_STATE_INPUT_REQUIRED",
    "auth-required": "TASK_STATE_AUTH_REQUIRED",
}
TASK_STATE_FROM_V1: Final[dict[str, str]] = {value: key for key, value in _TASK_STATE_TO_V1.items()}


def project_v0_3_task(task: dict[str, Any]) -> dict[str, Any]:
    status = task.get("status") if isinstance(task.get("status"), dict) else {}
    result: dict[str, Any] = {
        "id": str(task.get("id") or ""),
        "contextId": str(task.get("contextId") or ""),
        "status": {
            "state": _TASK_STATE_TO_V1.get(str(status.get("state") or ""), "TASK_STATE_UNSPECIFIED"),
        },
        "artifacts": task.get("artifacts") if isinstance(task.get("artifacts"), list) else [],
        "history": [project_v0_3_message(item) for item in (task.get("history") or []) if isinstance(item, dict)],
        "metadata": task.get("metadata") if isinstance(task.get("metadata"), dict) else {},
    }
    if status.get("timestamp"):
        result["status"]["timestamp"] = status["timestamp"]
    if isinstance(status.get("message"), dict):
        result["status"]["message"] = project_v0_3_message(status["message"])
    return result


def task_row_to_v1(
    row: Any,
    *,
    result_message: dict[str, Any] | None = None,
    include_artifacts: bool = True,
    state_override: str = "",
    status_timestamp: datetime | None = None,
    error_code: str = "",
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    timestamp = status_timestamp or row.completed_at or row.started_at
    if timestamp is not None and timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    state = state_override or row.state
    task: dict[str, Any] = {
        "id": row.task_id,
        "contextId": row.context_id,
        "status": {
            "state": state,
            "timestamp": timestamp.isoformat().replace("+00:00", "Z") if timestamp else None,
        },
        "artifacts": [],
        "history": [],
        "metadata": ({"errorCode": error_code} if error_code else {}),
    }
    if state in {"completed", "input-required", "auth-required"} and isinstance(
        result_message, dict
    ):
        task["status"]["message"] = result_message
        task["history"] = [result_message]
        if state == "completed" and include_artifacts:
            # ``None`` is the explicit compatibility signal for pre-050 rows.
            # New executions pass a durable list, including an empty list.
            task["artifacts"] = artifacts if artifacts is not None else [{
                "artifactId": f"{row.task_id}-result",
                "name": "Agent result",
                "description": "Compatibility projection for a pre-050 Task result",
                "parts": [
                    _project_part(part)
                    for part in (result_message.get("parts") or [])
                    if isinstance(part, dict)
                ],
                "metadata": {
                    "sourceMessageId": str(result_message.get("messageId") or ""),
                },
                "extensions": [],
            }]
    elif include_artifacts and artifacts:
        # A durable Artifact is still independently retrievable if legacy
        # result-message persistence is unavailable during migration.
        task["artifacts"] = artifacts
    return project_v0_3_task(task)


def _cursor_key() -> bytes:
    return hashlib.sha256((settings.SECRET_KEY + ":a2a-v1-task-cursor").encode("utf-8")).digest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def encode_task_cursor(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    signature = hmac.new(_cursor_key(), body, hashlib.sha256).digest()
    return f"{_b64encode(body)}.{_b64encode(signature)}"


def decode_task_cursor(token: str) -> dict[str, Any]:
    if not isinstance(token, str) or not token or len(token) > MAX_CURSOR_BYTES or token.count(".") != 1:
        raise A2AV1ProtocolError("INVALID_PARAMS", "pageToken is malformed", "pageToken")
    encoded_body, encoded_signature = token.split(".", 1)
    try:
        body = _b64decode(encoded_body)
        signature = _b64decode(encoded_signature)
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise A2AV1ProtocolError("INVALID_PARAMS", "pageToken is malformed", "pageToken") from exc
    expected = hmac.new(_cursor_key(), body, hashlib.sha256).digest()
    canonical = (
        _b64encode(body) == encoded_body
        and _b64encode(signature) == encoded_signature
    )
    if (
        not canonical
        or not hmac.compare_digest(signature, expected)
        or not isinstance(payload, dict)
    ):
        raise A2AV1ProtocolError("INVALID_PARAMS", "pageToken signature is invalid", "pageToken")
    if payload.get("v") != 1:
        raise A2AV1ProtocolError("INVALID_PARAMS", "pageToken version is unsupported", "pageToken")
    return payload


def parse_iso_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise A2AV1ProtocolError("INVALID_PARAMS", "timestamp must be ISO 8601", field_name) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


__all__ = [
    "A2A_V1_HEADER",
    "A2A_V1_VERSION",
    "A2AV1ProtocolError",
    "CanonicalMessage",
    "CanonicalPart",
    "MAX_V1_BODY_BYTES",
    "SUPPORTED_V1_METHODS",
    "TASK_STATE_FROM_V1",
    "decode_task_cursor",
    "encode_task_cursor",
    "parse_iso_timestamp",
    "parse_v1_jsonrpc",
    "parse_v1_message",
    "project_v0_3_message",
    "project_v0_3_task",
    "task_row_to_v1",
    "validate_v1_version",
]
