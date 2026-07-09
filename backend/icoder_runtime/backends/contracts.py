"""iCoDer Agent Backend Provider contracts.

Phase 4-A Task 1 (2026-07-07): foundation for the unified
``AgentBackendProvider`` interface. Every backend (rule engine, pure
LLM, LLM with tools, ensemble, hybrid, cascade, external A2A, cached)
implements the same protocol so ``AgentRunner`` / ``InboundHandler``
never branch on backend form.

Design (per ``docs/architecture/agent_backend/ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md``
Item 1 + Item 4):

  - ``AgentBackendProvider`` is a ``Protocol`` (structural typing) so
    concrete providers don't need to inherit from a base class.
  - ``BackendRequest`` / ``BackendResponse`` / ``AgentRunContext`` are
    dataclasses — fast to construct, no Pydantic overhead on the hot
    path.
  - ``OutputContract`` is a Pydantic model — schema-validated before
    it leaves the runtime, so downstream consumers (frontend, A2A
    outbound, SSE streamer, RunTrace) never branch on backend form.
  - ``ProviderHealth`` / ``ProviderCapability`` are dataclasses used
    by ``ProviderRegistry.health()`` and agent-pack validation.

The 8 supported ``backend_type`` values cover the Corti-observed
patterns (rule_engine / pure_llm / llm_with_tools) plus the iCoDer
composable meta-providers (ensemble / cascade / hybrid / cached /
external_a2A).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


# ── Enums (string literals — JSON-serializable) ────────────────────────

BackendType = Literal[
    "rule_engine",
    "pure_llm",
    "llm_with_tools",
    "ensemble",
    "cascade",
    "hybrid",
    "external_a2a",
    "cached",
]
"""The 8 supported backend types (per ``ICODER_AGENT_BACKEND_PROVIDER_SPEC.md``)."""

FinishState = Literal["completed", "input-required", "failed"]
"""A2A §4 task state — the 3 Corti-observed finish states."""

ProviderStatus = Literal["pass", "warning", "fail", "complete", "incomplete",
                         "unclear", "compliant", "non_compliant", "requires_review"]
"""9-state status enum (Corti-observed across 3 agents)."""

Severity = Literal["info", "warning", "error", "critical"]


# ── Output contract (Pydantic — schema-validated) ──────────────────────


class OutputIssue(BaseModel):
    """A single finding raised by a provider."""

    code: str = Field(
        ..., description="Stable issue code, e.g. 'R001', 'compliance.ruleset_missing'.",
    )
    severity: Severity = Field(..., description="Issue severity.")
    message: str = Field(..., description="Human-readable issue description.")
    evidence: list[str] = Field(
        default_factory=list,
        description="Citations / char-span refs / tool-call IDs that ground this issue.",
    )
    recommended_action: str | None = Field(
        default=None,
        description="Optional next-step suggestion (Corti 'Why it matters' equivalent).",
    )


class ToolCallRecord(BaseModel):
    """One MCP tool call invoked by a provider."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None
    duration_ms: int = 0
    error: str | None = None
    scope_granted: list[str] = Field(default_factory=list)


class OutputContract(BaseModel):
    """Unified output schema across all 8 provider types.

    Every provider's raw output is normalized into this shape before
    being returned to ``AgentRunner`` / ``InboundHandler``. Downstream
    consumers (frontend, A2A outbound, SSE streamer, RunTrace) read
    only this shape — no per-provider branching.
    """

    # Identity
    agent_id: str = ""
    run_id: str = ""
    backend_provider: str = Field(
        ..., description="provider_id that produced this output (e.g. 'icoder.rule-engine.v1').",
    )

    # Status (Corti 9-state)
    status: ProviderStatus
    summary: str = Field("", description="2-4 sentence plain-language summary.")

    # Findings
    issues: list[OutputIssue] = Field(default_factory=list)
    corrected_draft: str | None = Field(
        default=None,
        description="For Note-Completeness-style agents that produce a corrected note draft.",
    )
    risk_flags: list[str] = Field(default_factory=list)

    # Tool calls (empty for PureLLM / RuleEngine)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)

    # Metadata
    latency_ms: int = 0
    cost_usd: float | None = None
    finish_state: FinishState = "completed"
    finish_reason: str | None = None

    # Schema validation metadata
    schema_ref: str = Field(
        default="icoder/OutputContract/v1",
        description="The schema this output conforms to (used by OutputContract validation).",
    )
    schema_version: str = "1.0"

    # Raw provider output (opaque to runtime; consumed by frontend for
    # provider-specific UI rendering — e.g. per-code validation table).
    raw: dict[str, Any] = Field(default_factory=dict)


# ── Request / Response / Context (dataclasses — hot path) ─────────────


@dataclass
class BackendRequest:
    """Input to a provider's ``invoke`` / ``stream``.

    ``input`` is an opaque dict — the provider interprets it per its
    ``backend_type`` (rule_engine expects ``{codes, note}``, pure_llm
    expects ``{text}``, llm_with_tools expects ``{text, tool_scope}``).
    """

    input: dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    user_input: str = ""
    tool_scope: list[str] = field(default_factory=list)
    """Whitelist of MCP tools this agent is allowed to call."""

    mandatory_tools: list[str] = field(default_factory=list)
    """Tools that must be called at least once (Corti Code Validation: verify+guidelines)."""

    forbidden_tools: list[str] = field(default_factory=list)
    """Tools this agent must NOT call (Corti Compliance Guardrail: search)."""

    placeholder_values: dict[str, Any] = field(default_factory=dict)
    """Map of ``{{PLACEHOLDER}}`` → value (e.g. ``{{COMPLIANCE_RULESET}}``)."""

    timeout_seconds: float = 60.0
    extra_context: dict[str, Any] = field(default_factory=dict)
    """Provider-specific extras (e.g. ``rule_verdict`` for HybridProvider)."""

    def with_extra_context(self, extras: dict[str, Any]) -> "BackendRequest":
        """Return a copy with ``extras`` merged into ``extra_context``."""
        merged = {**self.extra_context, **extras}
        return BackendRequest(
            input=dict(self.input),
            system_prompt=self.system_prompt,
            user_input=self.user_input,
            tool_scope=list(self.tool_scope),
            mandatory_tools=list(self.mandatory_tools),
            forbidden_tools=list(self.forbidden_tools),
            placeholder_values=dict(self.placeholder_values),
            timeout_seconds=self.timeout_seconds,
            extra_context=merged,
        )


@dataclass
class BackendResponse:
    """Provider output, BEFORE normalization to ``OutputContract``.

    Carries both the canonical fields (``status``, ``summary``,
    ``issues``, ``finish_state``) and the opaque ``raw_provider_response``
    dict that the frontend may consume for provider-specific UI.
    """

    status: ProviderStatus
    summary: str = ""
    issues: list[OutputIssue] = field(default_factory=list)
    corrected_draft: str | None = None
    risk_flags: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    latency_ms: int = 0
    cost_usd: float | None = None
    finish_state: FinishState = "completed"
    finish_reason: str | None = None
    raw_provider_response: dict[str, Any] = field(default_factory=dict)
    """Opaque provider-specific output (NOT consumed by runtime)."""

    backend_provider: str = ""
    """Filled by ``ProviderRegistry`` after invoke — for RunTrace."""

    backend_type: BackendType | str = ""
    """Filled by ``ProviderRegistry`` after invoke — for RunTrace."""

    fallback_used: bool = False
    """True if this response came from a cascade/ensemble fallback."""

    markdown: str = ""
    """Markdown rendering of the response (for SSE streaming / frontend)."""

    confidence: float | None = None
    """Per-response confidence in [0,1] (LLM providers may populate)."""

    evidence_refs: list[str] = field(default_factory=list)
    """Citations / char-span refs that ground the response."""

    trace_refs: list[str] = field(default_factory=list)
    """Run IDs / stage traces that this response correlates to."""

    def to_output_contract(
        self,
        *,
        agent_id: str = "",
        run_id: str = "",
        schema_ref: str = "icoder/OutputContract/v1",
    ) -> OutputContract:
        """Normalize to ``OutputContract`` (schema-validated Pydantic)."""
        return OutputContract(
            agent_id=agent_id,
            run_id=run_id,
            backend_provider=self.backend_provider,
            status=self.status,
            summary=self.summary,
            issues=list(self.issues),
            corrected_draft=self.corrected_draft,
            risk_flags=list(self.risk_flags),
            tool_calls=list(self.tool_calls),
            latency_ms=self.latency_ms,
            cost_usd=self.cost_usd,
            finish_state=self.finish_state,
            finish_reason=self.finish_reason,
            schema_ref=schema_ref,
            raw=dict(self.raw_provider_response),
        )


@dataclass
class AgentRunContext:
    """Per-run context — built once by ``AgentRunner`` and passed to
    every provider ``invoke`` / ``stream`` call.

    Carries identity (run_id / context_id / agent_id / tenant_id), the
    PHI-redacted input string, and a ``backend_config`` dict straight
    from the agent pack (so providers can read ``llm.model``,
    ``tools.scope`` etc. without re-parsing).
    """

    run_id: str
    context_id: str
    agent_id: str
    tenant_id: str = "default"
    region: str = "cn"
    redacted_input: str = ""
    """PHI-redacted user input — providers NEVER see raw PHI."""

    agent_pack: dict[str, Any] = field(default_factory=dict)
    """The full agent_pack.json (read-only) — providers read backend_config."""

    backend_config: dict[str, Any] = field(default_factory=dict)
    """Convenience: agent_pack['agent']['backend_config'] (or {})."""

    interaction_id: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)


# ── Provider health / capability ───────────────────────────────────────


@dataclass
class ProviderHealth:
    """Result of ``provider.health()``.

    Aggregated by ``ProviderRegistry.health_all()`` and exposed at
    ``GET /api/v1/agent-runtime/providers/health`` (Phase 4-B).
    """

    state: Literal["ok", "degraded", "down"] = "ok"
    latency_ms: int = 0
    last_check: datetime = field(default_factory=datetime.utcnow)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderCapability:
    """Static metadata describing what a provider can do.

    Used by ``ProviderRegistry.list()`` and agent-pack validation
    (``icoder pack validate`` checks ``backend_provider`` exists and
    ``tools.scope`` is a subset of provider's supported tools).
    """

    provider_id: str
    backend_type: BackendType
    supports_tool_calling: bool
    supports_streaming: bool
    deterministic: bool
    default_output_contract: str = "icoder/OutputContract/v1"
    supported_tools: list[str] = field(default_factory=list)
    """MCP tools this provider is wired to call (empty for PureLLM/RuleEngine)."""

    description: str = ""


# ── The unified protocol ───────────────────────────────────────────────


@runtime_checkable
class AgentBackendProvider(Protocol):
    """Unified interface for all 8 agent backend types.

    Implementations live in ``icoder_runtime/backends/``:

      - ``rule_engine_provider.RuleEngineProvider``
      - ``pure_llm_provider.PureLLMProvider`` (skeleton)
      - ``llm_with_tools_provider.LLMWithToolsProvider`` (skeleton)
      - (future) ``ensemble_provider``, ``cascade_provider``,
        ``hybrid_provider``, ``external_a2a_provider``, ``cached_provider``

    ``AgentRunner`` / ``InboundHandler`` resolve the provider from
    ``agent_pack.json`` ``backend_provider`` field via
    ``ProviderRegistry.resolve_from_agent_pack`` and call only this
    interface — never branch on backend form.
    """

    # Identity (class-level attributes — no @property needed)
    provider_id: str
    backend_type: BackendType
    supports_tool_calling: bool
    supports_streaming: bool
    deterministic: bool

    async def health(self) -> ProviderHealth:
        """Liveness probe. Returns ``{state, latency_ms, ...}``."""
        ...

    async def invoke(
        self, req: BackendRequest, ctx: AgentRunContext,
    ) -> BackendResponse:
        """Single-shot invocation (non-streaming callers)."""
        ...

    async def stream(
        self, req: BackendRequest, ctx: AgentRunContext,
    ) -> AsyncIterator[Any]:
        """Streaming invocation. Yields events (chunks / tool calls / finish).

        Skeletons that don't implement streaming yet should raise
        ``NotImplementedError`` so callers can detect and fall back
        to ``invoke()``.
        """
        ...

    def output_contract(self) -> str:
        """Return the schema_ref this provider emits (e.g. 'icoder/RuleEngineOutput/v1').

        Used by ``OutputContract`` validation and the frontend's
        provider-specific UI renderer selection.
        """
        ...

    def fallback_chain(self) -> list["AgentBackendProvider"] | None:
        """Optional cascade/ensemble fallback chain. ``None`` = no fallback."""
        ...

    def capabilities(self) -> ProviderCapability:
        """Static capability metadata — for ``ProviderRegistry.list()``."""
        ...


__all__ = [
    "AgentBackendProvider",
    "BackendRequest",
    "BackendResponse",
    "AgentRunContext",
    "OutputContract",
    "OutputIssue",
    "ToolCallRecord",
    "ProviderHealth",
    "ProviderCapability",
    "BackendType",
    "FinishState",
    "ProviderStatus",
    "Severity",
]
