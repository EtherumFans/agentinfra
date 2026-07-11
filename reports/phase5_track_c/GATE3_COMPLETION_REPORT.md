# Phase 5 Track C — Gate 3 Completion Report

**Date**: 2026-07-11
**Gate**: 3 — Corti-compatible Orchestrator kernel (§8.1 explicit components)
**Verdict**: `PASS_GATE3_KERNEL_READY_FOR_GATE4_MAINLINE`

---

## 1. Gate 3 scope (from PDF §8)

The PDF §8 mandate has two parts:

| § | Requirement | Status |
|---|---|---|
| §8.1 | Implement CortiLikeOrchestrator with explicit ContextBuilder + Planner + CapabilityRegistry + Delegator + ResultNormalizer + Aggregator + ConflictResolver + CompletionController + PolicyGuard | ✅ Closed |
| §8.2 | Audit existing 5-state state machine + Planner/Delegator/Aggregator/Context for production wiring; choose reuse-and-modify OR refactor-with-compat; never keep two parallel main Orchestrators | ✅ Closed (reuse-and-modify) |

## 2. §8.2 Audit findings

The existing orchestrator modules at `backend/app/icoder/agent_runtime/orchestrator/` were **heavily wired into production** (not isolated):

- `a2a_facade.py` imports from `inbound_handler` + `run_trace`
- `app/main.py` lifespan constructs Planner/Delegator/Aggregator/InboundHandler (12+ imports)
- `agent_run.py` uses `run_trace` for cost-recording
- 6 production experts import `delegator` (coding/code_reconciler/evidence_extractor/index_navigator/tabular_validator)
- 200+ tests across `tests/unit/icoder/orchestrator/` + `tests/unit/icoder/agent_runtime/` + `tests/e2e/icoder/` exercise these modules
- MCP server (`app/icoder/mcp/server.py`) uses `run_trace`

**§8.1 component mapping vs existing modules:**

| §8.1 Target | Existing Module | Status |
|---|---|---|
| Planner | `planner.py` (394 LOC) | ✅ reuse (LLM-driven, 3-retry, JSON-validation) |
| Delegator | `delegator.py` (272 LOC) | ✅ reuse (sequential, per-expert retry policy) |
| Aggregator | `aggregator.py` (253 LOC) | ✅ reuse (priority sort + conflict detect) |
| State Machine | `state_machine.py` (126 LOC) | ✅ reuse (received→planning→delegating→aggregating→completed/failed) |
| RunContext | `run_context.py` (68 LOC) | ✅ reuse |
| InboundHandler | `inbound_handler.py` (578 LOC) | ✅ reuse (wire-level entry point) |
| PHI Redactor | `phi_redactor.py` | ✅ reuse (was already PolicyGuard-equivalent for input stage) |
| Wiring | `wiring.py` (399 LOC) | ✅ reuse (Planner/Delegator/Aggregator factory) |
| **ContextBuilder** | implicit in InboundHandler steps 2-3 | ⚠️ extracted to new `context_builder.py` |
| **CapabilityRegistry** | implicit in agent_provider + agent.expert_ids | ⚠️ extracted to new `capability_registry.py` |
| **ResultNormalizer** | ❌ missing | ✅ new `result_normalizer.py` |
| **ConflictResolver** | partial (`Aggregator._detect_conflicts`) | ✅ new `conflict_resolver.py` (adds autoresolve vs defer policy) |
| **CompletionController** | ❌ missing | ✅ new `completion_controller.py` |
| **PolicyGuard** | partial (PHI redactor + writeback block) | ✅ new `policy_guard.py` (centralized gate) |

**Decision per §8.2**: REUSE-AND-MODIFY. The existing modules are battle-tested. Building a parallel CortiLikeOrchestrator would (a) invalidate 200+ tests, (b) violate the "no two parallel main Orchestrators" rule, and (c) duplicate working retry/state-machine/PHI logic.

The new CortiLikeOrchestrator is therefore a **facade** — it names the existing modules using §8.1 vocabulary and adds the missing components as composable layers. It does NOT replace InboundHandler; it wraps it and exposes the §8.1 components individually for Gate 4 to call.

## 3. Files added (Gate 3)

| File | LOC | Purpose |
|---|---|---|
| `backend/app/icoder/agent_runtime/orchestrator/policy_guard.py` | 110 | Centralized safety boundary (PHI + writeback + residency) |
| `backend/app/icoder/agent_runtime/orchestrator/capability_registry.py` | 130 | Explicit Expert + Tool registry with agent bindings |
| `backend/app/icoder/agent_runtime/orchestrator/context_builder.py` | 75 | Explicit RunContext construction with server-generated IDs |
| `backend/app/icoder/agent_runtime/orchestrator/result_normalizer.py` | 145 | Projects raw expert outputs into NormalizedExpertResult |
| `backend/app/icoder/agent_runtime/orchestrator/conflict_resolver.py` | 115 | LLM-driven conflict resolution (autoresolve vs defer) |
| `backend/app/icoder/agent_runtime/orchestrator/completion_controller.py` | 145 | Semantic completeness gate (COMPLETED/WARNINGS/REVIEW/INCOMPLETE) |
| `backend/app/icoder/agent_runtime/orchestrator/corti_like_orchestrator.py` | 235 | Facade composing all 9 §8.1 components |
| `backend/tests/unit/icoder/orchestrator/test_corti_like_orchestrator.py` | 290 | 20 tests covering all 7 new modules |

**Total**: ~1245 LOC new (1010 src + 235 test façade), 0 LOC removed. No existing module modified — purely additive.

## 4. Test evidence

```
tests\unit\icoder\orchestrator\test_corti_like_orchestrator.py ............ [ 60%]
..........                                                              [100%]

======================== 20 passed, 1 warning in 1.63s ========================
```

Coverage by component:

| Component | Tests | Key cases |
|---|---|---|
| PolicyGuard | 3 | success / redactor-fail / passthrough |
| CapabilityRegistry | 2 | register+lookup / agent-provider builder |
| ContextBuilder | 2 | unique IDs / data-part text extraction |
| ResultNormalizer | 4 | evidence / procedure / error / compliance-issues |
| ConflictResolver | 3 | autoresolves drg_code / defers primary_dx / empty |
| CompletionController | 5 | clean / no-codes / critical-violation / conflict-deferred / expert-failed |
| CortiLikeOrchestrator facade | 1 | end-to-end handle() + metadata block |

## 5. Regression check

Full orchestrator + agent_runtime regression: **362 passed / 1 pre-existing fail**. The 1 failure (`test_three_runnable_agents.py::test_compliance_guardrail_passes_complete_case`) is pre-existing — verified via `git stash` + re-run; the failure persists without my changes.

## 6. §8.1 component contract summary

### ContextBuilder
```python
artifact = ctx_builder.build(agent_id="ag", parts=[...])
# artifact.run_context.run_id  (server-generated UUID)
# artifact.run_context.context_id  (server-generated UUID, Q4 strict isolation)
# artifact.original_text  (extracted from parts)
```

### PolicyGuard
```python
decision = guard.evaluate_input(raw_input="...", agent_id="...")
# decision.allowed: bool
# decision.redacted_text: str  (PHI-stripped)
# decision.production_writeback_blocked: True  (always True per spec)
```

### CapabilityRegistry
```python
reg.experts_for_agent("medical-coding-agent") → list[ExpertCapability]
reg.lookup_expert("evidence-extractor") → ExpertCapability | None
reg.expert_ids_for_agent("ag") → ["evidence-extractor", ...]
```

### ResultNormalizer
```python
normalized = normalize_expert_result("evidence-extractor", raw_dict)
# normalized.codes_emitted: list[str]  (all ICD codes from any field path)
# normalized.procedures_emitted: list[str]
# normalized.issues: list[dict]  (rule violations + risks + deficits)
# normalized.confidence: float | None
```

### ConflictResolver
```python
resolutions = resolver.resolve({"primary_diagnosis.code": [...]})
# resolutions[0].strategy ∈ {autoresolve, llm_resolve, defer_to_human}
# resolutions[0].deferred_to_human: True for primary_dx (high-stakes)
```

### CompletionController
```python
decision = ctrl.evaluate(normalized=normalized, conflicts=resolutions)
# decision.status ∈ {COMPLETED, COMPLETED_WITH_WARNINGS, NEEDS_HUMAN_REVIEW, INCOMPLETE}
# decision.must_replan: True only on INCOMPLETE
# decision.review_required: True on NEEDS_HUMAN_REVIEW
```

### CortiLikeOrchestrator (facade)
```python
orch = CortiLikeOrchestrator(phi_redactor=..., planner=..., delegator=...,
                              aggregator=..., agent_provider=...)
response = orch.handle(agent_id, request)  # delegates to InboundHandler
# + post-aggregate hooks: normalize → resolve → completion-decide
# + response.metadata["corti_like_orchestrator"] = {components, agent_id, capability_count}
```

## 7. What this closes

- ✅ §8.1 explicit component vocabulary: every Corti-style component is now a named, testable class
- ✅ §8.2 production-wiring audit: existing modules confirmed wired + reused, no parallel orchestrator
- ✅ Foundation for Gate 4: coding-compliance mainline can call ContextBuilder → PolicyGuard → Planner → Delegator → ResultNormalizer → ConflictResolver → CompletionController as a stable API
- ✅ Human-review gate: CompletionController now distinguishes COMPLETED / WARNINGS / NEEDS_HUMAN_REVIEW / INCOMPLETE — required by Gate 4 §9.4 (Human Review Gate)

## 8. Deferred to Gate 4

- LLM_RESOLVE strategy: ConflictResolver returns the strategy value but Gate 4 actually executes the LLM call (only when principal-dx-review reports `coding_draft_consistent=false`)
- InboundHandler hooks: Gate 3 leaves InboundHandler unchanged and adds post-aggregate hooks via facade. Gate 4 may refactor InboundHandler to expose intermediate ExpertResult for the hooks to consume properly.
- Capability registry population: Gate 3 builds the registry from agent_provider; full population (with MCP tool introspection) lands when Gate 4 wires it into the lifespan.

## 9. Next: Gate 4 — Coding compliance orchestrator mainline

Gate 4 implements the 7-stage coding compliance mainline per §9:
1. discharge-summary-structuring (input)
2. medical-coding-agent (codes)
3. principal-diagnosis-review (primary dx)
4. evidence-extractor (tiers)
5. compliance-guardrail (violations)
6. note-completeness (deficits)
7. drg-analyzer (risk)

Plus CaseState accumulator + Human Review Gate (AUTO_PASS / REVIEW_RECOMMENDED / REVIEW_REQUIRED / BLOCKED_*).
