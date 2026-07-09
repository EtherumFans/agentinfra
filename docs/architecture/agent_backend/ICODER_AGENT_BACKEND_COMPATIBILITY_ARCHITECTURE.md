# iCoDer Agent Backend Compatibility Architecture

**Document type:** Architecture spec (Part B)
**Date:** 2026-07-07
**Authors:** SONG Luhua
**Inputs:** `docs/reverse_engineering/corti_3_agents/CORTI_3_AGENTS_BACKEND_RE_REPORT.md`, `CORTI_3_AGENTS_TECHNICAL_INFERENCE_MATRIX.md`, `CORTI_NOTE_COMPLETENESS_SYSTEM_PROMPT.md` + 6 probe captures

## 1. Problem statement

Corti's reverse engineering (Part A) confirmed 3 distinct agent-backend patterns running on the same `coding-expert` shared LLM-with-tools backbone:

| Pattern | Agent | Tools | Operator config | Latency | Cost / msg |
|---------|-------|-------|------------------|---------|------------|
| LLM + 4 tools (mandatory) | Code Validation | verify/guidelines/explore/search | none | ~12s | $0.016 |
| LLM + 3 tools + placeholder | Compliance Guardrail | verify/guidelines/explore (search FORBIDDEN) | `{{COMPLIANCE_RULESET}}` | ~5s | $0.018 |
| Pure LLM (0 tools) | Note Completeness | none | none | ~12s | $0.030 |

iCoDer today has only one backend form: a rule-based engine (`RuleEngine` + `MedicalCodingRuleSet`, `model.primary="none"`, `supports_tool_calling=false`). To reach Corti parity, iCoDer must support all 3 patterns (and 5 more — see Provider Spec) under a **unified interface**, so that:

- An agent's `backend_provider` field in `agent_pack.json` selects the backend form declaratively
- The runtime executor (`AgentRunner` / `InboundHandler`) does not branch on backend form
- Rule-based and LLM-based agents coexist (iCoDer keeps RuleEngine for deterministic medical-coding pathways; adds LLM providers for Corti-style agents)
- Tool-MCP wiring is uniform: any provider that supports tools uses the same MCP layer as the existing MCP gateway
- Output normalization (`OutputContract`) and observability (`RunTrace`) are provider-agnostic

This document specifies the 10 design items required to achieve that.

## 2. Design items (10 total)

### Item 1 — `AgentBackendProvider` interface

**Purpose:** Single Python Protocol that every backend (rule engine, LLM, LLM+tools, ensemble, hybrid) implements. `AgentRunner` calls only this interface; never branches on backend form.

**Spec:**

```python
from typing import Protocol, runtime_checkable, AsyncIterator
from icoder_runtime.contracts import (
    AgentRunContext, BackendRequest, BackendResponse, OutputContract,
    RunTraceEvent, ToolCallRequest, ToolCallResponse,
)

@runtime_checkable
class AgentBackendProvider(Protocol):
    """Unified interface for all agent backends.

    Implementations: RuleEngineProvider, PureLLMProvider,
    LLMWithToolsProvider, EnsembleProvider, HybridProvider,
    CascadeProvider, ExternalA2AProvider, CachedProvider.
    """

    # Identity
    provider_id: str  # e.g. "icoder.rule-engine.v1"
    backend_type: str  # enum: rule_engine | pure_llm | llm_with_tools | ensemble | hybrid | cascade | external_a2a | cached
    supports_tool_calling: bool
    supports_streaming: bool
    deterministic: bool

    async def health(self) -> dict:
        """Liveness probe. Returns {state: "ok"|"degraded"|"down", latency_ms, ...}."""

    async def invoke(self, req: BackendRequest, ctx: AgentRunContext) -> BackendResponse:
        """Single-shot invocation. Used by non-streaming callers."""

    async def stream(self, req: BackendRequest, ctx: AgentRunContext) -> AsyncIterator[RunTraceEvent]:
        """Streaming invocation. Yields RunTraceEvent sequence:
        stage_start -> tool_call (if any) -> stage_end -> output_chunk* -> finish.
        """

    async def call_tool(self, req: ToolCallRequest, ctx: AgentRunContext) -> ToolCallResponse:
        """Optional. Only implemented when supports_tool_calling=True.
        For LLMWithToolsProvider this proxies to MCP server tools.
        For RuleEngineProvider this is not called (raise NotImplementedError)."""

    def output_contract(self) -> type[OutputContract]:
        """Pydantic schema this provider emits. Runtime uses this to validate
        and to project to the agent's declared OutputContract."""

    def fallback_chain(self) -> list["AgentBackendProvider"] | None:
        """Optional. Returns the cascade/ensemble fallback chain.
        None = no fallback. Used by EnsembleProvider/CascadeProvider."""
```

**Runtime contract:**

- `AgentRunner` resolves provider from `agent_pack.json` `backend_provider` field via `ProviderRegistry`
- `AgentRunner.invoke()` is the ONLY entry point — no `if backend_type == "llm": ...` branches
- Provider implementations live in `icoder_runtime/backends/{provider_type}.py`
- All providers emit `RunTraceEvent` objects; the runtime aggregates into `RunTrace`

**Key property:** the existing `RuleEngine` becomes one of 8 providers, not a special case.

### Item 2 — `CapabilityAdapter`

**Purpose:** Wrap non-conforming backends (legacy rule engines, external A2A agents, third-party HTTP APIs) so they expose the `AgentBackendProvider` interface.

**Pattern:**

```python
class CapabilityAdapter:
    """Base class for adapters that bridge non-conforming backends."""

    def __init__(self, inner: Any, *, output_contract: type[OutputContract]):
        self.inner = inner
        self._output_contract = output_contract

    def adapt(self) -> AgentBackendProvider:
        """Returns a ProviderProtocol-compliant wrapper around self.inner."""
```

**Concrete adapters:**

| Adapter | Wraps | Output transform |
|---------|-------|------------------|
| `RuleEngineAdapter` | `compliance_services.RuleEngine` | RuleEngine verdict → `OutputContract` (status / summary / issues / evidence) |
| `MedicalCodingAdapter` (existing, refactored) | `HybridCodingAdapter` / `MedCodERRetrievalRuleSet` | `MedicalCodingOutputSchema` → `OutputContract` |
| `ExternalA2AAdapter` | any A2A v0.3 peer (Corti, third-party) | A2A `Message.parts[]` → `OutputContract` |
| `LegacyHTTPAdapter` | arbitrary REST POST endpoint | response JSON → `OutputContract` (provider supplies schema) |
| `StaticResponseAdapter` | fixed canned response (for testing) | direct `OutputContract` |

**Why this matters:** Without `CapabilityAdapter`, every non-conforming backend requires bespoke wiring in `AgentRunner`. With the adapter, the runtime stays uniform.

**Note on `MedicalCodingAdapter`:** the existing `HybridCodingAdapter.infer_async` becomes a `RuleEngineProvider`-equivalent (deterministic mode) OR `LLMWithToolsProvider`-equivalent (medcoder mode) depending on `mode=` — see Item 10.

### Item 3 — `ToolMCPCompatLayer`

**Purpose:** Bridge provider-native tool definitions to iCoDer's MCP layer, so that all tool-calling providers use the same MCP server registry, auth, and redaction.

**Design:**

```
LLMWithToolsProvider (e.g. DeepSeek)
  │
  │  provider-native tool schema (DeepSeek function-calling JSON)
  │
  ▼
ToolMCPCompatLayer
  │
  │  MCP/JSON-RPC 2.0 calls (tools/call, tools/list)
  │
  ▼
MCP Server Registry (icoder_runtime.mcp.server)
  │
  ├── verify tool        → MedicalCodingRuleSet.verify()
  ├── guidelines tool    → CodingGuidelinesKB.search()
  ├── explore tool       → CodeCatalogExplore.search()
  ├── search tool        → DocumentationSearch.search()
  └── icoder_* tools     → business workbench endpoints
```

**Spec:**

```python
class ToolMCPCompatLayer:
    """Translates provider-native tool calls to MCP/JSON-RPC."""

    def __init__(self, mcp_registry: "MCPToolRegistry"):
        self.mcp = mcp_registry

    def provider_to_mcp(self, tool_call: dict, provider_id: str) -> ToolCallRequest:
        """e.g. DeepSeek tool_call {name, arguments} → MCP tools/call request."""

    def mcp_to_provider(self, mcp_resp: ToolCallResponse, provider_id: str) -> dict:
        """e.g. MCP tools/call response → DeepSeek function-call result."""

    def list_for_provider(self, provider_id: str) -> list[dict]:
        """Returns provider-native tool schemas for all MCP tools
        the provider is authorized to call (per agent_pack tool scope)."""
```

**Key property:** the 4 Corti `coding-expert` tools (verify/guidelines/explore/search) and the 8 iCoDer MCP tools (`icoder_*`) share the same MCP server. An agent's `tool_scope` in `agent_pack.json` filters which tools each provider can call — Corti-style scoping (e.g., Compliance Guardrail forbids `search`).

**Auth integration:** all MCP calls pass through the existing 4-layer auth (Phase 3-C1: Bearer / mTLS / OAuth2 Client Credentials / Custom Header) and 3-layer redaction (`redacted_view` / `phi_redacted` / `audit_safe`).

### Item 4 — `OutputContract`

**Purpose:** Pydantic schema every provider's raw output is normalized into, so downstream consumers (frontend / A2A outbound / SSE streamer / RunTrace) never branch on backend form.

**Spec:**

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class OutputIssue(BaseModel):
    code: str                      # e.g. "R001", "compliance.ruleset_missing"
    severity: Literal["info", "warning", "error", "critical"]
    message: str
    evidence: list[str] = Field(default_factory=list)  # citations / span refs
    recommended_action: Optional[str] = None

class OutputContract(BaseModel):
    """Unified output schema across all 8 provider types."""

    # Identity
    agent_id: str
    run_id: str
    backend_provider: str          # e.g. "icoder.llm-with-tools.v1"

    # Status (3-state pattern across all 3 Corti agents)
    status: Literal["pass", "warning", "fail", "complete", "incomplete", "unclear", "compliant", "non_compliant", "requires_review"]
    summary: str                   # 2-4 sentence plain-language summary

    # Findings
    issues: list[OutputIssue] = Field(default_factory=list)
    corrected_draft: Optional[str] = None  # for Note Completeness-style agents
    risk_flags: list[str] = Field(default_factory=list)

    # Metadata
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    latency_ms: int
    cost_usd: Optional[float] = None
    finish_state: Literal["completed", "input-required", "failed"]
    finish_reason: Optional[str] = None

    # Raw provider output (for debugging / provider-specific UI)
    raw: dict                      # opaque to runtime, consumed only by frontend
```

**Normalization rules:**

| Provider | Status mapping |
|----------|----------------|
| RuleEngine | rule_verdict → pass / warning / fail |
| PureLLM | LLM-generated status string parsed into 9-state enum |
| LLMWithTools | same as PureLLM, plus tool_calls list populated |
| Ensemble | majority / weighted vote → status |
| Cascade | first non-fail provider's status |
| Hybrid | rule_verdict + LLM_summary combined |

**Frontend rendering:** the frontend consumes `OutputContract` and renders provider-specific UI from `raw` (e.g., per-code validation table for Code Validation, Missing Items table for Note Completeness, status banner for Compliance Guardrail).

### Item 5 — `RunTrace` spec

**Purpose:** Provider-agnostic 9-step trace emitted by every provider, so `RunTraceViewer` and `AuditLog` work uniformly.

**Spec (extends existing 9-step spec from Phase 3-D):**

```
Step 1: received         — AgentRunner received request
Step 2: provider_resolved — backend_provider located in registry
Step 3: context_loaded    — AgentRunContext built (contextId, PHI redaction applied)
Step 4: tool_scope_checked — MCP tool scope filtered for this agent
Step 5: backend_invoked   — provider.invoke() / stream() called
Step 6: tool_calls        — 0+ MCP tool calls (skipped for PureLLM / RuleEngine)
Step 7: output_normalized — provider raw output → OutputContract
Step 8: contract_validated — OutputContract schema-validated
Step 9: finished          — state: completed | input-required | failed
```

**Per-step fields:**

```python
class RunTraceEvent(BaseModel):
    step: int                      # 1..9
    step_name: str
    provider_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_ms: Optional[int]
    payload: dict                  # step-specific
    redacted_payload: dict         # PHI-redacted view for audit log
```

**Provider extension points:**

- PureLLM provider emits step 6 with 0 tool_calls
- LLMWithTools provider emits 0+ step-6 events (one per MCP call)
- RuleEngine provider emits step 6 with rule evaluations as "pseudo-tool-calls"
- Ensemble provider emits nested sub-traces per provider in step 5

**Storage:** `RunTrace` persisted to `runtime_run_traces` table (existing from Phase 3-D2) with full event JSONB.

### Item 6 — `ProviderRegistry`

**Purpose:** Process-wide registry of available providers. Looked up by `provider_id` from `agent_pack.json` `backend_provider` field.

**Spec:**

```python
class ProviderRegistry:
    """Singleton registry. Populated at startup from icoder_runtime/backends/*.py."""

    def register(self, provider: AgentBackendProvider) -> None: ...
    def get(self, provider_id: str) -> AgentBackendProvider: ...
    def list(self) -> list[str]: ...
    def list_by_type(self, backend_type: str) -> list[AgentBackendProvider]: ...
    def health_all(self) -> dict[str, dict]: ...
```

**Registration sources (at startup):**

1. **Built-in providers** (always registered):
   - `icoder.rule-engine.v1` — wraps `compliance_services.RuleEngine`
   - `icoder.pure-llm.v1` — DeepSeek V4 chat completion, no tools
   - `icoder.llm-with-tools.v1` — DeepSeek V4 + MCP tool compat layer
   - `icoder.ensemble.v1` — multi-provider majority vote
   - `icoder.cascade.v1` — fallback chain
   - `icoder.hybrid.v1` — rule + LLM combined
   - `icoder.cached.v1` — response cache wrapper
   - `icoder.external-a2a.v1` — A2A peer delegation

2. **Plugin providers** (loaded from `icoder_runtime/backends/plugins/`):
   - Discovered via `@register_provider` decorator
   - Useful for ISV custom backends (e.g., custom rule pack, custom LLM endpoint)

3. **Tenant-scoped providers** (loaded from tenant config):
   - Per-tenant LLM endpoints (e.g., hospital-specific DeepSeek deployment)
   - Per-tenant MCP tool scopes (e.g., restricted `search` tool)

**Health check:** `/api/v1/agent-runtime/providers/health` returns aggregated health for all registered providers (extends existing `/health`).

### Item 7 — `agent_pack.json` `backend_provider` field

**Purpose:** Declarative backend selection in the agent pack, so the same agent definition can switch backends without code changes.

**Schema (v1.2 addition):**

```json
{
  "schema_version": "1.2",
  "agent": {
    "name": "Code Validation Agent",
    "backend_provider": "icoder.llm-with-tools.v1",
    "backend_config": {
      "llm": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.0
      },
      "tools": {
        "scope": ["verify", "guidelines", "explore", "search"],
        "mandatory": ["verify", "guidelines"],
        "forbidden": []
      },
      "placeholder_values": {
        "{{COMPLIANCE_RULESET}}": null
      }
    },
    "experts": [{"name": "coding-expert", "type": "reference"}],
    "system_prompt": "...",
    "output_contract": "icoder.contracts.CodeValidationOutput"
  }
}
```

**Field semantics:**

| Field | Required | Description |
|-------|----------|-------------|
| `backend_provider` | yes | `provider_id` from registry (e.g., `icoder.llm-with-tools.v1`) |
| `backend_config.llm` | for LLM providers | LLM endpoint config (provider/model/temperature/max_tokens) |
| `backend_config.tools.scope` | for tool-calling providers | Whitelist of MCP tools this agent can call |
| `backend_config.tools.mandatory` | optional | Tools that MUST be called at least once (Corti Code Validation: verify+guidelines) |
| `backend_config.tools.forbidden` | optional | Tools this agent must NOT call (Corti Compliance Guardrail: search) |
| `backend_config.placeholder_values` | optional | Map of `{{PLACEHOLDER}}` → value or null (Compliance Guardrail: `{{COMPLIANCE_RULESET}}` until configured) |
| `output_contract` | yes | Pydantic schema path for this agent's OutputContract subclass |

**Validation:** `icoder pack validate` enforces:
- `backend_provider` exists in registry (or fails with actionable error)
- `tools.scope` only contains registered MCP tools
- `tools.mandatory` ⊆ `tools.scope`
- `tools.forbidden` ∩ `tools.scope` = ∅
- `output_contract` resolves to a Pydantic class

**Backward compat:** v1.0 packs without `backend_provider` default to `icoder.rule-engine.v1` (preserves existing 16 official agent packs).

### Item 8 — `fallback` / `ensemble` / `hybrid` patterns

**Purpose:** Three composable meta-providers for resilience and combined deterministic+LLM execution.

**8a. `CascadeProvider` (fallback chain):**

```python
class CascadeProvider:
    """Tries providers in order; first non-fail wins."""

    def __init__(self, chain: list[AgentBackendProvider]):
        self.chain = chain

    async def invoke(self, req, ctx):
        for provider in self.chain:
            try:
                resp = await provider.invoke(req, ctx)
                if resp.finish_state != "failed":
                    return resp
            except Exception:
                continue
        return BackendResponse(status="fail", summary="All providers failed")
```

**Use case:** `icoder.llm-with-tools.v1` → fallback to `icoder.rule-engine.v1` if LLM gateway down.

**8b. `EnsembleProvider` (parallel vote):**

```python
class EnsembleProvider:
    """Runs N providers in parallel; majority vote on status."""

    def __init__(self, members: list[AgentBackendProvider], strategy: str = "majority"):
        self.members = members
        self.strategy = strategy

    async def invoke(self, req, ctx):
        responses = await asyncio.gather(*[m.invoke(req, ctx) for m in self.members])
        return self._vote(responses)
```

**Use case:** ensemble of `icoder.pure-llm.v1` (3 different temperatures) for robustness on critical decisions.

**8c. `HybridProvider` (rule + LLM combined):**

```python
class HybridProvider:
    """Rule engine evaluates; LLM summarizes / explains."""

    def __init__(self, rule: AgentBackendProvider, llm: AgentBackendProvider):
        self.rule = rule
        self.llm = llm

    async def invoke(self, req, ctx):
        rule_resp = await self.rule.invoke(req, ctx)
        if rule_resp.finish_state == "completed":
            # LLM takes rule verdict as input, generates natural-language summary
            llm_req = req.with_extra_context({"rule_verdict": rule_resp.raw})
            llm_resp = await self.llm.invoke(llm_req, ctx)
            return merge(rule_resp, llm_resp)
        return rule_resp
```

**Use case:** Medical Coding Agent keeps RuleEngine for ICD-10 code assignment (deterministic), uses LLM for natural-language summary of reasoning — preserves F1 baseline while gaining Corti-style explainability.

### Item 9 — Unified deterministic + LLM execution

**Purpose:** The same `AgentRunner` runs both deterministic (rule-engine) and LLM agents, with no branching on backend form.

**Execution flow:**

```
1. AgentRunner.run(req)
2.   provider = ProviderRegistry.get(agent.backend_provider)
3.   ctx = AgentRunContext.from(req, agent, session)
4.   trace = RunTrace.start(agent_id, run_id)
5.   trace.event(step=1, name="received")
6.   trace.event(step=2, name="provider_resolved", payload={provider_id})
7.   ctx.apply_phi_redaction()  # always, regardless of backend
8.   trace.event(step=3, name="context_loaded")
9.   tool_scope = agent.backend_config.tools.scope
10.  trace.event(step=4, name="tool_scope_checked", payload={tool_scope})
11.  async for event in provider.stream(req, ctx):
12.    trace.event(event)
13.    if event.is_tool_call:
14.      mcp_resp = await mcp.call(event.tool_call)
15.      trace.event(step=6, name="tool_calls", payload=mcp_resp)
16.      provider.consume_tool_response(mcp_resp)
17.  trace.event(step=7, name="output_normalized")
18.  output = OutputContract.from_provider(provider, agent.output_contract)
19.  trace.event(step=8, name="contract_validated", payload=output)
20.  trace.event(step=9, name="finished", payload={state: output.finish_state})
21.  return output
```

**Key invariants:**

- Line 11 `provider.stream()` works for all 8 provider types — RuleEngine yields a single finish event, LLM yields text-delta chunks, LLMWithTools yields interleaved text + tool_call events
- Line 13 `event.is_tool_call` is False for RuleEngine and PureLLM providers
- Line 18 `OutputContract.from_provider()` normalizes — RuleEngine output shape → OutputContract, LLM raw text → OutputContract with parsed status
- Line 20 `finish_state` enum covers `completed` / `input-required` / `failed` (the 3 Corti states observed)

**No branching:** there is no `if isinstance(provider, LLMWithToolsProvider)` anywhere in `AgentRunner`. All backend-form-specific logic lives inside provider implementations.

### Item 10 — Medical Coding backend decoupling plan

**Purpose:** Unbundle Medical Coding Agent from its current hard-wired `HybridCodingAdapter` / `MedCodERRetrievalRuleSet` coupling, so it can switch between rule-based, LLM-based, and hybrid backends via `backend_provider` in `agent_pack.json`.

**Current state (pre-decoupling):**

```
Medical Coding Agent (official_agents/medical_coding/agent_pack.json)
  └── agent.config.backend_provider = NOT SET  (implicit)
      └── AgentRunner → hardcoded MedicalCodingRuntimeEndpoint
          └── HybridCodingAdapter.infer_async(mode="medcoder"|"hybrid"|"prompt")
              └── 5-stage pipeline tightly coupled to BGE-M3 + FAISS + DeepSeek
```

**Target state (post-decoupling):**

```
Medical Coding Agent (official_agents/medical_coding/agent_pack.json)
  └── agent.config.backend_provider = "icoder.hybrid.v1"  (default)
      └── backend_config = {
            "rule_provider": "icoder.rule-engine.medcoder.v1",
            "llm_provider": "icoder.llm-with-tools.medcoder.v1",
            "merge_strategy": "rule_first_llm_summarize"
          }
```

**Migration steps (concrete file changes — see `ICODER_MEDICAL_CODING_BACKEND_DECOUPLING_PLAN.md` for full detail):**

1. Extract `HybridCodingAdapter` stages 1-5 into separate MCP tools:
   - `icoder_medcoder_extract` (Stage 1 — LLM extraction)
   - `icoder_medcoder_retrieve` (Stage 2 — BGE-M3 + FAISS)
   - `icoder_medcoder_merge` (Stage 3 — candidate set)
   - `icoder_medcoder_rerank` (Stage 4 — DeepSeek rank)
   - `icoder_medcoder_compliance` (Stage 5 — calibration)
2. Implement `MedCodERRuleEngineProvider` (rule-only mode, Stage 2+5 only)
3. Implement `MedCodERLLMWithToolsProvider` (full 5-stage via tool calls)
4. Implement `MedCodERHybridProvider` (default — rule-first, LLM summarizes)
5. Update `medical_coding/agent_pack.json` to declare `backend_provider: "icoder.hybrid.medcoder.v1"`
6. Update `MedicalCodingRuntimeEndpoint` to delegate to `AgentRunner.invoke()` instead of calling `HybridCodingAdapter` directly
7. Update `scripts/e2e_medcoder_validation.py` to test all 3 backend modes via `backend_provider` switch (no code changes to test variants)

**Decoupling boundary:** the F1 baseline (per-case micro-F1 over primary + secondary dx) MUST NOT regress. The acceptance test is `python scripts/e2e_runtime_validation.py --base-url http://localhost:8000` producing F1 ≥ baseline.

## 3. End-to-end flow (post-architecture)

```
Frontend (MedicalCodingPage) → POST /api/v2/tools/coding
  ↓
MedicalCodingRuntimeEndpoint
  ↓
AgentRunner.run(req, agent_id="medical-coding-agent")
  ↓
ProviderRegistry.get("icoder.hybrid.medcoder.v1")
  ↓
MedCodERHybridProvider.stream(req, ctx)
  ├── MedCodERRuleEngineProvider.invoke (Stages 2+5)
  │   └── calls MCP tool: icoder_medcoder_retrieve, icoder_medcoder_compliance
  └── MedCodERLLMWithToolsProvider.invoke (Stages 1+3+4)
      └── calls MCP tools: icoder_medcoder_extract, icoder_medcoder_merge, icoder_medcoder_rerank
  ↓
OutputContract (MedicalCodingOutputSchema projection)
  ↓
SSE stream: 9-step RunTrace events
  ↓
Frontend renders DiagnosisCard with evidence chips + TopKChips + override
```

## 4. Compatibility with existing systems

| Existing system | Compatibility |
|-----------------|---------------|
| `compliance_services.RuleEngine` | becomes `RuleEngineProvider` (wrapped by `RuleEngineAdapter`) |
| `MedicalCodingRuleSet` (12 rules) | stays; consumed by `RuleEngineProvider` |
| `HybridCodingAdapter` (5-stage) | unbundled into 5 MCP tools (see Item 10) |
| `LLMGateway` (DeepSeek V4) | becomes `LLMClient` used by `PureLLMProvider` and `LLMWithToolsProvider` |
| `MCPToolRegistry` (8 iCoDer tools) | stays; `ToolMCPCompatLayer` adds 4 Corti-style tools (verify/guidelines/explore/search) |
| `RunHistory` / `AuditLog` / `FallbackTracker` | consume `RunTrace` events uniformly |
| `ShadowDiffService` | compares 2 providers' `OutputContract` (e.g., rule vs LLM for A/B canary) |
| `DataPolicy` (PHI redaction) | applied at `AgentRunContext` construction (step 3), before any provider sees data |

## 5. Phasing

| Phase | Scope | Effort | Depends on |
|-------|-------|--------|-------------|
| Phase 4-A | Items 1, 4, 6 — Provider interface + OutputContract + Registry | 3 days | none |
| Phase 4-B | Items 2, 3 — CapabilityAdapter + ToolMCPCompatLayer | 3 days | 4-A |
| Phase 4-C | Items 5, 7, 9 — RunTrace spec + agent_pack schema + unified executor | 4 days | 4-A, 4-B |
| Phase 4-D | Items 8 — fallback/ensemble/hybrid meta-providers | 3 days | 4-A, 4-B |
| Phase 4-E | Item 10 — Medical Coding backend decoupling | 5 days | 4-A..4-D |
| Phase 4-F | Migrate 16 official agent packs to declare `backend_provider` | 2 days | 4-A..4-E |
| Phase 4-G | 3 Corti-style agents (Code Validation + Compliance Guardrail + Note Completeness) | 4 days | 4-A..4-F |

**Total:** ~24 days for full Corti-parity backend architecture.

## 6. Acceptance criteria

1. `AgentRunner` contains zero `if backend_type ==` branches
2. All 16 existing official agent packs still pass after declaring `backend_provider` (default `icoder.rule-engine.v1`)
3. F1 baseline on 201 cases does not regress after Medical Coding decoupling
4. 3 new Corti-parity agents (Code Validation + Compliance Guardrail + Note Completeness) reproducible in iCoDer with `backend_provider = icoder.llm-with-tools.v1` / `icoder.llm-with-tools.v1` / `icoder.pure-llm.v1`
5. `RunTraceViewer` renders 9-step trace for all 8 provider types without per-provider UI branches
6. `/api/v1/agent-runtime/providers/health` returns health for all registered providers
7. `icoder pack validate` rejects packs with unknown `backend_provider` or invalid `tools.scope`

## 7. Risks

| Risk | Mitigation |
|------|------------|
| LLM cost spike (Note Completeness $0.029672/msg) | `icoder.cached.v1` for repeat queries; `icoder.hybrid.v1` for rule-first agents |
| LLM non-determinism breaks F1 baseline | Medical Coding keeps `icoder.hybrid.medcoder.v1` (rule-first); LLM only summarizes |
| Prompt injection against LLM providers | system prompt mandates structure (Corti pattern); `OutputContract` validation rejects malformed output; `redacted_view` for audit |
| Provider registry startup race | lazy registration on first `get()`; fail-fast with actionable error if missing |
| Backward compat for v1.0 packs | default `backend_provider = icoder.rule-engine.v1` if missing |
| MCP tool scope leak | `backend_config.tools.scope` whitelist enforced at `ToolMCPCompatLayer` boundary |
