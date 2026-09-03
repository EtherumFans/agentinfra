# Phase 5 Track D — Gate 0 Baseline + CDI Asset Audit

**Date**: 2026-07-11
**Gate**: 0 — Current state + CDI asset audit (PDF §3)
**Status**: `COMPLETE`

---

## 1. Git state

```
HEAD:        d2cf64b2d09bebc0b2fe21bb0c88b0fea8fec592
Branch:      master
Recent:      docs(track-c7): final report — READY_FOR_FORMAL_QUALITY_BENCHMARK (PDF §19 tier 1)
Working tree clean.
```

Track C (Corti Agent Runtime and Orchestrator Reconstruction) is COMPLETE — `READY_FOR_FORMAL_QUALITY_BENCHMARK` (tier 1). Track D builds on the orchestrator kernel Track C established.

## 2. Audit: current CDI assets

### 2.1 Agent packs (2 metadata-only)

| Agent pack | Path | maturity | runtime |
|---|---|---|---|
| `cdi-review` | `backend/official_agents/cdi-review/agent_pack.json` | `metadata-only` | ❌ Not runnable |
| `documentation-gap` | `backend/official_agents/documentation-gap/agent_pack.json` | `metadata-only` | ❌ Not runnable |

Both packs declare:
- system_prompt: 1-liner placeholder
- experts: `[]`
- tools: 4 stubs (`cdi_review`, `check_documentation_gaps`, `generate_cdi_query`, `extract_evidence`)
- llm_capabilities: supports_tool_calling=false, supports_json_mode=true
- code: `{}` (no actual implementation)

### 2.2 Agent registry

`backend/.icoder/agent_registry.json` lists both packs as registered certified agents. Neither has runtime.

### 2.3 Domain models

❌ No CDI gap schema exists.
❌ No Provider Query / Clarification data model exists.
❌ No Query state machine exists.
❌ No Physician Response model exists.
❌ No Documentation Version model exists.

### 2.4 API surface

❌ No `/api/cdi/runs`, `/api/cdi/queries`, etc.
✅ Existing infrastructure reusable: `/api/v1/agents/{id}/run` (unified facade), `/api/v1/coding-compliance/run` (orchestrator pattern), A2A envelope in `app.icoder.agent_runtime.orchestrator.a2a_facade`.

### 2.5 Frontend routes

❌ No `/ai-studio/cdi` route.
❌ No CDI workbench page.
❌ No Physician Response Panel.

### 2.6 Roles / permissions

`backend/app/services/permissions.py` and `backend/icoder_runtime/permissions.py` have permission presets (`medical_coding`, `cdi_audit`, `drg_analysis`, `restrictive`, `full_access`). `cdi_audit` is read-only analysis (9 tools) — close to what Track D needs, but no Query-lifecycle permissions.

### 2.7 Documentation references

| Doc | CDI mention |
|---|---|
| `CLAUDE.md` | None (only Runtime Core layer mentioned) |
| `docs/PRODUCT-MODULES.md` | `cdi_audit` preset + 9 tools + Agent #78 "CDI临床文档改进审查" |
| `docs/SOLUTION-SCENARIOS.md` | Scenario 2: CDI Agent — only as concept, no runtime spec |
| `docs/TECHNICAL-DESIGN.md` | `cdi_review` Tier2 LLM tool, `generate_cdi_query` tool, `CDIExpert` |
| `docs/architecture/CURRENT_ARCHITECTURE.md` | mentions CDI as quality-control feature |
| `docs/corti_parity/ICODER_ASSET_INVENTORY.md` | likely outdated inventory |
| `docs/product/CORTI_PARITY_ROADMAP.md` | references CDI |

**Conclusion**: CDI is mentioned across docs but **never positioned as a CORE_ENTRY_AGENT**. Always a "tool" or "preset" or "scenario", not a peer to Medical Coding.

### 2.8 Corti CDI reference (from earlier tracks)

From Track B/B-2 audits: Corti has `clinical-documentation-improvement-cdi-agent` as a top-level agent in `coding_and_revenue_cycle` use case. Corti's CDI agent has:
- Documentation Gap identification
- Clinical specificity analysis
- Non-leading Provider Query generation
- Multiple Expert collaboration (coding-expert, clinical-evidence, medical-calculator, etc.)
- Risk Flags
- Specialist Trace (which expert said what)
- Manual review + physician response loop

Track B-2 verified Corti's CDI agent shape via static analysis (no live run because Corti account lacked CDI execution permission).

## 3. Current boundary confusion (per PDF §0)

Track B-2 already clarified but docs still conflate:
- ❌ `discharge-summary-structuring` = "出院小结结构化抽取" (NOT CDI)
- ❌ `note-completeness-agent` = "形式完整性检查" (NOT CDI)
- ❌ `cdi-review` = metadata-only (no real runtime)
- ❌ `medical-coding` ≠ CDI (different lifecycle)
- ✅ `documentation-gap` should be a CDI capability/result type, not a separate top-level agent

Track D must explicitly document these boundaries across all docs.

## 4. Reusable Track C assets

Track D must REUSE (not rebuild):

| Component | Path | Purpose |
|---|---|---|
| PolicyGuard | `orchestrator/policy_guard.py` | PHI redaction + writeback policy |
| CapabilityRegistry | `orchestrator/capability_registry.py` | Expert + Tool registry with agent bindings |
| ContextBuilder | `orchestrator/context_builder.py` | Server-generated run_id + context_id |
| ResultNormalizer | `orchestrator/result_normalizer.py` | Project raw outputs to common shape |
| ConflictResolver | `orchestrator/conflict_resolver.py` | Strategy AUTORESOLVE/LLM/DEFER |
| CompletionController | `orchestrator/completion_controller.py` | Status decisioning |
| CortiLikeOrchestrator | `orchestrator/corti_like_orchestrator.py` | Facade composing all 9 components |
| CodingComplianceOrchestrator | `orchestrator/coding_compliance_orchestrator.py` | 7-stage pipeline pattern (template for CDI Orchestrator) |
| Agent Run facade | `api/agent_run.py` | unified entry, A2A envelope, trace persistence |
| A2A facade | `agent_runtime/orchestrator/a2a_facade.py` | A2A v0.3 envelope |

Track D's CDI Orchestrator will follow the same pattern as CodingComplianceOrchestrator: pure-logic class accepting a callable runner, threading a state object through N stages, ending in a review gate.

## 5. Track D scope per PDF (12 gates, 9 commits)

```
Gate 0  → baseline audit (THIS REPORT)
Gate 1  → docs realignment (cdi = CORE_ENTRY_AGENT)         commit 1: docs(track-d1)
Gate 2  → Corti CDI reverse engineering (4 reports)          commit 2: docs(track-d2)
Gate 3  → promote cdi-review → cdi core agent                commit 3: feat(track-d3)
Gate 4  → China CDI capability model (gap types + evidence)  commit 4: feat(track-d4)
Gate 5  → Provider Query data model + non-leading gate       commit 5: feat(track-d5)
Gate 6  → CDI Orchestrator + clarification lifecycle         commit 6: feat(track-d6)
Gate 7  → CDI workbench (3-pane) + Physician Response Panel  commit 7: feat(track-d7)
Gate 8  → roles + notifications + SLA + audit dashboard      commit 8: feat(track-d8)
Gate 9  → hospital integration + API + A2A                   commit 9: feat(track-d9)
Gate 10 → security red lines (folded into Gate 12)
Gate 11 → API + A2A (merged with Gate 9)
Gate 12 → security red lines                                 (in Gate 9 commit)
```

PDF §18 explicitly lists 9 commits; Gate 10/11/12 fold into the existing commit grouping.

## 6. Verdict

**PASS_GATE0** — baseline established, asset audit complete, scope confirmed.

## 7. Next: Gate 1 — Documentation realignment (P0)

Force-update all core docs to position CDI as CORE_ENTRY_AGENT. This is PDF §4's mandatory P0 task that must happen BEFORE any code work.
