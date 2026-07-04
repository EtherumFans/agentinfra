"""Outbound A2A route (SPEC §7.3).

Orchestrator → Expert (``POST /api/icoder/internal/experts/{expert_id}/v1/message:send``).

Per Q-A10 (open question Q-A10) Phase 1 dispatches **in-process** via
a caller-supplied callable. The HTTP route exists so spec compliance
is testable end-to-end; it does not actually issue an HTTP request to
the Expert.

The expert caller signature::

    expert_caller(expert_id: str, request_body: dict) -> dict

Returns the A2A Message dict that the Expert would return. The route
wraps it in a JSON-RPC 2.0 success envelope.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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
    agent_not_found,
    internal_error,
    invalid_params,
)
from .messages import parse_params
from .version import (
    A2A_PROTOCOL_HEADER,
    A2A_PROTOCOL_VERSION,
    A2AVersionError,
    validate_version_header,
)


# In-process callable contract for an Expert invocation.
ExpertCaller = Callable[[str, dict[str, Any]], Union[dict[str, Any], Awaitable[dict[str, Any]]]]


def build_outbound_router(expert_caller: ExpertCaller) -> APIRouter:
    """Build the outbound (Orchestrator → Expert) router.

    The caller injects an in-process ``expert_caller(expert_id, body)``
    that returns an A2A Message dict. For Phase 1 this is the only
    integration shape (Q-A10).
    """
    router = APIRouter(prefix="/internal/experts", tags=["a2a-outbound"])

    @router.post("/{expert_id}/v1/message:send", operation_id="a2a_internal_message_send_v0_3")
    async def internal_message_send(expert_id: str, request: Request) -> JSONResponse:
        # ── [1] Version header
        try:
            validate_version_header(dict(request.headers))
        except A2AVersionError as e:
            return JSONResponse(
                status_code=400,
                headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
                content=make_parse_error_response(str(e)),
            )

        # ── [2] Body parse
        raw = await request.body()
        parsed = parse_request(raw)
        if isinstance(parsed, A2AError):
            return _error(parsed, None, parsed.http_status)
        if not isinstance(parsed, JsonRpcRequest):
            return _error(
                A2AError(
                    code=A2AErrorCode.INTERNAL_ERROR,
                    details="envelope parser returned unexpected type",
                ),
                None,
                500,
            )

        # ── [3] Method validate
        method_err = validate_method(parsed.method, SUPPORTED_METHODS)
        if method_err is not None:
            return _error(method_err, parsed.id, method_err.http_status)

        # ── [4] params.message parse (parts/role validated)
        try:
            params = parse_params(parsed.params)
        except A2AError as e:
            return _error(e, parsed.id, e.http_status)

        # ── [5] Build Expert-bound request body
        outbound_body = {
            "jsonrpc": "2.0",
            "id": parsed.id,
            "method": parsed.method,
            "params": parsed.params,
            "metadata": (parsed.params or {}).get("metadata", {}),
        }

        # ── [6] Dispatch in-process
        try:
            result = expert_caller(expert_id, outbound_body)
            # Awaitable support
            if hasattr(result, "__await__"):
                result = await result  # type: ignore[assignment]
        except KeyError:
            return _error(agent_not_found(expert_id), parsed.id, 404)
        except A2AError as e:
            return _error(e, parsed.id, e.http_status)
        except Exception as e:
            err = A2AError(
                code=A2AErrorCode.INTERNAL_ERROR,
                details=f"expert invocation failed: {e}",
            )
            return _error(err, parsed.id, err.http_status)

        # ── [7] Envelope success response
        body = make_success_response(parsed.id, result)
        return JSONResponse(
            status_code=200,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content=body,
        )

    return router


def _error(
    err: A2AError, req_id: str | int | None, http_status: int
) -> JSONResponse:
    body = make_error_response(req_id, err)
    return JSONResponse(
        status_code=http_status,
        headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        content=body,
    )


__all__ = [
    "ExpertCaller",
    "build_outbound_router",
]