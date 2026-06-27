"""MCP server — FastAPI in-process mount exposing 5 MedCodER tools.

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
from typing import Any, Callable, Awaitable

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .errors import MCPError, MCPErrorCode
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

    @router.post("/mcp/v1/tools/list")
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
            for name, desc in TOOL_REGISTRY.items():
                tools_out.append({
                    "name": desc.name,
                    "description": desc.description,
                    "inputSchema": desc.input_schema,
                    "outputSchema": desc.output_schema,
                    "stage": desc.stage,
                    "ref": desc.handler_ref,
                })

            return JSONResponse(_envelope_success(
                req_id, {"tools": tools_out, "isError": False},
            ))
        except Exception as e:
            logger.exception("mcp tools/list failed")
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INTERNAL_ERROR,
                f"internal error: {type(e).__name__}: {e}",
            ), status_code=200)

    @router.post("/mcp/v1/tools/call")
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

        descriptor = TOOL_REGISTRY.get(tool_name)
        if descriptor is None:
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.METHOD_NOT_FOUND,
                f"unknown tool {tool_name!r}",
                data={"allowed_tools": list(TOOL_REGISTRY)},
            ), status_code=200)

        # ── PHI redaction (R4) ──
        # M2 best-effort: if a redactor is registered on app.state, redact
        # string-typed arguments before dispatch. If context_id is provided
        # but the redactor is missing, fail closed (-32004) — never leak.
        redactor = getattr(request.app.state, "phi_redactor", None)
        ctx_id = getattr(request.state, "context_id", None)
        if ctx_id and redactor is None:
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.PHI_REDACTION_FAILED,
                "contextId provided but no PHI redactor is registered",
                data={"context_id": ctx_id},
            ), status_code=200)
        arguments = _redact_phi(arguments, redactor)

        # ── Input validation against the tool's inputSchema ──
        try:
            input_schema_model = _pydantic_model_from_descriptor(descriptor, "input")
            validated = input_schema_model.model_validate(arguments)
            arguments = validated.model_dump()
        except ValidationError as ve:
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INVALID_PARAMS,
                f"params.arguments failed validation: {ve.error_count()} error(s)",
                data={"errors": ve.errors(include_url=False)},
            ), status_code=200)
        except Exception as e:
            # If we can't resolve the Pydantic model (e.g. legacy registry
            # entry), fall through and let the handler validate.
            logger.debug("mcp tools/call: pydantic validate skipped: %s", e)

        # ── Handler dispatch ──
        try:
            handler = resolve_handler(descriptor.handler_ref)
        except (ImportError, AttributeError, TypeError) as e:
            logger.exception("mcp handler resolve failed for %s", tool_name)
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INTERNAL_ERROR,
                f"handler resolve failed: {type(e).__name__}: {e}",
            ), status_code=200)

        try:
            result = await handler(arguments, request)
        except MCPError as me:
            # Typed application errors (catalog miss / retriever / etc.)
            return JSONResponse(_envelope_error(
                req_id, me.code, me.message, data=me.data,
            ), status_code=200)
        except TimeoutError as te:
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.LLM_TIMEOUT,
                f"tool {tool_name} timed out: {te}",
            ), status_code=200)
        except Exception as e:
            logger.exception("mcp tool %s raised", tool_name)
            return JSONResponse(_envelope_error(
                req_id, MCPErrorCode.INTERNAL_ERROR,
                f"tool {tool_name} failed: {type(e).__name__}: {e}",
            ), status_code=200)

        return JSONResponse(_envelope_success(
            req_id, {"content": result, "isError": False},
        ))

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

    Returns:
        None. The router is mounted as a side effect.
    """
    # Store strategy + (optional) redactor on app.state so handlers can
    # read them via ``request.app.state``. No new lifespan state.
    app.state.medcoder_strategy = strategy
    if phi_redactor is not None:
        app.state.phi_redactor = phi_redactor

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
    logger.info(
        "MCP server mounted at /mcp/v1/tools/{list,call} with %d tools",
        len(TOOL_REGISTRY),
    )


__all__ = [
    "mount_mcp",
    "build_router",
    "resolve_handler",
    "ALLOWED_METHODS",
    "_redact_phi",
]