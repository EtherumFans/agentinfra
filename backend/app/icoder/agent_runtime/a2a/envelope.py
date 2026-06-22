"""JSON-RPC 2.0 envelope (SPEC §4).

Wraps A2A messages in JSON-RPC 2.0 request/response envelopes:

::

    Request:
        {"jsonrpc": "2.0", "id": "...", "method": "message/send", "params": {...}}

    Success Response:
        {"jsonrpc": "2.0", "id": "...", "result": {...}}

    Error Response:
        {"jsonrpc": "2.0", "id": "...", "error": {"code": -32600, "message": "...", "data": {...}}}

Strict spec compliance (Q-A1):
- Batch requests (array body) → -32600
- Unknown ``method`` → -32601
- Missing ``jsonrpc: "2.0"`` or wrong type → -32600
- ``id`` may be string / number / null (we accept all per spec)
"""

from __future__ import annotations

import json
from typing import Any, Final, Union

from pydantic import BaseModel, ConfigDict, Field

from .errors import (
    JSON_RPC_INVALID_REQUEST,
    JSON_RPC_METHOD_NOT_FOUND,
    JSON_RPC_PARSE_ERROR,
    A2AError,
    A2AErrorCode,
    invalid_request,
    method_not_found,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JSONRPC_VERSION: Final[str] = "2.0"

# Phase 1 supported methods (SPEC §3). Phase 5 adds message/stream.
SUPPORTED_METHODS: Final[tuple[str, ...]] = ("message/send",)

# Phase 1 supported A2A business operations. Phase 5 adds tasks/cancel,
# Phase 1 stubs tasks/get and tasks/cancel (routes_task_stub.py).
SUPPORTED_TASKS_METHODS: Final[tuple[str, ...]] = (
    "tasks/get",
    "tasks/cancel",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request envelope (SPEC §4.1).

    ``id`` is intentionally typed ``str | int | None`` per the JSON-RPC
    spec — clients may use any of those. ``None`` is used for
    notifications (no response expected).
    """

    model_config = ConfigDict(extra="allow")

    jsonrpc: str = Field(default=JSONRPC_VERSION)
    id: Union[str, int, None] = None
    method: str = ""
    params: dict[str, Any] | None = None


class JsonRpcErrorBody(BaseModel):
    """JSON-RPC 2.0 error object (SPEC §4.4)."""

    model_config = ConfigDict(extra="allow")

    code: int
    message: str
    data: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope (success or error).

    Either ``result`` (success) or ``error`` (failure) is populated —
    never both. The Pydantic model carries both as optional so callers
    pick which to fill.
    """

    model_config = ConfigDict(extra="allow")

    jsonrpc: str = Field(default=JSONRPC_VERSION)
    id: Union[str, int, None] = None
    result: Any = None
    error: JsonRpcErrorBody | None = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class EnvelopeParseError(Exception):
    """Raised when the request body cannot be parsed into a JsonRpcRequest.

    The route catches this and returns a -32700 (Parse Error) response
    with HTTP 400 — the body cannot even be turned into an envelope.
    """

    def __init__(self, message: str, *, code: int = JSON_RPC_PARSE_ERROR) -> None:
        super().__init__(message)
        self.code = code


def parse_request(body: bytes | str | dict) -> JsonRpcRequest | A2AError:
    """Parse a JSON-RPC 2.0 request from raw bytes / str / dict.

    Returns:
        :class:`JsonRpcRequest` on success.
        :class:`A2AError` (with code=INVALID_REQUEST or PARSE_ERROR)
        on failure. The route catches it and serializes the error.

    Strict spec compliance (Q-A1):
    - Top-level must be a JSON object, NOT an array (batch rejected).
    - ``jsonrpc`` must equal ``"2.0"``.
    - ``method`` must be a non-empty string.
    """
    # Accept dict / list (already parsed) or raw JSON.
    if isinstance(body, dict):
        obj = body
    elif isinstance(body, (bytes, bytearray)):
        try:
            obj = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return _envelope_error(
                f"JSON parse error: {e}",
                code=JSON_RPC_PARSE_ERROR,
                a2a_code=A2AErrorCode.INTERNAL_ERROR,
                details=str(e),
            )
    elif isinstance(body, str):
        try:
            obj = json.loads(body)
        except json.JSONDecodeError as e:
            return _envelope_error(
                f"JSON parse error: {e}",
                code=JSON_RPC_PARSE_ERROR,
                a2a_code=A2AErrorCode.INTERNAL_ERROR,
                details=str(e),
            )
    elif isinstance(body, (list, tuple)):
        # Already a Python list/tuple — treat as batch input.
        obj = list(body)
    else:
        return _envelope_error(
            f"unsupported body type: {type(body).__name__}",
            code=JSON_RPC_PARSE_ERROR,
            a2a_code=A2AErrorCode.INTERNAL_ERROR,
        )

    # Strict: array (batch) rejected per SPEC §4.5
    if isinstance(obj, list):
        return invalid_request(
            details="batch requests not supported in Phase 1",
        )

    if not isinstance(obj, dict):
        return _envelope_error(
            "request body must be a JSON object",
            code=JSON_RPC_INVALID_REQUEST,
            a2a_code=A2AErrorCode.INVALID_REQUEST,
            details=f"got {type(obj).__name__}",
        )

    # Validate jsonrpc field
    jsonrpc = obj.get("jsonrpc")
    if jsonrpc != JSONRPC_VERSION:
        return invalid_request(
            details=(
                f"jsonrpc must be {JSONRPC_VERSION!r}, got {jsonrpc!r}"
            ),
        )

    # Validate method
    method = obj.get("method")
    if not isinstance(method, str) or not method:
        return invalid_request(details="missing or invalid 'method' field")

    # id is optional (notification), but if present must be str/int/None
    req_id = obj.get("id", None)
    if req_id is not None and not isinstance(req_id, (str, int)):
        return invalid_request(
            details=f"id must be string, number, or null; got {type(req_id).__name__}",
        )

    try:
        return JsonRpcRequest.model_validate(obj)
    except Exception as e:
        return invalid_request(details=f"envelope validation failed: {e}")


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def make_success_response(req_id: str | int | None, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response body."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "result": result,
    }


def make_error_response(req_id: str | int | None, error: A2AError) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response body from an :class:`A2AError`."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "error": error.to_envelope_error(),
    }


def make_parse_error_response(message: str, req_id: str | int | None = None) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 parse-error response (-32700).

    Used when the body could not even be parsed — there's no
    ``id`` to echo back, so we use None.
    """
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "error": {
            "code": JSON_RPC_PARSE_ERROR,
            "message": "Parse error",
            "data": {"a2a_error_code": A2AErrorCode.INVALID_REQUEST, "details": message},
        },
    }


# ---------------------------------------------------------------------------
# Method validation
# ---------------------------------------------------------------------------


def validate_method(method: str, allowed: tuple[str, ...]) -> A2AError | None:
    """Return an :class:`A2AError` (METHOD_NOT_FOUND) if ``method`` is not in ``allowed``.

    Returns ``None`` if the method is allowed. The route should call
    this and short-circuit on a non-None result.
    """
    if method not in allowed:
        return method_not_found(method=method)
    return None


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _envelope_error(
    message: str,
    *,
    code: int,
    a2a_code: str,
    details: str = "",
) -> A2AError:
    """Build a synthetic A2AError for parse failures."""
    return A2AError(
        code=a2a_code,
        message=message,
        details=details,
        jsonrpc_code=code,
    )


__all__ = [
    "EnvelopeParseError",
    "JSONRPC_VERSION",
    "JsonRpcErrorBody",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "SUPPORTED_METHODS",
    "SUPPORTED_TASKS_METHODS",
    "make_error_response",
    "make_parse_error_response",
    "make_success_response",
    "parse_request",
    "validate_method",
]