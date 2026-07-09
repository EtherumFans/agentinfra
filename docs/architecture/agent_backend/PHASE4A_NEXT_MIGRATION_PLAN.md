# Phase 4-A → Phase 4-B — Next Migration Plan

**Document type:** Migration plan
**Date:** 2026-07-07
**Author:** SONG Luhua
**Scope:** What ships in Phase 4-B (first real LLM agent migration), Phase 4-C (Corti 3-agent parity), Phase 4-D (meta-providers). Phase 4-A only laid the foundation — no production agent was migrated.

---

## 0. Phase 4-A recap (what's in the ground)

Phase 4-A shipped:
- `AgentBackendProvider` Protocol + 6 supporting dataclasses (`contracts.py`).
- `ProviderRegistry` with lazy builtin registration (`registry.py`).
- `RuleEngineProvider` (production) wrapping `RuleEngineAdapter` + `rule_engine_service`.
- `PureLLMProvider` skeleton (no LLM wired).
- `LLMWithToolsProvider` skeleton (no LLM wired, but routes through `ToolMCPCompatLayer`).
- `ToolMCPCompatLayer` (provider↔MCP bridge, routes through `dispatch_tool`).
- `agent_pack.json` v1.2 schema extension (`backend_provider` + `backend_config`).
- RunTrace 9 backend metadata keys + `emit_backend_metadata_event()` helper.
- Frontend `BackendProviderSummary` component on `RunTracePage.tsx`.
- 132 new tests + 64 regression tests, all green; TypeScript 0 errors.

What Phase 4-A did NOT do:
- Did NOT migrate any of the 3 Corti parity agents (Code Validation, Compliance Guardrail, Note Completeness) to LLM.
- Did NOT wire `LLMGateway` (DeepSeek) into `PureLLMProvider` or `LLMWithToolsProvider`.
- Did NOT touch the 4 runnable official packs (`backend_provider=""` everywhere).
- Did NOT implement the 5 meta-providers (ensemble, cascade, hybrid, cached, external_a2a).
- Did NOT change the Medical Coding Agent quality logic.

---

## 1. Phase 4-B — First real LLM agent migration (Note Completeness)

**Goal:** prove the foundation works end-to-end by migrating ONE Corti-style agent from rule-engine heuristics to a real LLM backend.

### 1.1 Why Note Completeness first?

- Smallest Corti pattern: **0 tools, 6-section Markdown output**. No MCP wiring needed for the first migration — only `PureLLMProvider.invoke()` + a system prompt.
- Corti reverse engineering (Phase 3-B1.5 Part B) captured the system prompt and 6-section structure. We can replicate without guessing.
- Latency / cost benchmark exists: ~12s, $0.029672/msg (Corti probe 5/6).
- The existing iCoDer `note-completeness` official pack currently uses rule-engine heuristics — migrating to LLM is a clean A/B test (legacy vs. LLM on the same input).

### 1.2 Scope

| Step | File(s) | Effort |
|------|---------|--------|
| 1. Wire `LLMGateway` into `PureLLMProvider` | `icoder_runtime/backends/pure_llm_provider.py` (edit) + new `LLMGatewayAdapter` | S |
| 2. Update `note-completeness/agent_pack.json` to declare `backend_provider: "icoder.pure-llm.v1"` + `backend_config.llm` | `official_agents/note-completeness/agent_pack.json` (edit) | S |
| 3. Replace rule-engine system prompt with Corti-replicated Note Completeness prompt | `official_agents/note-completeness/system_prompt.md` (edit) | S |
| 4. Add `_parse_status_from_markdown` test cases for the 6 sections | `tests/unit/icoder/backends/test_pure_llm_provider.py` (extend) | S |
| 5. Add e2e test: agent run produces 6-section Markdown | `tests/e2e_product/test_note_completeness_llm.py` (new) | M |
| 6. Run baseline: 50-case Note Completeness golden set, compare to Corti probe output | `scripts/e2e_note_completeness_validation.py` (new) | M |
| 7. Emit `backend_metadata` RunTrace event from `PureLLMProvider.invoke()` | `pure_llm_provider.py` (edit) — call `emit_backend_metadata_event` | S |
| 8. Frontend: `BackendProviderSummary` already renders — verify in browser | (no code change; walkthrough) | S |

**Estimated effort:** 2-3 days.

### 1.3 Acceptance criteria

- `note-completeness` agent pack loads with `backend_provider="icoder.pure-llm.v1"` and `has_backend_config=True`.
- Agent run returns `BackendResponse` with non-empty `markdown` containing all 6 sections.
- RunTrace event has `backend_provider="icoder.pure-llm.v1"`, `backend_type="pure_llm"`, `provider_deterministic=False`, `supports_tool_calling=False`.
- 50-case baseline F1 (or equivalent Note Completeness metric) ≥ Corti probe 5/6 baseline within 10%.
- No regression in the other 3 runnable agents.

### 1.4 Forbidden in Phase 4-B

- Do NOT migrate Code Validation or Compliance Guardrail yet (they need `LLMWithToolsProvider` real LLM wiring — Phase 4-C).
- Do NOT delete the legacy rule-engine `note-completeness` system prompt — keep it as `system_prompt.legacy.md` for A/B fallback.
- Do NOT change the Medical Coding Agent.

---

## 2. Phase 4-C — Code Validation + Compliance Guardrail migration

**Goal:** migrate the 2 Corti LLM-with-tools agents. This is where `LLMWithToolsProvider` gets its real LLM wiring + the two Corti tool-scope patterns are encoded in their packs.

### 2.1 Why this order?

- Code Validation and Compliance Guardrail share the `LLMWithToolsProvider` backbone. Migrating them together amortizes the LLM wiring cost.
- The 2 tool-scope invariants (`mandatory ⊆ scope` and `forbidden ∩ scope = ∅`) are already enforced by Phase 4-A `ToolMCPCompatLayer.validate_tool_scope()`. So the migration is just pack edits + LLM wiring.

### 2.2 Scope

| Step | File(s) | Effort |
|------|---------|--------|
| 1. Wire `LLMGateway` into `LLMWithToolsProvider._real_llm_pipeline` | `llm_with_tools_provider.py` (edit) — replace `NotImplementedError` with real LLM call | M |
| 2. Implement tool-call loop (max 4 rounds, mandatory ⊆ called) | `llm_with_tools_provider.py` (edit) | M |
| 3. Update `code-validation/agent_pack.json` with `backend_provider: "icoder.llm-with-tools.v1"` + `backend_config.tools.scope=[verify,guidelines,explore,search]` + `mandatory=[verify,guidelines]` | `official_agents/code-validation/agent_pack.json` (edit) | S |
| 4. Update `compliance-guardrail/agent_pack.json` with `backend_provider: "icoder.llm-with-tools.v1"` + `scope=[verify,guidelines,explore]` + `forbidden=[search]` | `official_agents/compliance-guardrail/agent_pack.json` (edit) | S |
| 5. Replicate Corti system prompts for both agents | `system_prompt.md` for each | M |
| 6. Add e2e tests for both agents (LLM call + tool dispatch + 4-round loop) | `tests/e2e_product/test_code_validation_llm.py` + `test_compliance_guardrail_llm.py` (new) | M |
| 7. Run baseline: Corti probe 1-4 parity (latency / cost / output shape) | `scripts/e2e_corti_parity_validation.py` (extend) | M |
| 8. Emit `tool_rounds` + `fallback_used` in `backend_metadata` RunTrace event | `llm_with_tools_provider.py` (edit) | S |
| 9. Frontend: verify `BackendProviderSummary` shows `supports_tool_calling=True` + `tool_rounds` count | (walkthrough) | S |

**Estimated effort:** 4-5 days.

### 2.3 Acceptance criteria

- Both packs load with validation errors = 0 (the `mandatory ⊆ scope` and `forbidden ∩ scope = ∅` checks pass).
- Code Validation agent: 4 mandatory tool calls fired in order; final Markdown contains verify + guidelines evidence.
- Compliance Guardrail agent: `search` tool NEVER called (validated via `tool_rounds` log); 3 allowed tools called.
- Latency within 30% of Corti probes (Code Validation ~12s, Compliance Guardrail ~5s).
- RunTrace shows `supports_tool_calling=True`, `tool_rounds=4` (Code Validation) / `tool_rounds=3` (Compliance Guardrail).

---

## 3. Phase 4-D — Meta-providers

**Goal:** ship the 5 remaining backend types: `ensemble`, `cascade`, `hybrid`, `cached`, `external_a2a`. None of these have an immediate Corti parity use case, but they're in the spec for future-proofing.

### 3.1 Priority order

| Provider | Use case | Priority |
|----------|----------|----------|
| `cascade` | Try rule-engine first; fall back to LLM if rule-engine returns `warning` or `fail`. Used by Medical Coding Agent in Phase 4-E. | High |
| `cached` | Memoize expensive LLM calls by `(system_prompt + user_input) hash`. Used for batch agent runs on similar inputs. | Medium |
| `hybrid` | Run rule-engine + LLM in parallel; merge outputs. Used for compliance audits. | Medium |
| `ensemble` | Run N LLMs in parallel; majority-vote the output. Used for high-stakes coding decisions. | Low |
| `external_a2a` | Forward to a remote A2A endpoint (e.g. tenant-hosted specialist agent). Used for tenant-specific extensions. | Low |

### 3.2 Scope (per provider)

Each meta-provider is ~300 LOC + ~10 tests. Implementation pattern:

1. New file `icoder_runtime/backends/<name>_provider.py`.
2. Implement `AgentBackendProvider` Protocol.
3. Constructor takes the inner providers (e.g. `CascadeProvider(primary=rule_engine, secondary=pure_llm)`).
4. `invoke()` calls inner providers per the meta-strategy.
5. `fallback_chain()` returns the inner providers in order.
6. Register in `_register_builtin_providers()` (registry.py).
7. Add tests in `tests/unit/icoder/backends/test_<name>_provider.py`.
8. Document in `PHASE4D_META_PROVIDERS_SPEC.md` (new).

**Estimated effort:** 1-2 weeks for all 5.

### 3.3 Cascade provider sketch (the highest-priority meta-provider)

```python
class CascadeProvider:
    provider_id = "icoder.cascade.v1"
    backend_type = "cascade"
    deterministic = False  # depends on inner providers

    def __init__(self, primary: AgentBackendProvider, secondary: AgentBackendProvider,
                 *, escalate_on: set[ProviderStatus] = {"warning", "fail"}):
        self._primary = primary
        self._secondary = secondary
        self._escalate_on = escalate_on

    async def invoke(self, req, ctx):
        primary_resp = await self._primary.invoke(req, ctx)
        if primary_resp.status in self._escalate_on:
            secondary_resp = await self._secondary.invoke(req, ctx)
            secondary_resp.fallback_used = True
            secondary_resp.raw_provider_response["primary"] = primary_resp.raw_provider_response
            return secondary_resp
        return primary_resp

    def fallback_chain(self):
        return [self._primary, self._secondary]
```

This is what Medical Coding Agent will use in Phase 4-E: rule-engine first (R001-R012 deterministic), LLM second (semantic reasoning) if the rule-engine flags issues.

---

## 4. Phase 4-E — Medical Coding backend decoupling

**Goal:** decouple `MedicalCodingAgent` from its current embedded rule-engine + LLM logic, so the agent becomes a thin orchestrator that declares `backend_provider: "icoder.cascade.v1"` and delegates to the cascade provider.

### 4.1 Current state

Today, `MedicalCodingAgent` (in `app/agents/experts/medical_coding.py` or similar) has:
- Direct calls to `HybridCodingAdapter.infer_async()` (5-stage MedCodER pipeline).
- Direct calls to `RuleEngineAdapter.validate()` (R001-R012).
- Inline LLM calls via `LLMGateway`.
- RepairLoop glue.

This is ~800 LOC of business logic in the agent file. It works, but it's not portable — the same logic can't be reused by a different agent.

### 4.2 Target state

```python
# official_agents/medical_coding/agent_pack.json
{
  "format_version": "1.2",
  "agent_ref": "icoder/medical-coding-agent@1.0.0",
  "backend_provider": "icoder.cascade.v1",
  "backend_config": {
    "cascade": {
      "primary": "icoder.rule-engine.v1",
      "secondary": "icoder.medcoder-pipeline.v1",  // new in Phase 4-E
      "escalate_on": ["warning", "fail"]
    }
  }
}
```

`MedicalCodingAgent` becomes:
```python
class MedicalCodingAgent:
    async def run(self, ctx):
        provider = registry.resolve_from_agent_pack(self.pack)
        resp = await provider.invoke(self.build_request(ctx), ctx)
        return self.format_response(resp)
```

~50 LOC. The 5-stage MedCodER pipeline moves into a new `MedCoderPipelineProvider` (a thin wrapper around the existing `HybridCodingAdapter`).

### 4.3 Why this is Phase 4-E (not 4-B/C/D)

- It depends on `CascadeProvider` (Phase 4-D).
- It's the highest-stakes migration (Medical Coding is the only agent with real users). Doing it last gives us the most foundation confidence.
- The 5-stage MedCodER pipeline is already production-quality — wrapping it in a provider is mechanical work, not research.

### 4.4 Forbidden in Phase 4-E

- Do NOT rewrite the 5-stage pipeline logic. `MedCoderPipelineProvider` wraps `HybridCodingAdapter`, doesn't reimplement it.
- Do NOT change the F1 baseline (201 cases). Migration is complete only when F1 is unchanged.
- Do NOT change the frontend Medical Coding Page UX.

---

## 5. Sequencing summary

| Phase | Focus | Effort | Depends on | Outcome |
|-------|-------|--------|------------|---------|
| 4-A (done) | Foundation: contracts + registry + 3 providers (1 prod + 2 skeletons) + MCP layer + schema + RunTrace | 1 week | — | Foundation in place; 0 agents migrated |
| 4-B | Note Completeness: first LLM agent | 2-3 days | 4-A | 1 Corti-style LLM agent in production |
| 4-C | Code Validation + Compliance Guardrail: 2 LLM-with-tools agents | 4-5 days | 4-B | 3 Corti-style LLM agents in production (Corti 3-agent parity achieved) |
| 4-D | Meta-providers: cascade / cached / hybrid / ensemble / external_a2a | 1-2 weeks | 4-A | 5 meta-providers available for new agents |
| 4-E | Medical Coding backend decoupling: cascade + MedCoderPipelineProvider | 1 week | 4-D | Medical Coding Agent reduced from ~800 LOC to ~50 LOC; F1 unchanged |

**Total:** ~4-5 weeks for full Corti parity + Medical Coding decoupling.

---

## 6. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| DeepSeek V4 latency exceeds Corti baseline by >50% | Medium | Medium | Use `cached` provider (Phase 4-D) for batch runs; expose latency in `BackendProviderSummary` for monitoring. |
| Tool-scope invariants break in production (e.g. `search` accidentally called in Compliance Guardrail) | Low | High | `ToolMCPCompatLayer.validate_tool_scope()` already enforces; add a production-mode hard-fail if violated. |
| RunTrace redaction scan false-positives a backend key | Low | Low | All 9 backend keys are in `_SAFE_KEYS` (Phase 4-A Task 8); add tests for any new keys. |
| Medical Coding F1 drops after decoupling | Medium | High | Phase 4-E keeps `HybridCodingAdapter` unchanged; only the call site moves. F1 baseline test gates the migration. |
| New provider skeletons diverge from final LLM gateway API | Medium | Low | `LLMClient` Protocol is minimal (`complete` + `stream`); Phase 4-B adapter is a thin shim. |
| Meta-provider `fallback_chain` ordering causes infinite loops | Low | Medium | Each meta-provider has a max-depth check (e.g. `CascadeProvider` only escalates once). |

---

## 7. Success metrics

| Metric | Phase 4-A baseline | Phase 4-B target | Phase 4-C target | Phase 4-E target |
|--------|--------------------|------------------|------------------|------------------|
| Corti-style LLM agents in production | 0 | 1 (Note Completeness) | 3 (NC + CV + CG) | 3 |
| Medical Coding F1 (201 cases) | baseline | unchanged | unchanged | unchanged |
| Medical Coding Agent LOC | ~800 | ~800 | ~800 | ~50 |
| Backend providers available | 3 (1 prod + 2 skeleton) | 3 (1 prod + 2 real) | 3 (all real) | 8 (3 + 5 meta) |
| `BackendResponse` round-trip through `OutputContract` | ✅ | ✅ | ✅ | ✅ |
| RunTrace backend metadata visible in frontend | ✅ | ✅ | ✅ | ✅ |
| MCP dispatch never bypassed | ✅ | ✅ | ✅ | ✅ |

---

## 8. Open questions (deferred to Phase 4-B kickoff)

1. Should `PureLLMProvider` support multi-turn conversations (chat history), or only single-shot? Corti's Note Completeness is single-shot, but future agents may need chat.
2. Should `LLMWithToolsProvider` expose `tool_rounds` as a hard cap (default 4) or a soft target? Corti probes show 4 rounds for Code Validation; we don't have data for agents that legitimately need more.
3. Should `CascadeProvider` retry the secondary on `status=fail`, or accept the first response? Current sketch accepts the first response — may need a retry policy.
4. Should `cached` provider persist across process restarts (e.g. SQLite-backed), or only in-memory? In-memory is simpler; persistent helps for batch eval runs.
5. Should `external_a2a` provider authenticate via the existing MCP auth layer, or a separate A2A auth layer? Probably MCP auth (consistent with Phase 3-C), but needs confirmation.

These are all answerable within Phase 4-B; none blocks Phase 4-A sign-off.
