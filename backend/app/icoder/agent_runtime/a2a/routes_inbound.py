"""Inbound A2A route (SPEC §7.2).

Thin wrapper around :class:`InboundHandler`:

::

    HTTP POST body
      → JSON-RPC parse
      → method validate
      → params.message parse (incl. parts validation, Q4 contextId discard)
      → InboundRequest + InboundHandler.handle()
      → JSON-RPC success/error envelope
      → HTTP 200 + A2A-Protocol-Version: 0.3

The handler is unaware of JSON-RPC. This module owns the wire format.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..orchestrator.inbound_handler import (
    InboundHandler,
    InboundMessage,
    InboundRequest,
)
from .envelope import (
    SUPPORTED_METHODS,
    JsonRpcRequest,
    make_error_response,
    make_parse_error_response,
    make_success_response,
    parse_request,
    validate_method,
)
from .errors import (
    A2AError,
    A2AErrorCode,
    JSON_RPC_INVALID_REQUEST,
    JSON_RPC_PARSE_ERROR,
    agent_not_found,
    invalid_params,
    invalid_request,
)
from .messages import parse_params
from .version import (
    A2A_PROTOCOL_HEADER,
    A2A_PROTOCOL_VERSION,
    A2AVersionError,
    validate_version_header,
)


# JSON-RPC spec says outer HTTP status is 200 for protocol errors.
# However, two cases (parse error + missing protocol version) cannot even
# be parsed into a JSON-RPC envelope, so the route returns 400 directly.
_OUTER_HTTP_STATUS: int = 200


def build_inbound_router(handler: InboundHandler) -> APIRouter:
    """Build the inbound message:send router.

    Caller mounts it at e.g. ``/api/icoder/agents/{agent_id}`` — the
    :func:`mount_a2a` helper does this.
    """
    router = APIRouter(tags=["a2a-inbound"])

    @router.post("/v1/message:send")
    async def message_send(agent_id: str, request: Request) -> JSONResponse:
        """``POST /v1/message:send`` — A2A v0.3 message/send entry point."""
        return await _dispatch(handler, agent_id, request)

    return router


async def _dispatch(
    handler: InboundHandler,
    agent_id: str,
    request: Request,
) -> JSONResponse:
    """Internal: parse envelope, call handler, serialize response."""
    # ── [1] Version header (Q-A2 strict)
    try:
        validate_version_header(dict(request.headers))
    except A2AVersionError as e:
        # Cannot build a real envelope (no parsed request), return HTTP 400
        # directly with a parse-error-shaped body.
        return JSONResponse(
            status_code=400,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content=make_parse_error_response(str(e)),
        )

    # ── [2] Body parse
    raw = await request.body()
    parsed = parse_request(raw)
    if isinstance(parsed, A2AError):
        return _error_response(parsed, None, _OUTER_HTTP_STATUS)

    if not isinstance(parsed, JsonRpcRequest):
        # Defensive — parse_request returns either JsonRpcRequest or A2AError
        err = A2AError(
            code=A2AErrorCode.INTERNAL_ERROR,
            details="envelope parser returned unexpected type",
        )
        return _error_response(err, None, _OUTER_HTTP_STATUS)

    # ── [3] Method validate
    method_err = validate_method(parsed.method, SUPPORTED_METHODS)
    if method_err is not None:
        # Per SPEC §6.1: method not found → -32601 + HTTP 404 (not 200).
        return _error_response(method_err, parsed.id, method_err.http_status)

    # ── [4] params.message parse
    try:
        params = parse_params(parsed.params)
    except A2AError as e:
        return _error_response(e, parsed.id, e.http_status)

    message = params["message"]
    msg_obj = parsed.params["message"] if parsed.params else {}

    # ── [5] Build InboundRequest
    # Q4: ignore any client contextId — server-generated only.
    inbound_msg = InboundMessage(
        role=message["role"],
        parts=message["parts"],
        interaction_id=message["messageId"] or msg_obj.get("messageId", ""),
    )
    inbound_req = InboundRequest(
        message=inbound_msg,
        metadata=message["metadata"] or {},
    )

    # ── [6] Call handler (sync, but route is async) ──────────────────
    # Run in a thread so the sync handler (and any asyncio.run inside
    # its LLM/Expert adapters) doesn't deadlock against the running
    # event loop. Also keeps the loop unblocked during long LLM calls.
    import asyncio as _asyncio
    response = await _asyncio.to_thread(handler.handle, agent_id, inbound_req)

    # ── [7] Serialize response
    return _serialize_response(parsed.id, response)


def _serialize_response(req_id: str | int | None, response: Any) -> JSONResponse:
    """Build JSON-RPC envelope from an :class:`InboundResponse`."""
    if response.kind == "message":
        result = {
            "kind": "message",
            "role": response.role,
            "messageId": response.message_id,
            "contextId": response.context_id,
            "parts": response.parts,
            "metadata": response.metadata,
        }
        body = make_success_response(req_id, result)
        return JSONResponse(
            status_code=_OUTER_HTTP_STATUS,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content=body,
        )

    # Error path
    err_obj = response.error or {}
    # Map the OrchestratorError envelope to A2AError for envelope shape.
    a2a_code = err_obj.get("code", "INTERNAL_ERROR")
    # Translate legacy internal code names → A2A business codes if needed.
    code = _translate_code(a2a_code)
    details = err_obj.get("message", "")
    err = A2AError(code=code, details=details)
    return _error_response(err, req_id, response.http_status)


def _error_response(
    err: A2AError, req_id: str | int | None, http_status: int
) -> JSONResponse:
    """Build a JSON-RPC error response with the A2A-Protocol-Version header."""
    body = make_error_response(req_id, err)
    return JSONResponse(
        status_code=http_status,
        headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        content=body,
    )


# ---------------------------------------------------------------------------
# Code translation: legacy OrchestratorError codes → A2A business codes
# ---------------------------------------------------------------------------

# Maps the OrchestratorError envelope codes used by the handler to the
# matching A2A business codes. The handler uses a small set of lowercased
# codes; A2A uses UPPERCASE_SNAKE. Keep this table tight.
_LEGACY_TO_A2A_CODE = {
    "invalid_request": A2AErrorCode.INVALID_REQUEST,
    "planning_failed": A2AErrorCode.PLANNING_FAILED,
    "expert_failed": A2AErrorCode.EXPERT_FAILED,
    "aggregation_failed": A2AErrorCode.AGGREGATION_FAILED,
    "phi_redaction_failed": A2AErrorCode.PHI_REDACTION_FAILED,
    "agent_not_found": A2AErrorCode.AGENT_NOT_FOUND,
}


def _translate_code(legacy: str) -> str:
    """Translate legacy OrchestratorError code to A2A business code."""
    return _LEGACY_TO_A2A_CODE.get(legacy.lower(), A2AErrorCode.INTERNAL_ERROR)


__all__ = [
    "build_inbound_router",
]