"""A2A Message + Task (SPEC §3 / §4.2 / §4.3).

**Message** is what short, blocking runs return. **Task** is for long-
running, async work and is persisted by the task state-machine routes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import A2AError, A2AErrorCode, invalid_params
from .parts import DataPart, TextPart, parse_parts


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class A2AMessage(BaseModel):
    """A2A v0.3 Message (SPEC §4.2).

    ``kind: "message"`` discriminates from Task in result envelopes.
    ``messageId`` is server-generated for responses. A first request omits
    ``contextId`` and the server creates it; later requests may reuse that
    server-issued ID after tenant/agent/lifecycle validation by the route.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["message"] = "message"
    role: str
    messageId: str
    contextId: str
    parts: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class A2ATaskStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: str
    message: dict[str, Any] | None = None
    timestamp: str | None = None


class A2ATask(BaseModel):
    """A2A v0.3 Task (SPEC §4.3).

    Synchronous message sends return Messages directly; persisted
    asynchronous task rows use this wire shape and the transitions in
    :mod:`.task_state`.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["task"] = "task"
    id: str
    contextId: str
    status: A2ATaskStatus
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Inbound parsing — strict spec validation
# ---------------------------------------------------------------------------


def parse_message(obj: Any) -> dict[str, Any]:
    """Validate an inbound ``params.message`` payload (SPEC §4.1).

    Returns a sanitized dict with:
    - ``role``: validated against {"user", "agent", "orchestrator"}
    - ``parts``: validated list of TextPart/DataPart dicts
    - ``messageId``: optional client-supplied; preserved if present
    - ``contextId``: optional server-issued continuation identifier
    - ``metadata``: passed through

    Raises :class:`A2AError` (INVALID_REQUEST / INVALID_PARAMS) on failure.
    """
    if not isinstance(obj, dict):
        raise _invalid("params.message must be a JSON object")

    role = obj.get("role")
    if role not in ("user", "agent", "orchestrator"):
        raise _invalid(
            f"message.role must be one of: user, agent, orchestrator; got {role!r}",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    parts_obj = obj.get("parts")
    try:
        parsed_parts = parse_parts(parts_obj)
    except A2AError:
        raise
    except Exception as e:
        raise _invalid(f"parts validation failed: {e}", a2a_code=A2AErrorCode.INVALID_PARAMS) from e

    # messageId: optional client-supplied; if present must be string
    message_id = obj.get("messageId")
    if message_id is not None and not isinstance(message_id, str):
        raise _invalid(
            "message.messageId must be a string",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    context_id = obj.get("contextId")
    if context_id is not None and not isinstance(context_id, str):
        raise _invalid(
            "message.contextId must be a string",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise _invalid(
            "message.metadata must be an object",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    return {
        "role": role,
        "parts": [p.model_dump() for p in parsed_parts],
        "messageId": message_id or "",
        "contextId": context_id or "",
        "metadata": metadata,
    }


def parse_params(params: Any) -> dict[str, Any]:
    """Validate the entire ``params`` block of a JSON-RPC request.

    Returns the parsed ``message`` dict plus the optional
    ``configuration`` block (passed through).
    """
    if params is None:
        raise _invalid("params is required for message/send")

    if not isinstance(params, dict):
        raise _invalid(
            f"params must be an object; got {type(params).__name__}",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    if "message" not in params:
        raise _invalid(
            "params.message is required",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    message = parse_message(params["message"])
    config = params.get("configuration") or {}
    if config and not isinstance(config, dict):
        raise _invalid(
            "params.configuration must be an object",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    return {"message": message, "configuration": config}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_message_envelope(
    *,
    role: str,
    message_id: str,
    context_id: str,
    parts: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an A2A Message dict suitable for the ``result`` of a response."""
    return {
        "kind": "message",
        "role": role,
        "messageId": message_id,
        "contextId": context_id,
        "parts": parts,
        "metadata": metadata or {},
    }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _invalid(details: str, a2a_code: str = A2AErrorCode.INVALID_REQUEST) -> A2AError:
    return A2AError(code=a2a_code, details=details)


__all__ = [
    "A2AMessage",
    "A2ATask",
    "A2ATaskStatus",
    "parse_message",
    "parse_params",
    "serialize_message_envelope",
]
