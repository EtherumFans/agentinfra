# Phase 4-A — Agent Backend Provider Architecture Foundation

**Document type:** Implementation Report (Phase 4-A wrap-up)
**Date:** 2026-07-07
**Author:** SONG Luhua
**Scope:** Tasks 1–8 implementation; for test results see `PHASE4A_PROVIDER_FOUNDATION_TESTING_REPORT.md`; for registry contract see `PHASE4A_PROVIDER_REGISTRY_SPEC.md`; for pack schema see `PHASE4A_AGENT_PACK_BACKEND_SCHEMA.md`; for next migration see `PHASE4A_NEXT_MIGRATION_PLAN.md`.

---

## 1. Goal

Lay the foundation so that iCoDer can host **multiple backend types** (rule engine, pure LLM, LLM with tools, ensemble, cascade, hybrid, external A2A, cached) under a **unified `AgentBackendProvider` interface**. Phase 4-A ships the contracts + registry + 3 concrete providers (one production, two skeletons) + MCP compat layer + agent_pack schema extension + RunTrace metadata. No production agent is migrated yet — that is Phase 4-B.

The foundation must not regress the 4 currently-runnable agents (`compliance-guardrail`, `code-validation`, `note-completeness`, `medical_coding`) and must not slow startup.

## 2. Deliverables (Tasks 1–8)

| Task | File(s) | LOC | Status |
|------|---------|-----|--------|
| 1 — Core contracts | `icoder_runtime/backends/contracts.py` | ~430 | ✅ |
| 1 — Package init | `icoder_runtime/backends/__init__.py` | ~30 | ✅ |
| 2 — ProviderRegistry | `icoder_runtime/backends/registry.py` | ~375 | ✅ |
| 3 — Pack schema extension | `icoder_runtime/core/agent_pack_schema.py` (edit) + `agent_pack_loader.py` (edit) | ~+90 | ✅ |
| 4 — RuleEngineProvider | `icoder_runtime/backends/rule_engine_provider.py` | ~430 | ✅ |
| 5 — PureLLMProvider skeleton | `icoder_runtime/backends/pure_llm_provider.py` | ~390 | ✅ |
| 6 — LLMWithToolsProvider skeleton | `icoder_runtime/backends/llm_with_tools_provider.py` | ~340 | ✅ |
| 7 — ToolMCPCompatLayer | `icoder_runtime/backends/tool_mcp_compat_layer.py` | ~380 | ✅ |
| 8 — RunTrace backend metadata | `app/icoder/agent_runtime/orchestrator/run_trace.py` (edit) + `frontend/src/pages/RunTracePage.tsx` (edit) | ~+220 / ~+80 | ✅ |

**Total:** ~2,400 LOC added (8 new files + 4 edited files).

## 3. Architecture decisions

### 3.1 New package layout

```
backend/icoder_runtime/backends/
├── __init__.py                    ← re-exports contracts + registry
├── contracts.py                   ← Task 1: Protocol + 6 dataclasses
├── registry.py                    ← Task 2: ProviderRegistry
├── rule_engine_provider.py        ← Task 4: production rule-engine wrapper
├── pure_llm_provider.py           ← Task 5: skeleton (Note Completeness future)
├── llm_with_tools_provider.py     ← Task 6: skeleton (Code Validation / CG future)
└── tool_mcp_compat_layer.py       ← Task 7: provider↔MCP bridge
```

The `backends/` package is a **peer** of `icoder_runtime/providers/medical_coding/`. This keeps the provider abstraction in the runtime core while leaving the existing medical-coding provider untouched.

### 3.2 Contract surface (Task 1)

`AgentBackendProvider` is a `Protocol` (Python structural typing, `@runtime_checkable`). Eight required members:

| Member | Returns | Notes |
|--------|---------|-------|
| `provider_id` | `str` | Stable ID like `icoder.rule-engine.v1` |
| `backend_type` | `BackendType` | One of 8 enum values |
| `supports_tool_calling` | `bool` | Drives MCP wiring |
| `supports_streaming` | `bool` | Drives SSE wiring |
| `deterministic` | `bool` | `True` for rule_engine / cached; `False` otherwise |
| `health()` | `ProviderHealth` | Cheap liveness probe; never raises |
| `invoke(req, ctx)` | `BackendResponse` | Single-shot execution |
| `stream(req, ctx)` | `AsyncIterator[dict]` | SSE-style streaming |
| `output_contract()` | `str` | Schema ref like `icoder/RuleEngineOutput/v1` |
| `fallback_chain()` | `list[AgentBackendProvider] \| None` | For cascade / hybrid |
| `capabilities()` | `ProviderCapability` | For Hub UI + `icoder pack validate` |

Supporting dataclasses: `BackendRequest`, `BackendResponse`, `AgentRunContext`, `OutputIssue`, `ToolCallRecord`, `ProviderHealth`, `ProviderCapability`, plus Pydantic `OutputContract` (the schema validator used by Phase 4-B RepairLoop).

`BackendResponse.to_output_contract()` normalizes any provider's response into an `OutputContract` so downstream code (RepairLoop, audit log) doesn't branch on provider.

### 3.3 ProviderRegistry (Task 2)

Process-wide singleton (`get_default_registry()`). Thread-safe via single `RLock`. Lazy builtin registration — `__init__` is empty; the 3 Phase 4-A providers register on first `get()` / `list()` / `resolve_from_agent_pack()` call.

- `register(provider)` — duplicate `provider_id` raises `ValueError`.
- `get(provider_id)` — raises `ProviderNotRegisteredError` with actionable message listing registered IDs.
- `get_or_default(provider_id)` — falls back to `DEFAULT_FALLBACK_PROVIDER_ID = "icoder.rule-engine.v1"` when `provider_id` is `None` / empty (legacy v1.0 packs).
- `list()` / `list_by_type(t)` / `list_capabilities()` / `health(id)` / `health_all()`.
- `resolve_from_agent_pack(pack)` — reads `backend_provider` (top-level OR nested under `agent`) and returns the registered provider.

`auto_register_builtins: bool = True` constructor flag lets tests disable lazy registration for isolation.

### 3.4 Agent pack schema extension (Task 3)

`NormalizedPack` gained two fields:

```python
backend_provider: str = ""           # empty = legacy pack (use default fallback)
backend_config: dict[str, Any] = field(default_factory=dict)
```

Loader (`_populate_backend_provider(p)`) accepts both placements:
- top-level: `{"backend_provider": "...", "backend_config": {...}}`
- nested under `agent`: `{"agent": {"backend_provider": "...", "backend_config": {...}}}`

Validation (writes to `validation_errors` / `validation_warnings`):
- `backend_provider` must be a string; non-string → warning, falls back to default.
- `backend_config` must be a dict; non-dict → warning.
- `backend_config.tools.scope` must be a list; `mandatory ⊆ scope` (else error); `forbidden ∩ scope = ∅` (else error).

`to_summary()` exposes `backend_provider` + `has_backend_config` so the Agent Hub card can render the backend form.

**Backward compat:** the 4 runnable official packs load with `status=executable` and zero new validation errors.

### 3.5 RuleEngineProvider (Task 4)

`provider_id="icoder.rule-engine.v1"`, `backend_type="rule_engine"`, `deterministic=True`, `supports_tool_calling=False`, `supports_streaming=False`.

Wraps (no business-logic duplication):
- `icoder_runtime.providers.medical_coding.rule_engine_adapter.RuleEngineAdapter` (R001–R012 ICD-10 / ICD-9-CM-3 format + duplicate + consistency checks).
- `app.services.rule_engine.rule_engine_service` (15-rule KB lookup via `retrieve_rules`).
- `_FallbackRuleEngineAdapter` — defensive stub when the real adapter import fails (only R001 primary-diagnosis-non-empty; production never hits this).

Accepts 3 input shapes via `req.input`:
| Shape | Field | Use case |
|-------|-------|----------|
| `coding_output` (MedicalCodingOutputSchema dict) | direct R001-R012 validation | MedCodER RepairLoop |
| `coding_set` (primary/secondary/procedures) | projected to schema, then R001-R012 | compliance-guardrail / code-validation legacy path |
| `topic` (string) | KB lookup via `retrieve_rules` | knowledge retrieval |

Normalizes `CodingIssue.severity` {critical,high,medium,low,info} → `OutputIssue.severity` {critical,error,warning,info} via `severity_map`. Status verdict: `pass` if `result.passed`; `fail` if any critical issue; `warning` otherwise.

### 3.6 PureLLMProvider skeleton (Task 5)

`provider_id="icoder.pure-llm.v1"`, `backend_type="pure_llm"`, `deterministic=False`, `supports_tool_calling=False`, `supports_streaming=True`.

Mirrors Corti Note Completeness Agent pattern (0 tools, 6-section Markdown). Defines `LLMClient` Protocol (injected — not hardcoded to DeepSeek). Phase 4-A ships with **no LLM wired**; `invoke()` returns a deterministic placeholder envelope so tests can verify the contract without external calls.

`_parse_status_from_markdown(text)` heuristic scans the LLM output for the 9 status keywords. Order: `requires_review / non_compliant / compliant / incomplete / unclear / warning / fail / complete / pass` — `complete` precedes `pass` so `"All checks passed"` doesn't shadow an explicit `"# Status: complete"`.

Phase 4-B will inject `LLMGateway` (DeepSeek) as the `LLMClient`; the provider itself doesn't change.

### 3.7 LLMWithToolsProvider skeleton (Task 6)

`provider_id="icoder.llm-with-tools.v1"`, `backend_type="llm_with_tools"`, `deterministic=False`, `supports_tool_calling=True`, `supports_streaming=True`.

Mirrors Corti Code Validation (4 mandatory tools) and Compliance Guardrail (3 tools, `search` forbidden) patterns. Holds a `ToolMCPCompatLayer` instance.

`validate_tool_scope(req)` enforces the two Corti invariants:
- `set(mandatory_tools) ⊆ set(tool_scope)` — Code Validation requires `verify + guidelines`.
- `set(forbidden_tools) ∩ set(tool_scope) = ∅` — Compliance Guardrail forbids `search`.

Skeleton path (`_skeleton_pipeline`): runs **one** tool call through `ToolMCPCompatLayer.call()` and emits placeholder markdown listing the call. Real LLM pipeline (`_real_llm_pipeline`) raises `NotImplementedError` → wrapped as a fail envelope noting Phase 4-B.

### 3.8 ToolMCPCompatLayer (Task 7)

Bridge between provider-native tool calls and the MCP gateway. Provider code never talks to MCP dispatch directly — it goes through this layer.

| Method | Purpose |
|--------|---------|
| `list_available_tools()` | Wraps `list_tools_fn` (defaults to MCP `tools/list`) |
| `validate_tool_scope(scope, mandatory, forbidden)` | Enforces the two Corti invariants |
| `call(tool_name, args, request)` | Routes through `dispatch_tool_fn` (defaults to MCP `tools/dispatch`) — never bypasses |
| `provider_to_mcp(BackendResponse)` | Projects provider response → MCP `tools/call` result envelope |
| `mcp_to_provider(mcp_result)` | Projects MCP result → `ToolCallRecord` |
| `to_tool_call_record(tool_name, mcp_result, duration_ms)` | Builds `ToolCallRecord` for RunTrace |

Defense-in-depth: `_strip_secret_keys(result)` blankens `token / api_key / authorization / set-cookie / x-api-key` in any tool result before it reaches the provider.

### 3.9 RunTrace backend metadata (Task 8)

Added 9 keys to `_SAFE_KEYS` in `run_trace.py` so the defensive redaction scan leaves them intact:

```python
"backend_provider", "backend_type", "provider_latency_ms",
"provider_status", "provider_deterministic",
"supports_tool_calling", "fallback_used", "output_contract",
"tool_rounds",
```

New helper `emit_backend_metadata_event(run_id, backend_provider, backend_type, provider_latency_ms, provider_status, provider_deterministic, supports_tool_calling, fallback_used, output_contract, tool_rounds, *, step=OUTPUT_GENERATED, store)` writes a single RunTrace event with all 8 fields populated in `safe_metadata`. `provider_latency_ms` is mirrored to `duration_ms` so the trace timeline shows provider latency correctly.

Frontend: `RunTracePage.tsx` gained a `BackendProviderSummary` component rendering the 8 fields as a card. Wired into both the dispatcher path (under `dispatcher_detail`) and the non-dispatcher path (under `output_generated` / `completion`).

## 4. Forbidden actions (per Task spec) — verified not done

| Forbidden | Verification |
|-----------|--------------|
| Don't rewrite Medical Coding Agent quality logic | RuleEngineProvider reuses `RuleEngineAdapter` + `rule_engine_service`; no copy-paste of rule logic. |
| Don't migrate 3 Corti parity agents to LLM yet | 4 official packs still have `backend_provider=""` (legacy rule-engine path). |
| Don't delete existing rule-engine | `RuleEngineAdapter` + `rule_engine_service` imports unchanged; provider only wraps them. |
| Don't hardcode DeepSeek V4 to new provider interface | `PureLLMProvider` takes `LLMClient` Protocol; no `import DeepSeek` anywhere in `backends/`. |
| Don't extend 20 Agent roster | No new `official_agents/` directories added. |
| Don't change unrelated UI | Only `RunTracePage.tsx` touched (Phase 4-A scope). |

## 5. Test surface (Task 9)

132 new tests + 64 regression tests pass. See `PHASE4A_PROVIDER_FOUNDATION_TESTING_REPORT.md` for the full breakdown.

| Suite | Tests | Status |
|-------|-------|--------|
| `test_contracts.py` | 17 | ✅ |
| `test_registry.py` | 23 | ✅ |
| `test_rule_engine_provider.py` | 14 | ✅ |
| `test_pure_llm_provider.py` | 15 | ✅ |
| `test_llm_with_tools_provider.py` | 11 | ✅ |
| `test_tool_mcp_compat_layer.py` | 16 | ✅ |
| `test_agent_pack_backend_schema.py` | 13 | ✅ |
| `test_run_trace_backend_metadata.py` | 16 | ✅ |
| `test_agent_pack_loader.py` (regression) | 48 | ✅ |
| `test_run_trace_db_store.py` + `test_run_trace_store.py` (regression) | 16 | ✅ |
| **Total** | **196** | **✅** |

Frontend TypeScript: **0 errors** (`npx tsc --noEmit`).

## 6. PASS criteria (10 conditions)

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Task 1 contracts implemented | ✅ `contracts.py` shipped |
| 2 | Task 2 registry lazy-inits, no startup cost | ✅ `__init__` empty; lazy on first `get()` |
| 3 | Task 3 schema extension backward compatible | ✅ 4 runnable packs still `executable` |
| 4 | Task 4 RuleEngineProvider deterministic | ✅ `deterministic=True` |
| 5 | Task 5 PureLLMProvider skeleton streams | ✅ 3-event sequence |
| 6 | Task 6 LLMWithToolsProvider skeleton enforces scope | ✅ mandatory ⊆ scope; forbidden ∩ scope = ∅ |
| 7 | Task 7 ToolMCPCompatLayer routes through dispatch_tool | ✅ never bypasses |
| 8 | Task 8 RunTrace 8 backend keys in `_SAFE_KEYS` | ✅ defensive scan leaves them intact |
| 9 | Task 9 132 targeted tests + TypeScript 0 error | ✅ 196/196 tests pass; tsc 0 |
| 10 | 4 runnable agents no regression | ✅ all load `executable`, no new validation errors |

## 7. Verdict

**Phase 4-A PASS.** The foundation is in place: any future agent (Phase 4-B Note Completeness, Code Validation, Compliance Guardrail migration; Phase 4-D meta-providers) can declare a `backend_provider` in its `agent_pack.json` and the runtime will route through the unified `AgentBackendProvider.invoke()` / `stream()` interface — no executor branching, no MCP bypass, no PHI leakage, no redaction damage to backend metadata.

Phase 4-B can proceed: wire `LLMGateway` into `PureLLMProvider` and migrate Note Completeness as the first real LLM agent.
