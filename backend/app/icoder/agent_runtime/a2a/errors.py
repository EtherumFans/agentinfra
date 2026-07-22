"""A2A Error codes (SPEC §6).

Two layers of error codes:

1. **JSON-RPC 2.0 standard codes** (SPEC §6.1) — the ``code`` field of
   the JSON-RPC ``error`` object. Numeric range -32700 to -32099.

2. **A2A v0.3 business codes** (SPEC §6.2) — the ``data.a2a_error_code``
   field of the same error object. String identifiers like
   ``INVALID_REQUEST``, ``AGENT_NOT_FOUND``, etc.

A single error response uses both: ``code`` is the JSON-RPC standard,
``data.a2a_error_code`` is the A2A-specific business code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 standard error codes (SPEC §6.1)
# ---------------------------------------------------------------------------


JSON_RPC_PARSE_ERROR: Final[int] = -32700
JSON_RPC_INVALID_REQUEST: Final[int] = -32600
JSON_RPC_METHOD_NOT_FOUND: Final[int] = -32601
JSON_RPC_INVALID_PARAMS: Final[int] = -32602
JSON_RPC_INTERNAL_ERROR: Final[int] = -32603

# A2A v0.3 server-error range -32000 to -32099 is reserved for custom
# codes; we use -32000 as the base for A2A business errors.

# ---------------------------------------------------------------------------
# A2A v0.3 business error codes (SPEC §6.2)
# ---------------------------------------------------------------------------


class A2AErrorCode:
    """A2A v0.3 business error codes (SPEC §6.2)."""

    INVALID_REQUEST = "INVALID_REQUEST"
    METHOD_NOT_FOUND = "METHOD_NOT_FOUND"
    INVALID_PARAMS = "INVALID_PARAMS"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    CONTEXT_INVALID = "CONTEXT_INVALID"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_NOT_CANCELABLE = "TASK_NOT_CANCELABLE"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    PHI_REDACTION_FAILED = "PHI_REDACTION_FAILED"
    PRODUCTION_WRITEBACK_BLOCKED = "PRODUCTION_WRITEBACK_BLOCKED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    PLANNING_FAILED = "PLANNING_FAILED"
    EXPERT_FAILED = "EXPERT_FAILED"
    AGGREGATION_FAILED = "AGGREGATION_FAILED"
    # A1B-AE.5 — Corti public §9 mcp-authentication error codes (4 exhaustive)
    MCP_AUTH_DUPLICATE_NAME = "mcp_auth_duplicate_name"
    MCP_AUTH_MISSING_NAME = "mcp_auth_missing_name"
    MCP_AUTH_MISSING_TOKEN = "mcp_auth_missing_token"
    MCP_AUTH_MISSING_CREDENTIALS = "mcp_auth_missing_credentials"


# Phase 1: AUTH_REQUIRED and RATE_LIMITED are reserved but not raised.
ALL_A2A_ERROR_CODES: Final[tuple[str, ...]] = (
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
    A2AErrorCode.AUTH_REQUIRED,
    A2AErrorCode.RATE_LIMITED,
    A2AErrorCode.PLANNING_FAILED,
    A2AErrorCode.EXPERT_FAILED,
    A2AErrorCode.AGGREGATION_FAILED,
    A2AErrorCode.MCP_AUTH_DUPLICATE_NAME,
    A2AErrorCode.MCP_AUTH_MISSING_NAME,
    A2AErrorCode.MCP_AUTH_MISSING_TOKEN,
    A2AErrorCode.MCP_AUTH_MISSING_CREDENTIALS,
)


# ---------------------------------------------------------------------------
# A2AError — typed error with envelope serialization
# ---------------------------------------------------------------------------


# Mapping table: A2A business code → outer HTTP status.
# JSON-RPC spec says outer HTTP is 200 for errors, but the A2A v0.3 spec
# explicitly couples some codes to HTTP semantics for HTTP-only clients.
# Per SPEC §6.2 / §6.3.
_HTTP_STATUS_BY_CODE: Final[dict[str, int]] = {
    A2AErrorCode.INVALID_REQUEST: 400,
    A2AErrorCode.METHOD_NOT_FOUND: 404,
    A2AErrorCode.INVALID_PARAMS: 400,
    A2AErrorCode.INTERNAL_ERROR: 500,
    A2AErrorCode.AGENT_NOT_FOUND: 404,
    A2AErrorCode.CONTEXT_INVALID: 400,
    A2AErrorCode.TASK_NOT_FOUND: 404,
    A2AErrorCode.TASK_NOT_CANCELABLE: 409,
    A2AErrorCode.UNSUPPORTED_OPERATION: 501,
    A2AErrorCode.PHI_REDACTION_FAILED: 500,
    A2AErrorCode.PRODUCTION_WRITEBACK_BLOCKED: 403,
    A2AErrorCode.AUTH_REQUIRED: 401,
    A2AErrorCode.RATE_LIMITED: 429,
    A2AErrorCode.PLANNING_FAILED: 500,
    A2AErrorCode.EXPERT_FAILED: 502,
    A2AErrorCode.AGGREGATION_FAILED: 500,
    # A1B-AE.5 — MCP auth errors are client-side (4xx)
    A2AErrorCode.MCP_AUTH_DUPLICATE_NAME: 400,
    A2AErrorCode.MCP_AUTH_MISSING_NAME: 400,
    A2AErrorCode.MCP_AUTH_MISSING_TOKEN: 400,
    A2AErrorCode.MCP_AUTH_MISSING_CREDENTIALS: 400,
}

# Mapping: A2A business code → JSON-RPC standard code (data wrapper).
_JSONRPC_CODE_BY_A2A: Final[dict[str, int]] = {
    A2AErrorCode.INVALID_REQUEST: JSON_RPC_INVALID_REQUEST,
    A2AErrorCode.METHOD_NOT_FOUND: JSON_RPC_METHOD_NOT_FOUND,
    A2AErrorCode.INVALID_PARAMS: JSON_RPC_INVALID_PARAMS,
    A2AErrorCode.INTERNAL_ERROR: JSON_RPC_INTERNAL_ERROR,
    A2AErrorCode.AGENT_NOT_FOUND: JSON_RPC_METHOD_NOT_FOUND,
    A2AErrorCode.CONTEXT_INVALID: JSON_RPC_INVALID_REQUEST,
    A2AErrorCode.TASK_NOT_FOUND: JSON_RPC_METHOD_NOT_FOUND,
    A2AErrorCode.TASK_NOT_CANCELABLE: JSON_RPC_INVALID_REQUEST,
    A2AErrorCode.UNSUPPORTED_OPERATION: JSON_RPC_METHOD_NOT_FOUND,
    A2AErrorCode.PHI_REDACTION_FAILED: JSON_RPC_INTERNAL_ERROR,
    A2AErrorCode.PRODUCTION_WRITEBACK_BLOCKED: JSON_RPC_INVALID_REQUEST,
    A2AErrorCode.AUTH_REQUIRED: JSON_RPC_INVALID_REQUEST,
    A2AErrorCode.RATE_LIMITED: JSON_RPC_INVALID_REQUEST,
    A2AErrorCode.PLANNING_FAILED: JSON_RPC_INTERNAL_ERROR,
    A2AErrorCode.EXPERT_FAILED: JSON_RPC_INTERNAL_ERROR,
    A2AErrorCode.AGGREGATION_FAILED: JSON_RPC_INTERNAL_ERROR,
    # A1B-AE.5 — MCP auth errors are param-level validation failures
    A2AErrorCode.MCP_AUTH_DUPLICATE_NAME: JSON_RPC_INVALID_PARAMS,
    A2AErrorCode.MCP_AUTH_MISSING_NAME: JSON_RPC_INVALID_PARAMS,
    A2AErrorCode.MCP_AUTH_MISSING_TOKEN: JSON_RPC_INVALID_PARAMS,
    A2AErrorCode.MCP_AUTH_MISSING_CREDENTIALS: JSON_RPC_INVALID_PARAMS,
}

# Human-readable message (short) for each A2A business code.
_MESSAGE_BY_CODE: Final[dict[str, str]] = {
    A2AErrorCode.INVALID_REQUEST: "Invalid request",
    A2AErrorCode.METHOD_NOT_FOUND: "Method not found",
    A2AErrorCode.INVALID_PARAMS: "Invalid params",
    A2AErrorCode.INTERNAL_ERROR: "Internal error",
    A2AErrorCode.AGENT_NOT_FOUND: "Agent not found",
    A2AErrorCode.CONTEXT_INVALID: "Context invalid",
    A2AErrorCode.TASK_NOT_FOUND: "Task not found",
    A2AErrorCode.TASK_NOT_CANCELABLE: "Task not cancelable",
    A2AErrorCode.UNSUPPORTED_OPERATION: "Unsupported operation",
    A2AErrorCode.PHI_REDACTION_FAILED: "PHI redaction failed",
    A2AErrorCode.PRODUCTION_WRITEBACK_BLOCKED: "Production writeback blocked",
    A2AErrorCode.AUTH_REQUIRED: "Authorization required",
    A2AErrorCode.RATE_LIMITED: "Rate limited",
    A2AErrorCode.PLANNING_FAILED: "Planning failed",
    A2AErrorCode.EXPERT_FAILED: "Expert failed",
    A2AErrorCode.AGGREGATION_FAILED: "Aggregation failed",
    # A1B-AE.5 — Corti public §9 mcp-authentication error messages
    A2AErrorCode.MCP_AUTH_DUPLICATE_NAME: "Duplicate MCP auth name in message",
    A2AErrorCode.MCP_AUTH_MISSING_NAME: "MCP auth DataPart missing mcp_name",
    A2AErrorCode.MCP_AUTH_MISSING_TOKEN: "MCP auth DataPart missing token",
    A2AErrorCode.MCP_AUTH_MISSING_CREDENTIALS: "MCP auth DataPart missing client_id/client_secret",
}


@dataclass
class A2AError(Exception):
    """Typed A2A error with envelope (de)serialization."""

    code: str
    """A2A business code (e.g., ``INVALID_REQUEST``)."""

    message: str = ""
    """Short human-readable summary. Defaults from :data:`_MESSAGE_BY_CODE`."""

    details: str = ""
    """Long-form detail (e.g., which part failed validation)."""

    http_status: int = 0
    """Outer HTTP status. Defaults from :data:`_HTTP_STATUS_BY_CODE`."""

    jsonrpc_code: int = 0
    """JSON-RPC standard error code. Defaults from :data:`_JSONRPC_CODE_BY_A2A`."""

    spec_ref: str = ""
    """URL pointing into the A2A v0.3 spec. Optional."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Catch-all for additional structured data attached to the error."""

    def __post_init__(self) -> None:
        if self.code not in ALL_A2A_ERROR_CODES:
            raise ValueError(
                f"unknown A2A error code: {self.code!r}. "
                f"Valid: {', '.join(ALL_A2A_ERROR_CODES)}"
            )
        if not self.message:
            self.message = _MESSAGE_BY_CODE[self.code]
        if not self.http_status:
            self.http_status = _HTTP_STATUS_BY_CODE[self.code]
        if not self.jsonrpc_code:
            self.jsonrpc_code = _JSONRPC_CODE_BY_A2A[self.code]

    # ── Envelope shape

    def to_envelope_data(self) -> dict[str, Any]:
        """Build the ``error.data`` object per SPEC §6.3."""
        data: dict[str, Any] = {"a2a_error_code": self.code}
        if self.details:
            data["details"] = self.details
        if self.spec_ref:
            data["spec_ref"] = self.spec_ref
        # extra goes last, lets callers override defaults
        data.update(self.extra)
        return data

    def to_envelope_error(self) -> dict[str, Any]:
        """Build the full ``error`` object per SPEC §4.4 / §6.3."""
        return {
            "code": self.jsonrpc_code,
            "message": self.message,
            "data": self.to_envelope_data(),
        }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_error(code: str, **kwargs: Any) -> A2AError:
    """Construct an :class:`A2AError` with the given business code."""
    return A2AError(code=code, **kwargs)


# Convenience constructors for the most common codes. Avoid hand-rolling
# A2AError() at every call site — these are the spec-named helpers.

def invalid_request(details: str = "", **kw: Any) -> A2AError:
    return A2AError(code=A2AErrorCode.INVALID_REQUEST, details=details, **kw)


def method_not_found(method: str = "", **kw: Any) -> A2AError:
    details = f"method {method!r} not in A2A v0.3 spec" if method else ""
    return A2AError(
        code=A2AErrorCode.METHOD_NOT_FOUND,
        details=details,
        spec_ref="https://a2a-protocol.org/v0.3/spec#methods",
        **kw,
    )


def invalid_params(details: str = "", **kw: Any) -> A2AError:
    return A2AError(code=A2AErrorCode.INVALID_PARAMS, details=details, **kw)


def internal_error(details: str = "", **kw: Any) -> A2AError:
    return A2AError(code=A2AErrorCode.INTERNAL_ERROR, details=details, **kw)


def agent_not_found(agent_id: str, **kw: Any) -> A2AError:
    return A2AError(
        code=A2AErrorCode.AGENT_NOT_FOUND,
        details=f"agent {agent_id!r} not registered",
        **kw,
    )


def context_invalid(details: str = "", **kw: Any) -> A2AError:
    return A2AError(code=A2AErrorCode.CONTEXT_INVALID, details=details, **kw)


def task_not_found(task_id: str = "", **kw: Any) -> A2AError:
    details = f"task {task_id!r} not found" if task_id else ""
    return A2AError(code=A2AErrorCode.TASK_NOT_FOUND, details=details, **kw)


def task_not_cancelable(task_id: str = "", **kw: Any) -> A2AError:
    details = f"task {task_id!r} is in a terminal state" if task_id else ""
    return A2AError(code=A2AErrorCode.TASK_NOT_CANCELABLE, details=details, **kw)


def unsupported_operation(details: str = "", **kw: Any) -> A2AError:
    return A2AError(
        code=A2AErrorCode.UNSUPPORTED_OPERATION,
        details=details or "operation not implemented in Phase 1",
        **kw,
    )


def phi_redaction_failed(details: str = "", **kw: Any) -> A2AError:
    return A2AError(code=A2AErrorCode.PHI_REDACTION_FAILED, details=details, **kw)


def production_writeback_blocked(details: str = "", **kw: Any) -> A2AError:
    return A2AError(
        code=A2AErrorCode.PRODUCTION_WRITEBACK_BLOCKED, details=details, **kw
    )


# A1B-AE.5 — Corti public §9 mcp-authentication error factories
def mcp_auth_duplicate_name(name: str = "", **kw: Any) -> A2AError:
    details = f"duplicate mcp_name {name!r} in auth DataParts" if name else ""
    return A2AError(code=A2AErrorCode.MCP_AUTH_DUPLICATE_NAME, details=details, **kw)


def mcp_auth_missing_name(**kw: Any) -> A2AError:
    return A2AError(code=A2AErrorCode.MCP_AUTH_MISSING_NAME, **kw)


def mcp_auth_missing_token(name: str = "", **kw: Any) -> A2AError:
    details = f"auth DataPart for mcp_name={name!r} missing token" if name else ""
    return A2AError(code=A2AErrorCode.MCP_AUTH_MISSING_TOKEN, details=details, **kw)


def mcp_auth_missing_credentials(name: str = "", **kw: Any) -> A2AError:
    details = (
        f"auth DataPart for mcp_name={name!r} missing client_id/client_secret"
        if name
        else ""
    )
    return A2AError(code=A2AErrorCode.MCP_AUTH_MISSING_CREDENTIALS, details=details, **kw)


__all__ = [
    "A2AError",
    "A2AErrorCode",
    "ALL_A2A_ERROR_CODES",
    "JSON_RPC_INTERNAL_ERROR",
    "JSON_RPC_INVALID_PARAMS",
    "JSON_RPC_INVALID_REQUEST",
    "JSON_RPC_METHOD_NOT_FOUND",
    "JSON_RPC_PARSE_ERROR",
    "agent_not_found",
    "context_invalid",
    "internal_error",
    "invalid_params",
    "invalid_request",
    "make_error",
    "method_not_found",
    "mcp_auth_duplicate_name",
    "mcp_auth_missing_name",
    "mcp_auth_missing_token",
    "mcp_auth_missing_credentials",
    "phi_redaction_failed",
    "production_writeback_blocked",
    "task_not_cancelable",
    "task_not_found",
    "unsupported_operation",
]