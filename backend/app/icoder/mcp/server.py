"""MCP server — FastAPI in-process mount exposing 5 MedCodER tools.

These 5 tools (search_icd, verify_code, get_differentiation_hint,
rerank_codes, calibrate_confidence) back the Medical Coding Agent
(icoder/medical-coding-agent@2.0.0, Corti-style). The MedCodER 5-stage
pipeline is the Agent's internal_engine; users interact with the
Corti-style 7-step workflow + 8-field output contract, not with the
5-stage technical surface directly.

Transport:
  - POST /mcp/v1/tools/list  — returns all tool descriptors
  - POST /mcp/v1/tools/call  — dispatches one tool invocation

Wire format: JSON-RPC 2.0. Per the plan, only ``tools/list`` and
``tools/call`` are implemented in M2; ``initialize`` / ``resources/list``
/ ``prompts/list`` return ``-32601 Method Not Found``.

Envelope shape:

  Request::
      {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "tools/list" | "tools/call",
        "params": {
          "name": "search_icd",                 # tools/call only
          "arguments": {"emr_text": "..."},     # tools/call only
          "_meta": {"contextId": "ctx-uuid"}    # optional
        }
      }

  Success response::
      {
        "jsonrpc": "2.0",
        "id": "req-1",
        "result": {"content": [...], "isError": false}
      }

  Error response::
      {
        "jsonrpc": "2.0",
        "id": "req-1",
        "error": {"code": -32602, "message": "...", "data": {...}}
      }

Context propagation:
  - Middleware stashes ``params._meta.contextId`` on ``request.state.context_id``
    before dispatch. Handlers can read it via ``request.state.context_id``.

PHI redaction:
  - Per audit Part 7.1, every tool input MUST pass through PHI redaction
    before reaching a service. In M2 we delegate redaction to the handler
    level (best-effort): if a ``PHIRedactor`` instance is registered on
    ``app.state.phi_redactor``, the server invokes it on string-typed
    arguments before passing them to the handler. When ``context_id`` is
    missing OR the redactor is unavailable, the server returns
    ``-32004 PHI Redaction Failed`` (NOT a silent skip).

Boot-time assertion:
  - :func:`assert_tool_registry_matches_agent_pack` runs at mount time
    and ensures ``TOOL_REGISTRY`` matches the Agent Pack's ``tools`` list.
"""

from __future__ import annotations

import importlib
import json
import logging
import time
from typing import Any, Callable, Awaitable

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStatus,
    RunTraceStep,
    emit_trace_event,
)
from .auth import MCPAuthConfig
from .auth_resolver import RunAuthContext, resolve_mcp_auth
from .errors import MCPAuthError, MCPError, MCPErrorCode
from .tool_registry import TOOL_REGISTRY, ToolDescriptor, assert_tool_registry_matches_agent_pack

logger = logging.getLogger(__name__)


ALLOWED_METHODS = ("tools/list", "tools/call")


# ── Handler resolution ──────────────────────────────────────────


def resolve_handler(handler_ref: str) -> Callable[..., Awaitable[Any]]:
    """Resolve ``module:func`` dotted path to the actual async callable.

    Lazy import keeps the registry importable even when a handler module
    has heavy dependencies (e.g. pydantic, sentence-transformers).

    Raises:
        ImportError: module path is invalid.
        AttributeError: function name doesn't exist on the module.
    """
    module_path, _, func_name = handler_ref.partition(":")
    if not module_path or not func_name:
        raise ImportError(
            f"invalid handler_ref {handler_ref!r}: expected 'module:func'"
        )
    module = importlib.import_module(module_path)
    handler = getattr(module, func_name, None)
    if handler is None:
        raise AttributeError(
            f"{module_path} has no attribute {func_name}"
        )
    if not callable(handler):
        raise TypeError(f"{handler_ref} is not callable")
    return handler


# ── PHI redaction ───────────────────────────────────────────────


def _redact_phi(arguments: dict[str, Any], redactor: Any | None) -> dict[str, Any]:
    """Best-effort PHI redaction of string-typed arguments.

    Walks ``arguments`` recursively; for every ``str`` value, runs it
    through ``redactor.redact(text)`` and replaces with the redacted
    form. Non-string values pass through untouched.

    Why best-effort:
    - M2 keeps the handler surface 1:1 thin. Real PHI redaction is
      enforced at the Context boundary in production (every ContextMessage
      is constructed with ``redacted=True`` frozen). The MCP boundary
      adds a second line of defense so external clients cannot smuggle
      raw PHI through the JSON-RPC envelope.

    Returns the (possibly modified) arguments dict.
    """
    if redactor is None:
        return arguments
    redact = getattr(redactor, "redact", None)
    if not callable(redact):
        return arguments

    def _walk(value: Any) -> Any:
        if isinstance(value, str):
            try:
                result = redact(value)
                # PHIRedactor.redact returns a PHIRedactionResult; we
                # accept any object exposing ``.redacted_text``.
                if hasattr(result, "redacted_text"):
                    return result.redacted_text
                if isinstance(result, str):
                    return result
                return value
            except Exception:
                # Redaction failure should NOT silently leak raw input.
                # Replace with a generic redaction marker so the handler
                # can still process (it never sees raw PHI).
                return "<REDACTED:PHI_REDACTION_ERROR>"
        if isinstance(value, list):
            return [_walk(v) for v in value]
        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        return value

    return _walk(arguments)


# ── Auth config redaction (Phase 3-C1 B5 #8) ────────────────────


def _redact_auth_config(auth_config: MCPAuthConfig) -> dict[str, Any]:
    """Return a display-safe view of a ToolDescriptor's auth_config.

    tools/list advertises each tool's auth requirement so clients know
    what to send on tools/call. The advertisement MUST NOT include
    ``secret_ref`` / ``client_id_ref`` / ``client_secret_ref`` / the
    raw ``token`` — only the ``type`` and (optional) ``redacted_view``.

    For oauth2.0 we surface the ``token_url`` + ``scopes`` + ``audience``
    because those are public values the client needs to decide whether
    to ride on the server's oauth exchange or bring its own token.

    ``required_scopes`` (Phase 3-D0 Task 1) is added at the ToolDescriptor
    level, not on auth_config — but tools/list advertises it alongside
    the auth block so clients can pick a token that satisfies the
    requirement. ``required_scopes`` is public (not a secret).
    """
    # Pydantic models expose .model_dump() — but we hand-pick fields
    # rather than dumping wholesale so we never accidentally leak a
    # future secret-bearing field.
    type_ = getattr(auth_config, "type", "unknown")
    out: dict[str, Any] = {"type": type_}
    rv = getattr(auth_config, "redacted_view", None)
    if rv:
        out["redacted_view"] = rv
    if type_ == "oauth2.0":
        oauth = getattr(auth_config, "oauth", None)
        if oauth is not None:
            out["token_url"] = oauth.token_url
            out["scopes"] = list(oauth.scopes)
            if oauth.audience:
                out["audience"] = oauth.audience
    elif type_ == "bearer":
        # Bearer scopes are public (they declare what the token can do,
        # not the token itself). Safe to surface.
        scopes = getattr(auth_config, "scopes", None)
        if scopes:
            out["scopes"] = list(scopes)
    elif type_ == "inherit":
        inherit_from = getattr(auth_config, "inherit_from", None)
        if inherit_from:
            out["inherit_from"] = inherit_from
    return out


# ── Scope enforcement (Phase 3-D0 Task 1) ────────────────────────


def _check_required_scopes(
    descriptor: ToolDescriptor,
    auth_header: Any | None,
) -> tuple[bool, list[str], list[str]]:
    """Verify the resolved auth satisfies the tool's required_scopes.

    Returns ``(ok, required, granted)``:
      - ``ok=True`` when ``required_scopes`` is empty (no requirement)
        OR every required scope is in ``auth_header.granted_scopes``.
      - ``ok=False`` when ``required_scopes`` is non-empty AND either
        ``auth_header`` is ``None`` (auth_config was None) or the
        resolved auth doesn't carry all required scopes.

    The caller (tools_call dispatcher) raises ``MCP_AUTH_FORBIDDEN``
    when ``ok`` is False — this function is pure, no side effects, so
    it can be unit-tested in isolation.
    """
    required = list(descriptor.required_scopes)
    if not required:
        return True, required, []
    if auth_header is None:
        return False, required, []
    granted = list(getattr(auth_header, "granted_scopes", []) or [])
    required_set = set(required)
    granted_set = set(granted)
    return required_set.issubset(granted_set), required, granted


# ── Envelope helpers ────────────────────────────────────────────


def _envelope_success(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _envelope_error(
    req_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    err = MCPErrorCode.envelope(code, message, data=data)
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _parse_body(raw: bytes) -> dict[str, Any] | None:
    """Parse raw request bytes as a JSON-RPC envelope.

    Returns ``None`` on parse failure (caller should respond with
    ``-32700 Parse Error``).
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


# ── Dispatch (single code path for HTTP + in-process callers) ────


async def dispatch_tool(
    tool_name: str,
    arguments: dict[str, Any],
    request: Request,
    *,
    run_id: str | None = None,
    round_index: int | None = None,
    caller: str | None = None,
) -> dict[str, Any]:
    """Single code path for MCP tool dispatch.

    Phase 3-D2 Task 3 — extracted from the ``tools/call`` HTTP route so
    in-process callers (``_SimpleAgentDispatchHandler``) can route through
    the same scope check + auth resolution + trace emit + handler invoke
    path with zero HTTP overhead.

    Contract:
      - Raises :class:`MCPError` (or :class:`MCPAuthError` subclass) on
        any failure (unknown tool / invalid args / auth fail / scope
        forbidden / handler raised). The caller serializes the error
        envelope.
      - Returns ``{"content": result, "isError": False}`` on success.

    Caller must:
      - Set ``request.app.state.phi_redactor`` / ``mcp_secret_resolver``
        etc. (the FastAPI app does this in ``mount_mcp``).
      - Set ``request.state.context_id`` (the context_id middleware does
        this for HTTP; in-process callers set it directly).
      - Set ``request.state.run_id`` OR pass ``run_id=`` (for trace
        correlation).
      - Optionally pre-set ``request.state.auth_header`` to bypass
        auth_config resolution (in-process dev path with no bearer
        token — used by _SimpleAgentDispatchHandler).

    Trace emits (matching the original route's behavior):
      - AUTH_RESOLVED (when descriptor.auth_config is set)
      - SCOPE_CHECKED
      - TOOLS_CALL (OK or FAILED)
      - COMPLETION (OK or FAILED)
    """
    rid = run_id or getattr(request.state, "run_id", None) or "unknown"

    # Phase 3-D2.5 Part A1 — dispatch_detail accumulator.
    # Concentrated view of the dispatch lifecycle; emitted under
    # TOOLS_CALL.safe_metadata.dispatch_detail so the RunTrace UI can
    # render a single expandable panel per tool dispatch. Carries ONLY
    # display-safe fields (no raw token / Authorization / client_secret
    # / secret_ref / PHI). The existing _redact_safe_metadata scan
    # still runs before DB persist as defense-in-depth.
    dispatch_detail: dict[str, Any] = {
        "tool_name": tool_name,
        "dispatch_mode": "http" if isinstance(request, Request) else "in_process",
        "round_index": round_index,
        "caller": caller,
        "handler_ref": None,
        "input_schema_validation": "skipped",
        "phi_redaction": "skipped",
        "auth_type": None,
        "auth_resolved": False,
        "required_scopes": [],
        "granted_scopes": [],
        "scope_check": "skipped",
        "handler_status": "ok",
        "duration_ms": 0.0,
        "result_shape": None,
        "error_code": None,
        "error_stage": None,
    }
    t_dispatch_start = time.time()

    descriptor = TOOL_REGISTRY.get(tool_name)
    if descriptor is None:
        raise MCPError(
            MCPErrorCode.METHOD_NOT_FOUND,
            f"unknown tool {tool_name!r}",
            data={"allowed_tools": list(TOOL_REGISTRY)},
        )

    # ── PHI redaction ──
    redactor = getattr(request.app.state, "phi_redactor", None)
    ctx_id = getattr(request.state, "context_id", None)
    if ctx_id and redactor is None:
        dispatch_detail["phi_redaction"] = "failed"
        dispatch_detail["error_stage"] = "phi"
        dispatch_detail["error_code"] = MCPErrorCode.PHI_REDACTION_FAILED
        dispatch_detail["duration_ms"] = (time.time() - t_dispatch_start) * 1000
        emit_trace_event(
            rid, RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_dispatch_start) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "dispatch_detail": dict(dispatch_detail),
            },
        )
        raise MCPError(
            MCPErrorCode.PHI_REDACTION_FAILED,
            "contextId provided but no PHI redactor is registered",
            data={"context_id": ctx_id},
        )
    arguments = _redact_phi(arguments, redactor)
    dispatch_detail["phi_redaction"] = "passed" if redactor is not None else "skipped"

    # ── Input validation ──
    try:
        input_schema_model = _pydantic_model_from_descriptor(descriptor, "input")
        validated = input_schema_model.model_validate(arguments)
        arguments = validated.model_dump()
        dispatch_detail["input_schema_validation"] = "passed"
    except ValidationError as ve:
        dispatch_detail["input_schema_validation"] = "failed"
        dispatch_detail["error_stage"] = "schema"
        dispatch_detail["error_code"] = MCPErrorCode.INVALID_PARAMS
        dispatch_detail["duration_ms"] = (time.time() - t_dispatch_start) * 1000
        emit_trace_event(
            rid, RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_dispatch_start) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "dispatch_detail": dict(dispatch_detail),
            },
        )
        raise MCPError(
            MCPErrorCode.INVALID_PARAMS,
            f"params.arguments failed validation: {ve.error_count()} error(s)",
            data={"errors": ve.errors(include_url=False)},
        )
    except Exception as e:
        logger.debug("mcp dispatch_tool: pydantic validate skipped: %s", e)
        dispatch_detail["input_schema_validation"] = "skipped"

    # ── Auth resolution ──
    t0 = time.time()
    auth_header: Any | None = None
    if descriptor.auth_config is not None:
        auth_ctx = getattr(request.state, "mcp_run_auth_context", None) or RunAuthContext()
        resolve_kwargs: dict[str, Any] = {"context": auth_ctx}
        secret_resolver = getattr(request.app.state, "mcp_secret_resolver", None)
        if secret_resolver is not None:
            resolve_kwargs["secret_resolver"] = secret_resolver
        http_client_factory = getattr(request.app.state, "mcp_http_client_factory", None)
        if http_client_factory is not None:
            resolve_kwargs["http_client_factory"] = http_client_factory
        clock = getattr(request.app.state, "mcp_clock", None)
        if clock is not None:
            resolve_kwargs["clock"] = clock
        try:
            auth_header = await resolve_mcp_auth(
                descriptor.auth_config, **resolve_kwargs,
            )
            request.state.auth_header = auth_header
            dispatch_detail["auth_type"] = getattr(descriptor.auth_config, "type", "unknown")
            dispatch_detail["auth_resolved"] = True
            dispatch_detail["required_scopes"] = list(descriptor.required_scopes)
            dispatch_detail["granted_scopes"] = list(getattr(auth_header, "granted_scopes", []) or [])
            emit_trace_event(
                rid, RunTraceStep.AUTH_RESOLVED,
                status=RunTraceStatus.OK,
                duration_ms=(time.time() - t0) * 1000,
                safe_metadata={
                    "tool_name": tool_name,
                    "auth_type": getattr(descriptor.auth_config, "type", "unknown"),
                    "redacted_view": getattr(auth_header, "redacted_view", "") or "",
                    "granted_scopes": list(getattr(auth_header, "granted_scopes", []) or []),
                },
            )
        except MCPAuthError as e:
            dispatch_detail["auth_type"] = getattr(descriptor.auth_config, "type", "unknown")
            dispatch_detail["auth_resolved"] = False
            dispatch_detail["required_scopes"] = list(descriptor.required_scopes)
            dispatch_detail["granted_scopes"] = []
            dispatch_detail["error_stage"] = "auth"
            dispatch_detail["error_code"] = e.code
            dispatch_detail["duration_ms"] = (time.time() - t_dispatch_start) * 1000
            emit_trace_event(
                rid, RunTraceStep.AUTH_RESOLVED,
                status=RunTraceStatus.FAILED,
                duration_ms=(time.time() - t0) * 1000,
                safe_metadata={
                    "tool_name": tool_name,
                    "auth_type": getattr(descriptor.auth_config, "type", "unknown"),
                    "redacted_view": (e.data or {}).get("redacted_view", ""),
                    "mcp_error_code": (e.data or {}).get("mcp_error_code", ""),
                },
            )
            emit_trace_event(
                rid, RunTraceStep.TOOLS_CALL,
                status=RunTraceStatus.FAILED,
                duration_ms=(time.time() - t_dispatch_start) * 1000,
                safe_metadata={
                    "tool_name": tool_name,
                    "dispatch_detail": dict(dispatch_detail),
                },
            )
            raise
    else:
        # No auth_config on this tool — but the caller may have pre-set
        # request.state.auth_header (in-process dev path). Read it so the
        # scope check below can use it. Emit AUTH_RESOLVED with auth_type
        # "in-process" so the trace shows the bypass explicitly.
        auth_header = getattr(request.state, "auth_header", None)
        dispatch_detail["auth_type"] = "in-process"
        dispatch_detail["auth_resolved"] = True
        dispatch_detail["required_scopes"] = list(descriptor.required_scopes)
        dispatch_detail["granted_scopes"] = list(getattr(auth_header, "granted_scopes", []) or [])
        emit_trace_event(
            rid, RunTraceStep.AUTH_RESOLVED,
            status=RunTraceStatus.OK,
            duration_ms=(time.time() - t0) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "auth_type": "in-process",
                "redacted_view": getattr(auth_header, "redacted_view", "") or "",
                "granted_scopes": list(getattr(auth_header, "granted_scopes", []) or []),
                "note": "auth_config is None; in-process bypass (A2A route already authenticated)",
            },
        )

    # ── Scope check ──
    t_scope = time.time()
    scope_ok, scope_required, scope_granted = _check_required_scopes(
        descriptor, auth_header,
    )
    rv_for_log = (
        getattr(auth_header, "redacted_view", "") or ""
        if auth_header is not None else ""
    )
    logger.info(
        "mcp scope_check: tool=%s required=%s granted=%s ok=%s redacted_view=%r",
        tool_name, scope_required, scope_granted, scope_ok, rv_for_log,
    )
    dispatch_detail["scope_check"] = "passed" if scope_ok else "failed"
    emit_trace_event(
        rid, RunTraceStep.SCOPE_CHECKED,
        status=RunTraceStatus.OK if scope_ok else RunTraceStatus.FAILED,
        duration_ms=(time.time() - t_scope) * 1000,
        safe_metadata={
            "tool_name": tool_name,
            "required_scopes": scope_required,
            "granted_scopes": scope_granted,
            "redacted_view": rv_for_log,
        },
    )
    if not scope_ok:
        dispatch_detail["error_stage"] = "scope"
        dispatch_detail["error_code"] = MCPErrorCode.MCP_AUTH_FORBIDDEN
        dispatch_detail["duration_ms"] = (time.time() - t_dispatch_start) * 1000
        emit_trace_event(
            rid, RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_dispatch_start) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "dispatch_detail": dict(dispatch_detail),
            },
        )
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_FORBIDDEN,
            f"tool {tool_name!r} requires scopes {scope_required} "
            f"but resolved auth carries {scope_granted}",
            data={
                "tool_name": tool_name,
                "required_scopes": scope_required,
                "granted_scopes": scope_granted,
            },
            redacted_view=rv_for_log or None,
        )

    # ── Handler resolve ──
    t_dispatch = time.time()
    dispatch_detail["handler_ref"] = descriptor.handler_ref
    try:
        handler = resolve_handler(descriptor.handler_ref)
    except (ImportError, AttributeError, TypeError) as e:
        logger.exception("mcp handler resolve failed for %s", tool_name)
        dispatch_detail["handler_status"] = "failed"
        dispatch_detail["error_stage"] = "handler_resolve"
        dispatch_detail["error_code"] = MCPErrorCode.INTERNAL_ERROR
        dispatch_detail["duration_ms"] = (time.time() - t_dispatch_start) * 1000
        emit_trace_event(
            rid, RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_dispatch) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "dispatch_detail": dict(dispatch_detail),
                "error": f"handler resolve failed: {type(e).__name__}",
            },
        )
        raise MCPError(
            MCPErrorCode.INTERNAL_ERROR,
            f"handler resolve failed: {type(e).__name__}: {e}",
        )

    # ── Handler invoke ──
    t_handler = time.time()
    try:
        result = await handler(arguments, request)
    except MCPError as me:
        dispatch_detail["handler_status"] = "failed"
        dispatch_detail["error_stage"] = "handler_invoke"
        dispatch_detail["error_code"] = me.code
        dispatch_detail["duration_ms"] = (time.time() - t_handler) * 1000
        emit_trace_event(
            rid, RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_dispatch_start) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "dispatch_detail": dict(dispatch_detail),
            },
        )
        emit_trace_event(
            rid, RunTraceStep.COMPLETION,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_handler) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "error_code": me.code,
                "mcp_error_code": MCPErrorCode.name(me.code),
                "total_dispatch_ms": (time.time() - t0) * 1000,
            },
        )
        raise
    except TimeoutError as te:
        dispatch_detail["handler_status"] = "failed"
        dispatch_detail["error_stage"] = "handler_invoke"
        dispatch_detail["error_code"] = MCPErrorCode.LLM_TIMEOUT
        dispatch_detail["duration_ms"] = (time.time() - t_handler) * 1000
        emit_trace_event(
            rid, RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_dispatch_start) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "dispatch_detail": dict(dispatch_detail),
            },
        )
        emit_trace_event(
            rid, RunTraceStep.COMPLETION,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_handler) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "error": f"timeout: {te}",
                "total_dispatch_ms": (time.time() - t0) * 1000,
            },
        )
        raise MCPError(
            MCPErrorCode.LLM_TIMEOUT,
            f"tool {tool_name} timed out: {te}",
        )
    except Exception as e:
        logger.exception("mcp tool %s raised", tool_name)
        dispatch_detail["handler_status"] = "failed"
        dispatch_detail["error_stage"] = "handler_invoke"
        dispatch_detail["error_code"] = MCPErrorCode.INTERNAL_ERROR
        dispatch_detail["duration_ms"] = (time.time() - t_handler) * 1000
        emit_trace_event(
            rid, RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_dispatch_start) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "dispatch_detail": dict(dispatch_detail),
            },
        )
        emit_trace_event(
            rid, RunTraceStep.COMPLETION,
            status=RunTraceStatus.FAILED,
            duration_ms=(time.time() - t_handler) * 1000,
            safe_metadata={
                "tool_name": tool_name,
                "error": f"{type(e).__name__}: {e}",
                "total_dispatch_ms": (time.time() - t0) * 1000,
            },
        )
        raise MCPError(
            MCPErrorCode.INTERNAL_ERROR,
            f"tool {tool_name} failed: {type(e).__name__}: {e}",
        )

    # Result summary: type + top-level keys (if dict) + JSON size.
    # Full result is NOT emitted — only the shape summary, so the trace
    # stays compact and PHI-safe (the full result is in the A2A response).
    result_type = type(result).__name__
    result_keys: list[str] = []
    if isinstance(result, dict):
        result_keys = list(result.keys())[:20]
    result_size = len(json.dumps(result, ensure_ascii=False, default=str))

    dispatch_detail["handler_status"] = "ok"
    dispatch_detail["duration_ms"] = (time.time() - t_handler) * 1000
    keys_str = ", ".join(result_keys[:8])
    if isinstance(result, dict):
        if result_keys:
            dispatch_detail["result_shape"] = (
                f"{result_type}({{{keys_str}}}, size={result_size}B)"
            )
        else:
            dispatch_detail["result_shape"] = f"{result_type}(size={result_size}B)"
    else:
        dispatch_detail["result_shape"] = f"{result_type}(size={result_size}B)"

    emit_trace_event(
        rid, RunTraceStep.TOOLS_CALL,
        status=RunTraceStatus.OK,
        duration_ms=(time.time() - t_dispatch_start) * 1000,
        safe_metadata={
            "tool_name": tool_name,
            "dispatch_detail": dict(dispatch_detail),
        },
    )

    emit_trace_event(
        rid, RunTraceStep.COMPLETION,
        status=RunTraceStatus.OK,
        duration_ms=(time.time() - t_handler) * 1000,
        safe_metadata={
            "tool_name": tool_name,
            "is_error": False,
            "result_type": result_type,
            "result_keys": result_keys,
            "result_size": result_size,
            "total_dispatch_ms": (time.time() - t0) * 1000,
        },
    )

    return {"content": result, "isError": False}


# ── Middleware ──────────────────────────────────────────────────


async def _context_id_middleware(request: Request, call_next):
    """Stash ``params._meta.contextId`` on ``request.state`` for handlers."""
    if request.url.path.startswith("/mcp/v1/") and request.method == "POST":
        try:
            body = await request.body()
            envelope = _parse_body(body)
            if envelope is not None:
                params = envelope.get("params") or {}
                meta = params.get("_meta") or {}
                ctx_id = meta.get("contextId")
                request.state.context_id = ctx_id if isinstance(ctx_id, str) else None
            else:
                request.state.context_id = None
        except Exception:
            request.state.context_id = None
    return await call_next(request)


# ── Router ──────────────────────────────────────────────────────


def build_router() -> APIRouter:
    """Build the FastAPI router for the MCP endpoints.

    Pure factory — no module-level state. ``mount_mcp`` calls this and
    includes the router on the app.
    """
    router = APIRouter()

    @router.post("/mcp/v1/tools/list", operation_id="mcp_tools_list_v1")
    async def tools_list(request: Request):
        """Return all registered tool descriptors."""
        # Body is optional for tools/list; some clients send empty POST.
        req_id: Any = None
        try:
            body = await request.body()
            if body:
                envelope = _parse_body(body)
                if envelope is None:
                    return JSONResponse(_envelope_error(
                        None, MCPErrorCode.PARSE_ERROR,
                        "Invalid JSON in request body",
                    ), status_code=200)
                req_id = envelope.get("id")
                if envelope.get("jsonrpc") != "2.0":
                    return JSONResponse(_envelope_error(
                        req_id, MCPErrorCode.INVALID_REQUEST,
                        "jsonrpc must be '2.0'",
                    ), status_code=200)
                method = envelope.get("method")
                if method != "tools/list":
                    return JSONResponse(_envelope_error(
                        req_id, MCPErrorCode.METHOD_NOT_FOUND,
                        f"unknown method {method!r}",
                        data={"allowed_methods": list(ALLOWED_METHODS)},
                    ), status_code=200)

            tools_out: list[dict[str, Any]] = []
            # Phase 3-D1 Task 4: emit a tools_list trace event so the
            # RunTrace timeline surfaces the tool inventory the planner
            # was working with. ``run_id`` comes from request.state
            # (set by upstream middleware from the A2A envelope _meta).
            run_id_tl = getattr(request.state, "run_id", None) or "unknown"
            emit_trace_event(
                run_id_tl,
                RunTraceStep.TOOLS_LIST,
                status=RunTraceStatus.OK,
                safe_metadata={
                    "tool_count": len(TOOL_REGISTRY),
                    "tool_names": list(TOOL_REGISTRY.keys()),
                },
            )
            for name, desc in TOOL_REGISTRY.items():
                entry: dict[str, Any] = {
                    "name": desc.name,
                    "description": desc.description,
                    "inputSchema": desc.input_schema,
                    "outputSchema": desc.output_schema,
                    "stage": desc.stage,
                    "ref": desc.handler_ref,
                }
                # Phase 3-C1 B5 #8: advertise auth requirement (redacted).
                # _redact_auth_config strips secret_ref / client_*_ref /
                # raw token — only type + redacted_view + public oauth
                # fields survive.
                if desc.auth_config is not None:
                    entry["auth"] = _redact_auth_config(desc.auth_config)
                # Phase 3-D0 Task 1: advertise required_scopes (public,
                # not a secret) so clients know which scopes their token
                # must carry. Always present (empty list when no
                # requirement) for client-side branching simplicity.
                entry["required_scopes"] = list(desc.required_scopes)
                tools_out.append(entry)

            return JSONResponse(_envelope_success(
                req_id, {"tools": tools_out, "isError": False},
            ))
        except Exception as e:
            logger.exception("mcp tools/list failed")
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INTERNAL_ERROR,
                f"internal error: {type(e).__name__}: {e}",
            ), status_code=200)

    @router.post("/mcp/v1/tools/call", operation_id="mcp_tools_call_v1")
    async def tools_call(request: Request):
        """Dispatch one tool invocation."""
        body = await request.body()
        envelope = _parse_body(body)
        if envelope is None:
            return JSONResponse(_envelope_error(
                None, MCPErrorCode.PARSE_ERROR,
                "Invalid JSON in request body",
            ), status_code=200)

        req_id = envelope.get("id")
        if envelope.get("jsonrpc") != "2.0":
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INVALID_REQUEST,
                "jsonrpc must be '2.0'",
            ), status_code=200)

        method = envelope.get("method")
        if method != "tools/call":
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.METHOD_NOT_FOUND,
                f"unknown method {method!r}",
                data={"allowed_methods": list(ALLOWED_METHODS)},
            ), status_code=200)

        params = envelope.get("params") or {}
        if not isinstance(params, dict):
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INVALID_REQUEST,
                "params must be an object",
            ), status_code=200)

        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        if not isinstance(tool_name, str) or not tool_name:
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INVALID_PARAMS,
                "params.name must be a non-empty string",
            ), status_code=200)

        if not isinstance(arguments, dict):
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INVALID_PARAMS,
                "params.arguments must be an object",
            ), status_code=200)

        run_id_t = getattr(request.state, "run_id", None) or req_id or "unknown"

        # ── Dispatch via the shared code path (Phase 3-D2 Task 3) ──
        # Both the HTTP tools/call route and the in-process
        # _SimpleAgentDispatchHandler call dispatch_tool() so scope check
        # + auth resolution + trace emit + handler invoke share a single
        # implementation. Errors are raised as MCPError (or the
        # MCPAuthError subclass); we serialize them into JSON-RPC error
        # envelopes here.
        try:
            result = await dispatch_tool(
                tool_name, arguments, request, run_id=run_id_t,
            )
            return JSONResponse(_envelope_success(req_id, result))
        except MCPError as e:
            return JSONResponse(_envelope_error(
                req_id, e.code, e.message, data=e.data,
            ), status_code=200)

    return router


# ── Pydantic resolution (for inputSchema validation) ────────────


def _pydantic_model_from_descriptor(
    descriptor: ToolDescriptor,
    kind: str,
) -> Any:
    """Resolve the Pydantic model class for a tool's input/output schema.

    M2 keeps the Pydantic models in :mod:`app.icoder.mcp.tool_registry`.
    We re-import them here by name (not the descriptor itself) so the
    registry remains the SSOT and the server doesn't need to know the
    internal class names — just the convention that the model class name
    matches the input/output field in the descriptor.

    For M2 we hard-map by tool name (simpler and more honest than
    reflective resolution):
    """
    from . import tool_registry as _reg
    table = {
        ("search_icd", "input"): _reg.SearchIcdInput,
        ("search_icd", "output"): _reg.SearchIcdOutput,
        ("verify_code", "input"): _reg.VerifyCodeInput,
        ("verify_code", "output"): _reg.VerifyCodeOutput,
        ("get_differentiation_hint", "input"): _reg.GetDifferentiationHintInput,
        ("get_differentiation_hint", "output"): _reg.GetDifferentiationHintOutput,
        ("rerank_codes", "input"): _reg.RerankCodesInput,
        ("rerank_codes", "output"): _reg.RerankCodesOutput,
        ("calibrate_confidence", "input"): _reg.CalibrateConfidenceInput,
        ("calibrate_confidence", "output"): _reg.CalibrateConfidenceOutput,
        # Phase 3-D2 Task 3 — 3 agent-backed MCP tools
        ("validate_codes", "input"): _reg.ValidateCodesInput,
        ("validate_codes", "output"): _reg.ValidateCodesOutput,
        ("evaluate_compliance", "input"): _reg.EvaluateComplianceInput,
        ("evaluate_compliance", "output"): _reg.EvaluateComplianceOutput,
        ("check_documentation_gaps", "input"): _reg.CheckDocumentationGapsInput,
        ("check_documentation_gaps", "output"): _reg.CheckDocumentationGapsOutput,
    }
    model = table.get((descriptor.name, kind))
    if model is None:
        raise LookupError(f"no Pydantic model for {descriptor.name} {kind}")
    return model


# ── Mount ────────────────────────────────────────────────────────


def mount_mcp(
    app: FastAPI,
    *,
    strategy: Any,
    phi_redactor: Any | None = None,
    agent_pack_tools: list[dict] | None = None,
    secret_resolver: Any | None = None,
    http_client_factory: Any | None = None,
    clock: Any | None = None,
) -> None:
    """Mount the MCP router on a FastAPI app.

    Args:
        app: the FastAPI application (typically the main iCoDer app).
        strategy: a :class:`MedCodERStrategy` instance (M1). Stored on
            ``app.state.medcoder_strategy`` so handlers can read it via
            ``request.app.state.medcoder_strategy``.
        phi_redactor: optional :class:`PHIRedactor` instance. When
            ``None``, MCP tools accept any client without context_id but
            will reject (with ``-32004``) any client that DOES supply a
            context_id — fail-closed semantics.
        agent_pack_tools: optional ``tools`` array from the Agent Pack
            JSON. When provided, the boot-time assertion runs.
            Skipping it (e.g., in isolated unit tests) is allowed.
        secret_resolver: optional callable ``secret_ref -> str`` for
            bearer / oauth2.0 token resolution. When ``None``, the
            resolver falls back to the real CredentialVault
            (``app.services.credential_vault.vault.resolve``).
        http_client_factory: optional ``() -> httpx.AsyncClient`` factory
            for oauth2.0 token exchange. Tests inject a MockTransport-backed
            client; production lets the resolver construct a default client.
        clock: optional ``() -> float`` for oauth2.0 token expiry checks.
            Tests inject a fake to drive cache hit / miss / refresh.

    Returns:
        None. The router is mounted as a side effect.
    """
    # Store strategy + (optional) redactor + (optional) auth resolver
    # hooks on app.state so handlers can read them via ``request.app.state``.
    # No new lifespan state.
    app.state.medcoder_strategy = strategy
    if phi_redactor is not None:
        app.state.phi_redactor = phi_redactor
    if secret_resolver is not None:
        app.state.mcp_secret_resolver = secret_resolver
    if http_client_factory is not None:
        app.state.mcp_http_client_factory = http_client_factory
    if clock is not None:
        app.state.mcp_clock = clock

    # TD-004 fix: idempotent mount — if the MCP router is already mounted
    # (e.g. lifespan re-ran across TestClient sessions), skip re-mounting
    # to avoid duplicate operation_id warnings.
    if getattr(app.state, "_mcp_mounted", False):
        return

    # Install the context_id middleware (idempotent — FastAPI dedupes by
    # function identity, but we wrap in a closure so each mount call gets
    # its own middleware function reference).
    #
    # E1.1 (2026-06-26): if the middleware was already installed at
    # module-load time (see app/main.py), skip — Starlette eagerly builds
    # ``middleware_stack`` on the first ``__call__`` (which is the lifespan
    # startup scope), and ``app.add_middleware()`` raises
    # ``RuntimeError("Cannot add middleware after an application has
    # started")`` after that point.
    if not getattr(app.state, "_mcp_context_id_middleware_installed", False):
        app.middleware("http")(_context_id_middleware)
        app.state._mcp_context_id_middleware_installed = True

    # Boot-time assertion: TOOL_REGISTRY matches the Agent Pack's tools list.
    if agent_pack_tools is not None:
        try:
            assert_tool_registry_matches_agent_pack(agent_pack_tools)
        except AssertionError as e:
            logger.error("MCP mount: %s", e)
            raise

    router = build_router()
    app.include_router(router)
    app.state._mcp_mounted = True
    logger.info(
        "MCP server mounted at /mcp/v1/tools/{list,call} with %d tools",
        len(TOOL_REGISTRY),
    )


__all__ = [
    "mount_mcp",
    "build_router",
    "dispatch_tool",
    "resolve_handler",
    "ALLOWED_METHODS",
    "_redact_phi",
    "_check_required_scopes",
]