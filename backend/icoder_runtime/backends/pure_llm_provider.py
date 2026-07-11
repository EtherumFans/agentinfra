"""PureLLMProvider — LLM backend with no tool calls (skeleton).

Phase 4-A Task 5 (2026-07-07): skeleton for the Corti Note
Completeness Agent pattern (Probe 5/6: 0 tools, 6-section Markdown
output, $0.029672/msg).

This is a SKELETON — it implements the ``AgentBackendProvider``
interface correctly but does NOT yet wire a real LLM. The
``LLMGateway`` / DeepSeek wiring ships in Phase 4-B with the first
real agent migration (Note Completeness). For Phase 4-A the
provider is testable with a mock LLM client (see
``tests/unit/icoder/backends/test_pure_llm_provider.py``).

Provider metadata:
  - ``provider_id = "icoder.pure-llm.v1"``
  - ``backend_type = "pure_llm"``
  - ``supports_tool_calling = False``
  - ``supports_streaming = True``  (skeleton placeholder)
  - ``deterministic = False``

Hard rules (per Task 5 spec):
  1. Support ``system_prompt`` + ``user_input``.
  2. Support streaming interface placeholder.
  3. Support timeout / error envelope.
  4. Support markdown output.
  5. Temporarily can use only the existing ``LLMGateway`` / DeepSeek.
  6. Do NOT migrate Note Completeness yet — this is skeleton + tests.

The provider NEVER sees raw PHI — ``AgentRunContext.redacted_input``
is the only user-side text it reads (per architecture Item 9: "PHI
redaction applied at AgentRunContext construction, before any
provider sees data").
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Protocol

from .contracts import (
    AgentBackendProvider,
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    BackendType,
    ProviderCapability,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


# ── LLMClient protocol (injected, not hardcoded) ──────────────────────


class LLMClient(Protocol):
    """Minimal LLM client protocol.

    Phase 4-A: the only concrete implementation is
    ``app.icoder.core.llm_gateway.LLMGateway`` (DeepSeek V4). Phase 4-B
    will add OpenAI / Qwen / custom endpoint clients.

    The provider does NOT import ``LLMGateway`` directly — the caller
    injects it. This avoids hardcoding DeepSeek (Task 5 requirement
    #5: "暂时可以只接现有 LLMGateway / DeepSeek provider" — we wire
    DeepSeek by default but don't bake the import path into the
    provider class).

    Phase 4-C: ``tools`` param added for LLMWithToolsProvider
    tool-calling. PureLLMProvider always passes ``tools=None``.
    """

    async def complete(
        self,
        *,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
        tools: list[dict[str, Any]] | None = None,
    ) -> "LLMResponse":
        """Single-shot completion (non-streaming).

        ``tools`` is an OpenAI-style function-calling tool schema list.
        Providers that don't support tool-calling should accept and
        ignore the param (never raise). The returned ``LLMResponse.tool_calls``
        is an empty list when the LLM declines to call any tool.
        """
        ...

    def stream(
        self,
        *,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
    ) -> AsyncIterator["LLMChunk"]:
        """Streaming completion. Yields ``LLMChunk`` until done."""
        ...


class LLMResponse:
    """Result of a non-streaming LLM call.

    Phase 4-C: ``tool_calls`` carries the provider-native tool call
    list (OpenAI shape ``[{"id": ..., "type": "function",
    "function": {"name": ..., "arguments": "<json>"}}]``) when the LLM
    requests tool calls. Empty list when no tool calls were requested
    or when the provider doesn't support tool-calling.
    """

    def __init__(
        self, *, text: str, tool_calls: list[dict[str, Any]] | None = None,
        finish_reason: str = "",
        latency_ms: int = 0, cost_usd: float | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.text = text
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.latency_ms = latency_ms
        self.cost_usd = cost_usd
        self.raw = raw or {}


class LLMChunk:
    """One streaming chunk from an LLM call."""

    def __init__(self, *, delta: str = "", finish_reason: str = "") -> None:
        self.delta = delta
        self.finish_reason = finish_reason


# ── Provider ───────────────────────────────────────────────────────────


class PureLLMProvider:
    """Pure LLM backend with no tool calls.

    Skeleton (Phase 4-A): the ``invoke`` path is fully wired with a
    pluggable ``LLMClient``; the ``stream`` path emits a placeholder
    event sequence so callers can verify the streaming contract
    without a real LLM.
    """

    provider_id: str = "icoder.pure-llm.v1"
    backend_type: BackendType = "pure_llm"
    supports_tool_calling: bool = False
    supports_streaming: bool = True
    deterministic: bool = False

    _OUTPUT_CONTRACT_REF: str = "icoder/PureLLMOutput/v1"

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        llm_gateway: Any = None,
        gateway_provider: str = "",
        default_temperature: float = 0.0,
        default_max_tokens: int | None = None,
    ) -> None:
        # Priority: explicit llm_client > llm_gateway (wrapped via
        # LLMGatewayAdapter) > lazy-resolve at invoke time via
        # ``registry.get_gateway()`` (set by app/main.py at startup).
        if llm_client is not None:
            self._llm_client = llm_client
        elif llm_gateway is not None:
            from .llm_gateway_adapter import LLMGatewayAdapter
            self._llm_client = LLMGatewayAdapter(llm_gateway, provider=gateway_provider)
        else:
            self._llm_client = None
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    # ── AgentBackendProvider protocol ─────────────────────────────

    async def health(self) -> ProviderHealth:
        client = self._resolve_client()
        if client is None:
            return ProviderHealth(
                state="degraded",
                details={"note": "no llm_client and no gateway wired via registry"},
            )
        return ProviderHealth(
            state="ok",
            details={"provider_id": self.provider_id,
                     "backend_type": self.backend_type},
        )

    async def invoke(
        self, req: BackendRequest, ctx: AgentRunContext,
        *,
        request: Any = None,
    ) -> BackendResponse:
        """Single-shot LLM completion.

        Builds ``system_prompt + user_input`` from the request and
        context, calls ``LLMClient.complete``, and normalizes to a
        ``BackendResponse`` with ``markdown`` populated.

        Error envelope (Task 5 requirement #3): on timeout or LLM
        failure, returns a ``BackendResponse(status='fail',
        finish_state='failed')`` with the error class+message in
        ``finish_reason`` — never raises to the caller.
        """
        t0 = time.perf_counter()
        system_prompt = req.system_prompt or _extract_system_prompt(ctx)
        user_input = req.user_input or ctx.redacted_input or _extract_user_input(req)

        if not user_input:
            return self._fail(
                "empty user_input — PureLLMProvider needs req.user_input "
                "or ctx.redacted_input", t0,
            )

        client = self._resolve_client()
        if client is None:
            # Phase 4-A skeleton path: no llm_client AND no gateway wired
            # via registry. Return a deterministic placeholder so tests
            # can verify the contract without external calls. Phase 4-B
            # production code should never hit this — app/main.py sets
            # the gateway lookup at startup.
            placeholder_text = _placeholder_markdown(user_input, system_prompt)
            latency_ms_placeholder = int((time.perf_counter() - t0) * 1000)
            self._emit_backend_metadata(
                ctx, latency_ms_placeholder, "complete", fallback_used=False,
            )
            return BackendResponse(
                status="complete",
                summary="PureLLMProvider skeleton: placeholder response (no llm_client wired).",
                markdown=placeholder_text,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                latency_ms=latency_ms_placeholder,
                finish_state="completed",
                raw_provider_response={
                    "skeleton": True,
                    "system_prompt_chars": len(system_prompt),
                    "user_input_chars": len(user_input),
                    "placeholder_text_chars": len(placeholder_text),
                },
                evidence_refs=[],
                trace_refs=[ctx.run_id],
            )

        try:
            resp = await client.complete(
                system_prompt=system_prompt,
                user_input=user_input,
                temperature=self._default_temperature,
                max_tokens=self._default_max_tokens,
                timeout_seconds=req.timeout_seconds,
            )
        except NotImplementedError as e:
            return self._fail(f"llm_client.complete not implemented: {e}", t0)
        except TimeoutError as e:
            return self._fail(f"llm timeout: {e}", t0)
        except Exception as e:
            logger.exception("PureLLMProvider.invoke llm call failed")
            return self._fail(f"llm error: {type(e).__name__}: {e}", t0)

        latency_ms = resp.latency_ms or int((time.perf_counter() - t0) * 1000)
        status: ProviderStatus = _parse_status_from_markdown(resp.text)
        # Phase 4-B Step 2(b): emit backend_metadata RunTrace event so
        # the frontend BackendProviderSummary renders with real data.
        # Detect degraded LLM responses (gateway returned a mock fallback)
        # so the trace shows fallback_used=True.
        finish_reason_str = (resp.finish_reason or "") if isinstance(resp.finish_reason, str) else ""
        degraded = finish_reason_str.startswith("degraded")
        self._emit_backend_metadata(
            ctx, latency_ms, status, fallback_used=degraded,
        )
        return BackendResponse(
            status=status,
            summary=_extract_first_paragraph(resp.text),
            markdown=resp.text,
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            latency_ms=latency_ms,
            cost_usd=resp.cost_usd,
            finish_state="completed",
            finish_reason=resp.finish_reason or None,
            raw_provider_response=resp.raw,
            evidence_refs=[],
            trace_refs=[ctx.run_id],
        )

    async def stream(
        self, req: BackendRequest, ctx: AgentRunContext,
    ) -> AsyncIterator[Any]:
        """Streaming LLM completion (skeleton).

        Phase 4-A: emits a 3-event placeholder sequence so callers
        that use ``stream()`` get a uniform contract:

          1. ``{"step": "backend_invoked", "payload": BackendResponse}``
          2. ``{"step": "output_chunk", "payload": {"delta": str}}``
          3. ``{"step": "finished", "payload": {"state": "completed"}}``

        Phase 4-B will replace this with real LLM streaming (DeepSeek
        SSE) — the event shape stays the same so frontend code doesn't
        change.
        """
        resp = await self.invoke(req, ctx)
        yield {"step": "backend_invoked", "payload": resp}
        # Stream the markdown in 200-char chunks (placeholder).
        text = resp.markdown or ""
        for i in range(0, len(text), 200):
            yield {"step": "output_chunk", "payload": {"delta": text[i:i + 200]}}
        yield {"step": "finished", "payload": {"state": resp.finish_state}}

    def output_contract(self) -> str:
        return self._OUTPUT_CONTRACT_REF

    def fallback_chain(self) -> list[AgentBackendProvider] | None:
        return None

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=self.provider_id,
            backend_type=self.backend_type,
            supports_tool_calling=self.supports_tool_calling,
            supports_streaming=self.supports_streaming,
            deterministic=self.deterministic,
            default_output_contract=self._OUTPUT_CONTRACT_REF,
            supported_tools=[],
            description=(
                "Pure LLM backend (no tools). Mirrors Corti Note "
                "Completeness pattern: 0 tools, 6-section Markdown. "
                "Phase 4-A: skeleton (no real LLM wired)."
            ),
        )

    # ── Internal helpers ──────────────────────────────────────────

    def _resolve_client(self) -> LLMClient | None:
        """Return the LLMClient to use for this invoke, or None.

        Priority:
          1. ``self._llm_client`` set at construction time (explicit
             ``llm_client`` or ``llm_gateway`` arg).
          2. Lazy-resolve via ``registry.get_gateway()`` (set by
             ``app/main.py`` at startup). Wrap in ``LLMGatewayAdapter``.
          3. None — caller falls back to the skeleton placeholder path.
        """
        if self._llm_client is not None:
            return self._llm_client
        try:
            from .registry import get_gateway
            gateway = get_gateway()
        except Exception:
            return None
        if gateway is None:
            return None
        from .llm_gateway_adapter import LLMGatewayAdapter
        client = LLMGatewayAdapter(gateway)
        # Cache so subsequent invokes skip the lookup.
        self._llm_client = client
        return client

    def _emit_backend_metadata(
        self, ctx: AgentRunContext, latency_ms: int,
        status: ProviderStatus, *, fallback_used: bool = False,
    ) -> None:
        """Emit a ``backend_metadata`` RunTrace event.

        Phase 4-B Step 2(b): the RunTrace store gets a single event
        with all 8 backend metadata fields populated. The frontend
        ``BackendProviderSummary`` reads from this event.

        Defensive — never breaks the agent run if RunTrace is
        unavailable (e.g., in unit tests without a store).
        """
        try:
            from app.icoder.agent_runtime.orchestrator.run_trace import (
                emit_backend_metadata_event,
                get_default_store,
            )
            emit_backend_metadata_event(
                ctx.run_id,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                provider_latency_ms=latency_ms,
                provider_status=status,
                provider_deterministic=self.deterministic,
                supports_tool_calling=self.supports_tool_calling,
                fallback_used=fallback_used,
                output_contract=self.output_contract(),
                tool_rounds=0,
                store=get_default_store(),
            )
        except Exception as e:
            logger.warning(
                "PureLLMProvider: emit_backend_metadata_event failed: %s", e,
            )

    def _fail(self, message: str, t0: float) -> BackendResponse:
        return BackendResponse(
            status="fail",
            summary=f"PureLLMProvider: {message}",
            finish_state="failed",
            finish_reason=message[:300],
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            raw_provider_response={"error": message[:500]},
        )


# ── Helpers ────────────────────────────────────────────────────────────


def _extract_system_prompt(ctx: AgentRunContext) -> str:
    """Pull system_prompt from the agent pack if available."""
    pack = ctx.agent_pack or {}
    agent_node = pack.get("agent") if isinstance(pack, dict) else None
    if isinstance(agent_node, dict):
        sp = agent_node.get("system_prompt")
        if isinstance(sp, str) and sp:
            return sp
    if isinstance(pack, dict):
        sp = pack.get("system_prompt")
        if isinstance(sp, str) and sp:
            return sp
    return ""


def _extract_user_input(req: BackendRequest) -> str:
    """Pull user_input from ``req.input`` if ``req.user_input`` is empty."""
    if req.input and isinstance(req.input, dict):
        text = req.input.get("text") or req.input.get("user_input")
        if isinstance(text, str):
            return text
    return ""


def _placeholder_markdown(user_input: str, system_prompt: str) -> str:
    """Deterministic placeholder so tests can verify the contract."""
    return (
        "# PureLLMProvider — Skeleton Response\n\n"
        f"## User Input (truncated)\n\n> {user_input[:200]}\n\n"
        f"## System Prompt (truncated)\n\n> {system_prompt[:200]}\n\n"
        "## Status\n\ncomplete (skeleton — no real LLM call)\n\n"
        "## Note\n\nPhase 4-A skeleton. Wire `llm_client` to enable real LLM calls.\n"
    )


def _parse_status_from_markdown(text: str) -> ProviderStatus:
    """Heuristic: scan the LLM output for an explicit status keyword.

    Corti's Note Completeness Agent emits a 6-section Markdown with
    a status field. We do a simple case-insensitive scan for the 9
    states. If none match, default to ``complete``.

    Order matters: ``complete`` is checked before ``pass`` so that
    text like ``"... All checks passed."`` doesn't accidentally match
    ``pass`` when the writer meant ``complete``. ``compliant`` /
    ``non_compliant`` are checked first because they're more specific.
    """
    if not text:
        return "incomplete"
    lowered = text.lower()
    # Check multi-word / underscore states first (more specific), then
    # single-word states. Within single-word, ``complete`` precedes
    # ``pass`` so "passed" doesn't shadow an explicit "complete".
    for keyword in (
        "requires_review",
        "non_compliant",
        "compliant",
        "incomplete",
        "unclear",
        "warning",
        "fail",
        "complete",
        "pass",
    ):
        if keyword in lowered:
            return keyword  # type: ignore[return-value]
    return "complete"


def _extract_first_paragraph(text: str) -> str:
    """Pull the first non-empty paragraph from markdown as summary."""
    if not text:
        return ""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s[:300]
    return text[:300]


__all__ = [
    "PureLLMProvider",
    "LLMClient",
    "LLMResponse",
    "LLMChunk",
]
