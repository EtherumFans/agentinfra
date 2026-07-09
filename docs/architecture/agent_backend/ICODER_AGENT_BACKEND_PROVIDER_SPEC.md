# iCoDer Agent Backend Provider Spec — 8 Provider Types

**Document type:** Provider spec (Part B)
**Date:** 2026-07-07
**Authors:** SONG Luhua
**Parent doc:** `ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md` (Item 1 — `AgentBackendProvider` interface)

This document specifies the 8 concrete provider types that implement `AgentBackendProvider`. For each: use case, I/O contract, pros, cons, and fit-for-purpose per the 3 Corti-parity agents + Medical Coding Agent.

## Provider inventory

| # | `provider_id` | `backend_type` | Deterministic | Tools | Stream | Cost/msg (est.) |
|---|---------------|----------------|---------------|-------|--------|------------------|
| 1 | `icoder.rule-engine.v1` | rule_engine | YES | NO | NO | $0 |
| 2 | `icoder.pure-llm.v1` | pure_llm | NO | NO | YES | $0.005-0.030 |
| 3 | `icoder.llm-with-tools.v1` | llm_with_tools | NO | YES | YES | $0.005-0.020 |
| 4 | `icoder.ensemble.v1` | ensemble | NO | any | YES | N × member cost |
| 5 | `icoder.cascade.v1` | cascade | depends | any | YES | first-success cost |
| 6 | `icoder.hybrid.v1` | hybrid | depends | any | YES | rule + LLM cost |
| 7 | `icoder.external-a2a.v1` | external_a2a | NO | N/A | YES | peer-dependent |
| 8 | `icoder.cached.v1` | cached | depends | any | YES | $0 (cache hit) |

---

## Provider 1 — `icoder.rule-engine.v1`

**Use case:** Deterministic rule-based evaluation. Wraps `compliance_services.RuleEngine` + any `RuleSet` subclass (`MedicalCodingRuleSet`, future `DRGDIPRuleSet`, `InsuranceAuditRuleSet`, etc.).

**Implementation:**

```python
class RuleEngineProvider:
    provider_id = "icoder.rule-engine.v1"
    backend_type = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True

    def __init__(self, rule_set: RuleSet):
        self.engine = RuleEngine(rule_set)

    async def invoke(self, req, ctx):
        verdict = await self.engine.evaluate(req.input)
        return BackendResponse(
            status=map_verdict_to_status(verdict),
            summary=verdict.summary,
            issues=[OutputIssue(code=r.code, severity=r.severity, message=r.message, evidence=r.evidence) for r in verdict.rules_triggered],
            raw=verdict.dict(),
            finish_state="completed",
            latency_ms=...
        )

    async def stream(self, req, ctx):
        # Non-streaming: emit single finish event
        resp = await self.invoke(req, ctx)
        yield RunTraceEvent(step=5, name="backend_invoked", payload=resp.raw)
        yield RunTraceEvent(step=9, name="finished", payload={"state": "completed"})

    def output_contract(self):
        return RuleEngineOutputContract
```

**I/O:**

- Input: `BackendRequest.input` = arbitrary dict (rule_set-specific shape, e.g., `{codes: [...], note: "..."}` for `MedicalCodingRuleSet`)
- Output: `OutputContract` with `status ∈ {pass, warning, fail}`, `issues[]` populated from triggered rules

**Pros:**

- Zero LLM cost — runs on commodity CPU
- Fully deterministic — same input → byte-identical output (regression-testable)
- Explainable — every issue has a rule code and evidence chain
- Fast — <100ms typical latency
- PHI-safe — no external API calls, no prompt data leaves the cluster

**Cons:**

- Cannot handle natural-language reasoning (e.g., "Why it matters" cells in Note Completeness output)
- Cannot generate corrected drafts (Corti Step 4) — only flags gaps
- Rule coverage must be hand-coded; semantic gaps require exponential rule volume
- No tool calling — cannot query live code catalog, guidelines KB, etc. (without `HybridProvider`)

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Medical Coding Agent (rule mode) | ✅ Strong | F1 baseline relies on `MedicalCodingRuleSet` (R001-R010 + MC-R-M80-001); LLM-only regresses F1 |
| Code Validation Agent | ❌ Weak | Corti's per-code evidence citations + "Why it matters" require LLM semantic reasoning |
| Compliance Guardrail Agent | ⚠️ Partial | Works for known rule sets (CCI edits, LCD) but cannot handle novel payer policies — Corti uses LLM for this |
| Note Completeness Agent | ❌ Weak | Corrected note draft + 14-row Missing Items table with "Why it matters" requires LLM |

---

## Provider 2 — `icoder.pure-llm.v1`

**Use case:** Pure LLM backend with no tool calls. Mirrors Corti Note Completeness Agent (Probe 5/6: 0 tools, 6-section Markdown output, $0.029672/msg).

**Implementation:**

```python
class PureLLMProvider:
    provider_id = "icoder.pure-llm.v1"
    backend_type = "pure_llm"
    supports_tool_calling = False
    supports_streaming = True
    deterministic = False

    def __init__(self, llm: LLMClient, default_temperature: float = 0.0):
        self.llm = llm
        self.default_temperature = default_temperature

    async def stream(self, req, ctx):
        messages = build_messages(req, ctx)  # system + user
        async for chunk in self.llm.stream(messages, temperature=self.default_temperature):
            yield RunTraceEvent(step=7, name="output_chunk", payload={"delta": chunk})
        yield RunTraceEvent(step=9, name="finished", payload={"state": "completed"})

    def output_contract(self):
        return PureLLMOutputContract  # status parsed from LLM output
```

**I/O:**

- Input: `BackendRequest.input.text` (user message) + `agent.system_prompt` (from agent_pack)
- Output: `OutputContract` with `status` parsed from LLM-generated Markdown (regex-based status extraction), `raw.markdown` = full LLM output, `corrected_draft` populated for Note Completeness-style agents

**Pros:**

- Handles natural-language reasoning (semantic gap-finding, "Why it matters" cells, corrected drafts)
- Robust against prompt injection when system prompt mandates structure (CONFIRMED via Corti Probe 8)
- Streaming — frontend renders progressively
- Simple to implement — no MCP tool wiring

**Cons:**

- Non-deterministic — same input produces slightly different output across runs (CONFIRMED via Corti Probe 1 vs Probe 8 row count variation: 14 vs 13)
- Cost per message — $0.005-0.030 typical
- Latency — 5-15s typical
- No factual lookup — cannot query code catalog or guidelines KB (relies entirely on training data + chat context)
- PHI concern — prompts sent to LLM provider (mitigated by `DataPolicy` redaction at `AgentRunContext` boundary)

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Note Completeness Agent | ✅ Strong | Exact Corti pattern — 0 tools, 6-section Markdown, $0.029672/msg |
| Code Validation Agent | ❌ Weak | Needs `verify` + `guidelines` tool calls for evidence — pure LLM cannot cite code catalog |
| Compliance Guardrail Agent | ⚠️ Partial | Works for refusal path (no ruleset configured) but cannot evaluate actual rules without `verify` tool |
| Medical Coding Agent | ❌ Weak | Loses F1 (Corti's Code Validation uses tools for code lookup; pure LLM regresses) |

---

## Provider 3 — `icoder.llm-with-tools.v1`

**Use case:** LLM backend with MCP tool calls. Mirrors Corti Code Validation Agent (4 tools: verify/guidelines/explore/search) and Compliance Guardrail Agent (3 tools, search FORBIDDEN).

**Implementation:**

```python
class LLMWithToolsProvider:
    provider_id = "icoder.llm-with-tools.v1"
    backend_type = "llm_with_tools"
    supports_tool_calling = True
    supports_streaming = True
    deterministic = False

    def __init__(self, llm: LLMClient, mcp: ToolMCPCompatLayer):
        self.llm = llm
        self.mcp = mcp

    async def stream(self, req, ctx):
        messages = build_messages(req, ctx)
        tools = self.mcp.list_for_provider(self.provider_id, scope=req.tool_scope)
        while True:
            async for chunk in self.llm.stream(messages, tools=tools):
                if chunk.is_tool_call:
                    yield RunTraceEvent(step=6, name="tool_calls", payload=chunk.tool_call)
                    mcp_resp = await self.mcp.call(chunk.tool_call, ctx)
                    messages.append({"role": "tool", "content": mcp_resp.text})
                    yield RunTraceEvent(step=6, name="tool_response", payload=mcp_resp.dict())
                else:
                    yield RunTraceEvent(step=7, name="output_chunk", payload={"delta": chunk.text})
            if not self.llm.last_response_has_pending_tool_calls:
                break
        yield RunTraceEvent(step=9, name="finished", payload={"state": "completed"})

    async def call_tool(self, req, ctx):
        return await self.mcp.call(req, ctx)

    def output_contract(self):
        return LLMWithToolsOutputContract
```

**I/O:**

- Input: `BackendRequest.input.text` + `agent.system_prompt` + `agent.backend_config.tools` (scope/mandatory/forbidden)
- Output: `OutputContract` with `tool_calls[]` populated, `status` parsed from LLM output, `issues[].evidence` citing tool responses

**Pros:**

- Combines LLM reasoning with factual lookup — best of both worlds
- Reproduces Corti's 3-tool-heavy patterns (Code Validation 4 tools, Compliance Guardrail 3 tools)
- Streaming with interleaved tool calls — frontend can show "Calling verify..." status updates (matches Corti SSE `Calling expert: coding-expert`)
- Configurable tool scope per agent — supports Corti's mandatory/forbidden patterns
- Honors system prompt structure over prompt injection (CONFIRMED via Corti Probe 8)

**Cons:**

- Highest implementation complexity — MCP compat layer + tool scope enforcement + multi-turn tool-call loop
- Cost — $0.005-0.020/msg + per-tool-call cost
- Latency — 5-15s typical (LLM call) + per-tool latency (50-500ms each)
- Non-deterministic (same LLM backbone as PureLLM)
- PHI concern — both prompt AND tool-call responses may contain PHI; mitigated by `DataPolicy` redaction at MCP boundary

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Code Validation Agent | ✅ Strong | Exact Corti pattern — 4 tools mandatory (verify+guidelines+explore+search) |
| Compliance Guardrail Agent | ✅ Strong | Exact Corti pattern — 3 tools (verify+guidelines+explore), search forbidden |
| Note Completeness Agent | ⚠️ Partial | Corti uses PureLLM (0 tools) for this; LLMWithTools would be over-engineered but works |
| Medical Coding Agent | ✅ Strong | MedCodER 5-stage pipeline maps to 5 MCP tools (extract/retrieve/merge/rerank/compliance) |

---

## Provider 4 — `icoder.ensemble.v1`

**Use case:** Run N providers in parallel, vote on status. Used for high-stakes decisions where a single provider's non-determinism is unacceptable.

**Implementation:**

```python
class EnsembleProvider:
    provider_id = "icoder.ensemble.v1"
    backend_type = "ensemble"
    supports_tool_calling = True  # if any member supports
    supports_streaming = True
    deterministic = False

    def __init__(self, members: list[AgentBackendProvider], strategy: str = "majority"):
        self.members = members
        self.strategy = strategy

    async def invoke(self, req, ctx):
        responses = await asyncio.gather(*[m.invoke(req, ctx) for m in self.members])
        if self.strategy == "majority":
            return self._majority_vote(responses)
        elif self.strategy == "weighted":
            return self._weighted_vote(responses, weights=req.ensemble_weights)
        elif self.strategy == "first_non_fail":
            return next((r for r in responses if r.finish_state != "failed"), responses[0])
```

**I/O:**

- Input: `BackendRequest` + `ensemble_weights` (optional, for weighted strategy)
- Output: `OutputContract` with `status` from vote, `raw.member_responses[]` for debugging

**Pros:**

- Reduces non-determinism — majority vote over 3 LLM runs at different temperatures
- Increases robustness — single provider failure doesn't break the ensemble
- Increases accuracy — ensemble of rule + LLM catches both deterministic and semantic issues

**Cons:**

- Cost — N × member cost (3-LLM ensemble = 3× LLM cost)
- Latency — bounded by slowest member
- Implementation complexity — vote strategy must be domain-aware (majority on status, union on issues)
- Output merging — `issues[]` from N providers must be deduplicated

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Medical Coding Agent (high-stakes mode) | ✅ Strong | Ensemble of rule + LLM + RAG reduces F1 variance |
| Code Validation Agent | ⚠️ Partial | Corti uses single LLMWithTools; ensemble would 3× cost |
| Compliance Guardrail Agent | ❌ Weak | Refusal path doesn't need ensemble |
| Note Completeness Agent | ❌ Weak | Pure LLM is sufficient; ensemble would 3× cost |

---

## Provider 5 — `icoder.cascade.v1`

**Use case:** Fallback chain — try providers in order, first non-fail wins. Used for resilience when primary provider may be unavailable.

**Implementation:**

```python
class CascadeProvider:
    provider_id = "icoder.cascade.v1"
    backend_type = "cascade"
    supports_tool_calling = True  # if any member supports
    supports_streaming = True
    deterministic = False  # depends on which member succeeds

    def __init__(self, chain: list[AgentBackendProvider]):
        self.chain = chain

    async def invoke(self, req, ctx):
        errors = []
        for provider in self.chain:
            try:
                resp = await provider.invoke(req, ctx)
                if resp.finish_state != "failed":
                    resp.raw["cascade_winner"] = provider.provider_id
                    return resp
                errors.append({"provider": provider.provider_id, "error": resp.summary})
            except Exception as e:
                errors.append({"provider": provider.provider_id, "error": str(e)})
        return BackendResponse(status="fail", summary="All providers failed", raw={"cascade_errors": errors}, finish_state="failed")

    def fallback_chain(self):
        return self.chain
```

**I/O:**

- Input: `BackendRequest`
- Output: `OutputContract` with `raw.cascade_winner` indicating which provider succeeded

**Pros:**

- Resilience — primary LLM down → fallback to rule engine
- Cost-aware — cheap provider first, expensive provider only if cheap fails
- Tracks failure mode — `raw.cascade_errors[]` for debugging
- Composable with any provider type (PureLLM → RuleEngine, LLMWithTools → PureLLM, etc.)

**Cons:**

- Latency on failure — if primary fails after 5s, fallback adds another 5-15s
- Output variance — different providers produce different output shapes; `OutputContract` normalization critical
- Cascade depth — deep chains (3+) compound latency on multi-failure
- Hard to test — failure injection required for full coverage

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Medical Coding Agent | ✅ Strong | LLMWithTools → RuleEngine → cached lookup; F1 baseline preserved even on LLM outage |
| Code Validation Agent | ✅ Strong | LLMWithTools → PureLLM (without evidence) → RuleEngine (codes only) |
| Compliance Guardrail Agent | ⚠️ Partial | LLMWithTools → RuleEngine (ruleset-only); rule engine cannot handle empty-ruleset case |
| Note Completeness Agent | ⚠️ Partial | PureLLM → cached (for repeat queries); no rule-engine fallback possible |

---

## Provider 6 — `icoder.hybrid.v1`

**Use case:** Combine rule engine (deterministic) with LLM (semantic). Rule engine produces verdict; LLM produces natural-language summary explaining the verdict. Used for Medical Coding Agent default mode.

**Implementation:**

```python
class HybridProvider:
    provider_id = "icoder.hybrid.v1"
    backend_type = "hybrid"
    supports_tool_calling = True
    supports_streaming = True
    deterministic = False  # LLM summary is non-deterministic; rule verdict is deterministic

    def __init__(self, rule: AgentBackendProvider, llm: AgentBackendProvider, merge_strategy: str = "rule_first_llm_summarize"):
        self.rule = rule
        self.llm = llm
        self.merge_strategy = merge_strategy

    async def invoke(self, req, ctx):
        rule_resp = await self.rule.invoke(req, ctx)
        if self.merge_strategy == "rule_first_llm_summarize":
            llm_req = req.with_extra_context({"rule_verdict": rule_resp.raw})
            llm_resp = await self.llm.invoke(llm_req, ctx)
            return self._merge_rule_first_llm_summary(rule_resp, llm_resp)
        elif self.merge_strategy == "llm_first_rule_validate":
            llm_resp = await self.llm.invoke(req, ctx)
            rule_req = req.with_extra_context({"llm_output": llm_resp.raw})
            rule_resp = await self.rule.invoke(rule_req, ctx)
            return self._merge_llm_first_rule_validate(llm_resp, rule_resp)
```

**I/O:**

- Input: `BackendRequest` + `merge_strategy` (`rule_first_llm_summarize` | `llm_first_rule_validate`)
- Output: `OutputContract` with rule verdict + LLM summary combined; `tool_calls[]` from both providers

**Pros:**

- Preserves F1 baseline — rule engine drives code assignment, LLM only summarizes
- Adds Corti-style explainability — LLM produces "Why it matters" + evidence narrative
- Best of deterministic + LLM — verdict is reproducible, explanation is semantic
- Cost-aware — LLM only summarizes (cheaper than full LLMWithTools pipeline)

**Cons:**

- Implementation complexity — merge strategy must be domain-aware
- Two backend calls per request — rule + LLM (latency = rule_latency + llm_latency)
- Merge conflicts — if rule says PASS but LLM says WARNING, which wins? (Default: rule wins, LLM flags concern in `risk_flags[]`)
- PHI twice-exposed — both rule and LLM see PHI; mitigated by `DataPolicy` redaction at `AgentRunContext` boundary

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Medical Coding Agent | ✅ Strong | Default backend — rule for code assignment (F1), LLM for natural-language summary |
| Code Validation Agent | ⚠️ Partial | Could work but Corti uses LLMWithTools directly (rule engine lacks code-catalog evidence) |
| Compliance Guardrail Agent | ⚠️ Partial | Could work but Corti uses LLMWithTools + `{{COMPLIANCE_RULESET}}` placeholder |
| Note Completeness Agent | ❌ Weak | No rule engine to combine with — pure LLM is sufficient |

---

## Provider 7 — `icoder.external-a2a.v1`

**Use case:** Delegate to an external A2A v0.3 peer agent (e.g., Corti, third-party coding service). Used for cross-platform agent delegation.

**Implementation:**

```python
class ExternalA2AProvider:
    provider_id = "icoder.external-a2a.v1"
    backend_type = "external_a2a"
    supports_tool_calling = False  # peer agent's tools are not visible
    supports_streaming = True
    deterministic = False

    def __init__(self, peer_agent_card_url: str, auth: A2AAuthConfig):
        self.peer_url = peer_agent_card_url
        self.auth = auth

    async def stream(self, req, ctx):
        async with A2AClient(self.peer_url, self.auth) as client:
            task = await client.send_message(req.input.text)
            async for event in client.subscribe_task(task.id):
                if event.type == "text-delta":
                    yield RunTraceEvent(step=7, name="output_chunk", payload={"delta": event.delta})
                elif event.type == "tool_call":
                    yield RunTraceEvent(step=6, name="peer_tool_call", payload=event.dict())
                elif event.type == "finish":
                    yield RunTraceEvent(step=9, name="finished", payload={"state": event.state})
```

**I/O:**

- Input: `BackendRequest.input.text` (forwarded as A2A `Message.parts[0].text`)
- Output: `OutputContract` projected from peer's A2A `Message` response

**Pros:**

- Cross-platform — call Corti's `coding-expert` directly from iCoDer (if authorized)
- Allows third-party agent marketplace — ISVs can ship A2A-peer agents
- No LLM cost on iCoDer side — peer agent pays
- Reuses A2A v0.3 protocol (already implemented in `app/icoder/agent_runtime/a2a/`)

**Cons:**

- Network dependency — peer down = agent down
- Auth complexity — requires A2A auth (Bearer/mTLS/OAuth2 — already supported via Phase 3-C1)
- Output shape variance — peer's OutputContract may differ; requires `CapabilityAdapter`
- PHI concern — PHI sent to peer; mitigated by `DataPolicy` redaction + `tenant_config.allow_external_a2a` flag
- Latency — network round-trip + peer's processing time

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Medical Coding Agent | ⚠️ Partial | Could delegate to Corti for hard cases, but F1 baseline prefers local rule engine |
| Code Validation Agent | ⚠️ Partial | Could delegate to Corti's Code Validation Agent, but defeats purpose of iCoDer parity |
| Compliance Guardrail Agent | ❌ Weak | Same as above |
| Note Completeness Agent | ❌ Weak | Same as above |

---

## Provider 8 — `icoder.cached.v1`

**Use case:** Wrap any provider with a response cache. Repeat queries return cached `OutputContract` for free.

**Implementation:**

```python
class CachedProvider:
    provider_id = "icoder.cached.v1"
    backend_type = "cached"
    supports_tool_calling = True  # delegates to inner
    supports_streaming = True
    deterministic = True  # on cache hit

    def __init__(self, inner: AgentBackendProvider, cache: ResponseCache, ttl_seconds: int = 3600):
        self.inner = inner
        self.cache = cache
        self.ttl = ttl_seconds

    async def invoke(self, req, ctx):
        key = self._cache_key(req, ctx)
        cached = await self.cache.get(key)
        if cached:
            cached.raw["cache_hit"] = True
            return cached
        resp = await self.inner.invoke(req, ctx)
        await self.cache.set(key, resp, ttl=self.ttl)
        return resp

    def _cache_key(self, req, ctx):
        return hash_sha256(req.input.text + ctx.agent_id + ctx.tenant_id)
```

**I/O:**

- Input: `BackendRequest` (must be hashable — text + agent_id + tenant_id)
- Output: `OutputContract` with `raw.cache_hit` flag

**Pros:**

- Zero cost on cache hit — repeat queries free
- Zero latency on cache hit — <1ms response
- Wraps any provider — composable with all 7 other providers
- PHI-safe — cache stored in tenant-scoped KV store with TTL

**Cons:**

- Stale results — if code catalog updates, cached response may be outdated
- Cache invalidation complex — invalidation by agent_id + cache_version (must bump on rule updates)
- Storage cost — cache size grows with query volume
- Non-deterministic providers produce non-deterministic cache entries — first response is cached, subsequent responses vary

**Fit-for-purpose:**

| Agent | Fit | Reason |
|-------|-----|--------|
| Note Completeness Agent | ✅ Strong | Repeat queries on same note return cached — $0 second-run cost |
| Code Validation Agent | ⚠️ Partial | Code catalog changes invalidate; useful for stable code sets |
| Compliance Guardrail Agent | ❌ Weak | Ruleset changes invalidate; refusal path is already fast |
| Medical Coding Agent | ⚠️ Partial | Useful for batch processing of identical notes; less useful for unique encounters |

---

## Cross-provider comparison matrix

| Provider | Deterministic | Cost/msg | Latency | Tool-calling | Best agent fit |
|----------|---------------|----------|---------|--------------|----------------|
| RuleEngine | YES | $0 | <100ms | NO | Medical Coding (rule mode) |
| PureLLM | NO | $0.005-0.030 | 5-15s | NO | Note Completeness |
| LLMWithTools | NO | $0.005-0.020 | 5-15s | YES | Code Validation, Compliance Guardrail |
| Ensemble | NO | N×member | slowest+ε | any | Medical Coding (high-stakes) |
| Cascade | depends | first-success | 0-fail: fast; fail: slow | any | Medical Coding, Code Validation (resilience) |
| Hybrid | partial | rule+LLM | rule+LLM | YES | Medical Coding (default) |
| ExternalA2A | NO | peer-dependent | network+peer | N/A | Cross-platform delegation |
| Cached | YES (hit) / inner (miss) | $0 (hit) | <1ms (hit) | inner | Note Completeness, batch coding |

## Default backend_provider per official agent

Recommended defaults for the 16 existing official agent packs + 3 new Corti-parity agents:

| Agent | Current (implicit) | Recommended `backend_provider` | Reason |
|-------|---------------------|-------------------------------|--------|
| Medical Coding Agent | hardcoded HybridCodingAdapter | `icoder.hybrid.medcoder.v1` | F1 baseline + LLM explainability |
| Code Validation Agent (new) | N/A | `icoder.llm-with-tools.v1` | Corti parity — 4 mandatory tools |
| Compliance Guardrail Agent (new) | N/A | `icoder.llm-with-tools.v1` | Corti parity — 3 tools + `{{COMPLIANCE_RULESET}}` |
| Note Completeness Agent (new) | N/A | `icoder.pure-llm.v1` | Corti parity — 0 tools |
| CDI Review Agent | rule-based | `icoder.rule-engine.v1` | Deterministic CDI checks |
| Procedure Extractor | rule-based | `icoder.rule-engine.v1` | Regex extraction |
| Diagnosis Extractor | rule-based | `icoder.rule-engine.v1` | Regex extraction |
| Tabular Validator | rule-based | `icoder.rule-engine.v1` | Table schema validation |
| Index Navigator | rule-based | `icoder.rule-engine.v1` | Index lookup |
| DRG Analyzer | rule-based | `icoder.rule-engine.v1` | DRG rules |
| Evidence Ranker | rule-based | `icoder.rule-engine.v1` | Evidence scoring |
| Documentation Gap (new) | N/A | `icoder.pure-llm.v1` | Semantic gap-finding |
| Medcoder Coding Review | rule-based | `icoder.hybrid.medcoder.v1` | MedCodER 5-stage |
| Code Reconciler | rule-based | `icoder.rule-engine.v1` | Code set diff |
| Evidence Extractor | rule-based | `icoder.rule-engine.v1` | Regex extraction |
| Denial Appeals | rule-based | `icoder.rule-engine.v1` | Denial reason matching |

## Conclusion

The 8 provider types cover the full backend spectrum observed in Corti (3 patterns) plus iCoDer's existing rule-based pattern plus 4 composable meta-providers (ensemble, cascade, hybrid, cached) and 1 cross-platform option (external A2A). The `AgentBackendProvider` interface unifies them; `OutputContract` normalizes their outputs; `RunTrace` provides uniform observability.

The 3 Corti-parity agents map directly to providers 2 and 3:

- Code Validation → `icoder.llm-with-tools.v1` (4 mandatory tools)
- Compliance Guardrail → `icoder.llm-with-tools.v1` (3 tools + `{{COMPLIANCE_RULESET}}` placeholder)
- Note Completeness → `icoder.pure-llm.v1` (0 tools)

Medical Coding Agent keeps its F1 baseline via `icoder.hybrid.medcoder.v1` (rule-first + LLM-summary).
