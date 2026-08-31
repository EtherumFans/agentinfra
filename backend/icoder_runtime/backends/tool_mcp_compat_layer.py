"""ToolMCPCompatLayer — bridges provider-native tool calls to MCP.

Phase 4-A Task 7 (2026-07-07): the contract layer between
``LLMWithToolsProvider`` and the existing MCP server registry.

Why this layer exists (per
``ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md`` Item 3):

  LLMWithToolsProvider (e.g. DeepSeek function-calling)
    │
    │  provider-native tool schema (DeepSeek/OpenAI function JSON)
    │
    ▼
  ToolMCPCompatLayer.provider_to_mcp(tool_call) → ToolCallRequest
    │
    │  MCP/JSON-RPC 2.0 (tools/call)
    │
    ▼
  MCP Server Registry (``app.icoder.mcp.server.dispatch_tool``)
    │
    ├── verify tool        → MedicalCodingRuleSet.verify()
    ├── guidelines tool    → CodingGuidelinesKB.search()
    ├── explore tool       → CodeCatalogExplore.search()
    ├── search tool        → DocumentationSearch.search()
    └── icoder_* tools     → business workbench endpoints

Hard requirements (per Task 7 spec):
  1. Reuse existing MCP tool registry — do NOT shadow ``dispatch_tool``.
  2. Never bypass ``dispatch_tool`` — every tool call routes through
     it so scope checks + auth resolution + RunTrace emission remain
     uniform.
  3. All tool calls enter RunTrace (via ``dispatch_tool`` which already
     emits ``TOOLS_CALL``).
  4. Never leak token / secret / PHI — only ``redacted_view`` is
     surfaced in ``ToolCallRecord``.
  5. Support DeepSeek/OpenAI function-calling adaptation (placeholder
     for Phase 4-B — the current skeleton accepts raw dicts).

The layer is a SKELETON in Phase 4-A — it implements the contract
correctly but only routes one tool-call shape (provider-native dict →
MCP ``tools/call``). Provider-specific schema translation (e.g.
DeepSeek's ``function`` JSON → MCP ``input_schema``) ships in
Phase 4-B with the first real LLM-with-tools migration.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .contracts import AgentRunContext, ToolCallRecord

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRequest:
    """MCP ``tools/call`` request built from a provider-native tool call.

    Mirrors the shape that ``app.icoder.mcp.server.dispatch_tool``
    expects: ``tool_name`` + ``arguments`` + optional ``run_id``.
    """

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""


@dataclass
class ToolCallResponse:
    """MCP ``tools/call`` response, projected for the provider.

    ``content`` is the handler return value (already JSON-serializable);
    ``is_error`` indicates the handler raised or returned an error
    envelope; ``error_code`` / ``error_message`` populated when
    ``is_error=True``.
    """

    tool_name: str
    content: Any = None
    is_error: bool = False
    error_code: str = ""
    error_message: str = ""
    duration_ms: int = 0
    scope_granted: list[str] = field(default_factory=list)
    redacted_view: str = ""

    def to_provider_result(self) -> dict[str, Any]:
        """Project to a provider-friendly dict for tool-result loopback.

        LLM providers (DeepSeek/OpenAI) expect the tool result as a
        JSON-serializable dict. We surface ``content`` plus a thin
        envelope so the provider can mark the result role.
        """
        return {
            "tool_name": self.tool_name,
            "content": self.content,
            "is_error": self.is_error,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


class ToolMCPCompatLayer:
    """Translates provider-native tool calls to/from MCP.

    Construction is cheap (no I/O). The layer is wired to the existing
    ``app.icoder.mcp.server.dispatch_tool`` function — at runtime it
    builds a ``ToolCallRequest`` and calls ``dispatch_tool`` directly.

    The class is a SKELETON — the public methods are stable but
    provider-specific schema translation (DeepSeek function-calling
    JSON → MCP input_schema) ships in Phase 4-B. For Phase 4-A the
    layer accepts already-MCP-shaped dicts and ensures the routing
    goes through ``dispatch_tool`` (Task 7 requirement #2: "不绕过
    dispatch_tool").
    """

    def __init__(
        self,
        *,
        dispatch_tool_fn: Any = None,
        list_tools_fn: Any = None,
    ) -> None:
        # Lazy — defer the import to first call so module import is cheap.
        self._dispatch_tool_fn = dispatch_tool_fn
        self._list_tools_fn = list_tools_fn

    # ── Provider → MCP ────────────────────────────────────────────

    def provider_to_mcp(
        self, tool_call: dict[str, Any], provider_id: str = "",
    ) -> ToolCallRequest:
        """Build a MCP ``tools/call`` request from a provider-native tool call.

        Accepts both shapes the LLM ecosystem uses:

          - OpenAI function-calling: ``{"name": "...", "arguments": {...}}``
          - MCP-native: ``{"tool": "...", "input": {...}}`` (legacy)

        Strips out anything that isn't display-safe (PHI / tokens) —
        the MCP dispatch will redact again, but defense-in-depth.
        """
        if not isinstance(tool_call, dict):
            raise ValueError(
                f"provider_to_mcp: tool_call must be a dict, got {type(tool_call).__name__}"
            )
        name = (
            tool_call.get("name")
            or tool_call.get("tool")
            or tool_call.get("tool_name")
            or ""
        )
        if not isinstance(name, str) or not name:
            raise ValueError(
                "provider_to_mcp: tool_call missing 'name' (or 'tool'/'tool_name')"
            )
        args = (
            tool_call.get("arguments")
            or tool_call.get("input")
            or tool_call.get("args")
            or {}
        )
        if not isinstance(args, dict):
            raise ValueError(
                f"provider_to_mcp: arguments must be a dict, got {type(args).__name__}"
            )
        run_id = tool_call.get("run_id", "") or ""
        # Defensive: strip any obvious secret keys before handing off.
        args = _strip_secret_keys(args, provider_id)
        # Provider schemas commonly expose ``query`` while the canonical MCP
        # search_icd contract names the same value ``emr_text``. Normalize the
        # alias before validation without bypassing dispatch_tool.
        if name == "search_icd" and "emr_text" not in args:
            query = args.pop("query", None)
            if isinstance(query, str) and query.strip():
                args["emr_text"] = query
        return ToolCallRequest(
            tool_name=name,
            arguments=args,
            run_id=str(run_id),
        )

    # ── MCP → provider ────────────────────────────────────────────

    def mcp_to_provider(
        self, mcp_resp: dict[str, Any], provider_id: str = "",
    ) -> ToolCallResponse:
        """Project a MCP dispatch result to a provider-friendly response.

        ``dispatch_tool`` returns ``{"content": <handler result>, "isError": bool}``
        (plus optional ``error_code`` / ``error_message`` when the
        handler raised or the route returned an error envelope).
        """
        if not isinstance(mcp_resp, dict):
            return ToolCallResponse(
                tool_name="",
                is_error=True,
                error_code="INVALID_RESPONSE",
                error_message=f"mcp_resp must be a dict, got {type(mcp_resp).__name__}",
            )
        is_error = bool(mcp_resp.get("isError", False))
        content = mcp_resp.get("content")
        error_code = str(mcp_resp.get("error_code") or mcp_resp.get("code") or "")
        error_message = str(mcp_resp.get("error_message") or mcp_resp.get("message") or "")
        return ToolCallResponse(
            tool_name=str(mcp_resp.get("tool_name", "")),
            content=content,
            is_error=is_error,
            error_code=error_code,
            error_message=error_message,
            duration_ms=int(mcp_resp.get("duration_ms", 0) or 0),
            scope_granted=list(mcp_resp.get("scope_granted") or []),
            redacted_view=str(mcp_resp.get("redacted_view") or ""),
        )

    # ── Tool discovery + scope validation ─────────────────────────

    def list_available_tools(
        self,
        agent_id: str = "",
        provider_id: str = "",
        tool_scope: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return provider-native tool schemas for tools the provider may call.

        Filters by ``tool_scope`` (the agent's whitelist from
        ``backend_config.tools.scope``). Tools NOT in the scope are
        omitted — this is how Corti's "search forbidden for
        Compliance Guardrail" pattern is enforced (Task 7 requirement
        #4: "不泄露 token/secret/PHI" — listing forbidden tools would
        leak capability surface area).
        """
        all_tools = self._list_all_tools()
        if tool_scope is None:
            return all_tools
        scope_set = set(tool_scope)
        return [
            t for t in all_tools
            if t.get("name") in scope_set
        ]

    def validate_tool_scope(
        self,
        tool_scope: list[str],
        *,
        mandatory: list[str] | None = None,
        forbidden: list[str] | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate a tool-scope config from ``backend_config.tools``.

        Returns ``(ok, errors)``. Used by ``icoder pack validate`` and
        at runtime by ``LLMWithToolsProvider.invoke`` to enforce:

          - ``mandatory ⊆ tool_scope`` (Corti Code Validation: verify + guidelines)
          - ``forbidden ∩ tool_scope = ∅`` (Corti Compliance Guardrail: search forbidden)
        """
        errors: list[str] = []
        scope_set = set(tool_scope)
        if mandatory:
            missing = set(mandatory) - scope_set
            if missing:
                errors.append(
                    f"mandatory tools missing from scope: {sorted(missing)}"
                )
        if forbidden:
            leaked = set(forbidden) & scope_set
            if leaked:
                errors.append(
                    f"forbidden tools present in scope: {sorted(leaked)}"
                )
        return (not errors), errors

    # ── The actual dispatch (routing through ``dispatch_tool``) ──

    async def call(
        self,
        tool_call: dict[str, Any],
        ctx: AgentRunContext,
        *,
        provider_id: str = "",
        request: Any = None,
        round_index: int | None = None,
        caller: str | None = None,
    ) -> ToolCallResponse:
        """Execute a provider-native tool call by routing through MCP.

        Per Task 7 requirement #2: this NEVER calls a handler directly
        — it always routes through ``app.icoder.mcp.server.dispatch_tool``
        so scope / auth / RunTrace emission stay uniform.

        ``request`` is the FastAPI ``Request`` object that
        ``dispatch_tool`` expects (it reads ``request.app.state`` for
        phi_redactor / mcp_secret_resolver and ``request.state`` for
        context_id / run_id / auth_header). In-process callers construct
        a lightweight stand-in (see ``app.main.py:_handle_simple`` for
        the established pattern).
        """
        req = self.provider_to_mcp(tool_call, provider_id=provider_id)
        dispatch = self._get_dispatch_fn()
        if dispatch is None:
            return ToolCallResponse(
                tool_name=req.tool_name,
                is_error=True,
                error_code="DISPATCH_UNAVAILABLE",
                error_message="dispatch_tool function not resolvable",
            )
        if request is None:
            return ToolCallResponse(
                tool_name=req.tool_name,
                is_error=True,
                error_code="NO_REQUEST",
                error_message=(
                    "ToolMCPCompatLayer.call requires a `request` object "
                    "so dispatch_tool can read app.state. Pass the FastAPI "
                    "Request (or a stand-in) — see app.main.py:_handle_simple."
                ),
            )
        t0 = time.perf_counter()
        try:
            result = await dispatch(
                req.tool_name,
                req.arguments,
                request,
                run_id=req.run_id or ctx.run_id,
                round_index=round_index,
                caller=caller,
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)
            # dispatch_tool returns {"content": ..., "isError": bool}
            if not isinstance(result, dict):
                return ToolCallResponse(
                    tool_name=req.tool_name,
                    is_error=True,
                    error_code="INVALID_DISPATCH_RESULT",
                    error_message=f"dispatch_tool returned {type(result).__name__}",
                    duration_ms=duration_ms,
                )
            # Stamp latency on the projected response.
            resp = self.mcp_to_provider(result, provider_id=provider_id)
            resp.tool_name = req.tool_name
            resp.duration_ms = duration_ms or resp.duration_ms
            return resp
        except Exception as e:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "ToolMCPCompatLayer.call(%s) raised error_type=%s",
                req.tool_name, type(e).__name__,
            )
            return ToolCallResponse(
                tool_name=req.tool_name,
                is_error=True,
                error_code=type(e).__name__,
                error_message=f"tool_execution_failed:{type(e).__name__}",
                duration_ms=duration_ms,
            )

    def to_tool_call_record(
        self, call: ToolCallResponse, arguments: dict[str, Any] | None = None,
    ) -> ToolCallRecord:
        """Project a ``ToolCallResponse`` to a ``ToolCallRecord`` for
        ``OutputContract.tool_calls`` (consumed by RunTrace + frontend).
        """
        from .contracts import ToolCallRecord as _Record
        return _Record(
            tool_name=call.tool_name,
            arguments=dict(arguments or {}),
            result=call.content,
            duration_ms=call.duration_ms,
            error=(call.error_message or None) if call.is_error else None,
            scope_granted=list(call.scope_granted),
        )

    # ── Internal: lazy lookup of dispatch_tool + tool list ────────

    def _get_dispatch_fn(self) -> Any:
        if self._dispatch_tool_fn is not None:
            return self._dispatch_tool_fn
        try:
            from app.icoder.mcp.server import dispatch_tool
            self._dispatch_tool_fn = dispatch_tool
            return dispatch_tool
        except Exception as e:
            logger.error(
                "could not import dispatch_tool error_type=%s",
                type(e).__name__,
            )
            return None

    def _list_all_tools(self) -> list[dict[str, Any]]:
        if self._list_tools_fn is not None:
            try:
                return list(self._list_tools_fn() or [])
            except Exception as e:
                logger.warning("list_tools_fn raised: %s", e)
                return []
        try:
            from app.icoder.mcp.tool_registry import TOOL_REGISTRY
            out: list[dict[str, Any]] = []
            for name, descriptor in (TOOL_REGISTRY or {}).items():
                if hasattr(descriptor, "to_dict"):
                    out.append(descriptor.to_dict())
                elif isinstance(descriptor, dict):
                    out.append({"name": name, **descriptor})
                else:
                    out.append({"name": name, "description": str(descriptor)[:200]})
            return out
        except Exception as e:
            logger.debug("TOOL_REGISTRY lookup failed: %s", e)
            return []


# ── Helpers ────────────────────────────────────────────────────────────


_KNOWN_SECRET_KEYS: frozenset[str] = frozenset({
    "token", "secret", "client_secret", "authorization",
    "password", "refresh_token", "access_token", "api_key",
    "bearer_token", "raw_token",
})


def _strip_secret_keys(args: dict[str, Any], provider_id: str) -> dict[str, Any]:
    """Defense-in-depth: blank obvious secret keys before MCP dispatch.

    The MCP layer will redact again, but stripping here means a
    misbehaving LLM can't exfiltrate via tool arguments.
    """
    if not args:
        return {}
    out: dict[str, Any] = {}
    for k, v in args.items():
        if any(s in k.lower() for s in _KNOWN_SECRET_KEYS):
            logger.warning(
                "ToolMCPCompatLayer: stripping secret key %r from tool args (provider=%s)",
                k, provider_id,
            )
            out[k] = "[REDACTED]"
            continue
        out[k] = v
    return out


__all__ = [
    "ToolMCPCompatLayer",
    "ToolCallRequest",
    "ToolCallResponse",
]
