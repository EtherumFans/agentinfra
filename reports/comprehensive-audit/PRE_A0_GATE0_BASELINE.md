# Pre-A0 Gate 0 — Git, Audit and Corti Evidence Baseline

> First-round output for `Pre-A0 — Corti Developer Foundation Gap Reconciliation`.
> Scope: read-only audit. No code changes. No feature additions. No Agent/Expert/Tool/Runtime expansion. No Prompt edits. No historical-verdict rewrite.

This gate establishes the starting point. Per spec §20, the first round must surface 18 specific items before any further Pre-A0 gate runs.

---

## 1. Current Git HEAD

```
c147d015455017bc1d8420cbdbd813b3b8ec23ce
```

Short hash: `c147d01`. Subject: `feat(track-h): Tier 2 Corti controlled probes — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells`. Authored 2026-07-13 22:30:45 +0800.

## 2. Current Branch

```
master
```

Mainline. No Pre-A0 branch cut. No new commits will be authored by this task (reports + evidence only; no production code).

## 3. Working Tree Status

- 85 entries modified or untracked (per `git status --porcelain | wc -l`).
- `git diff --stat HEAD`: 32 tracked files changed, +2,208/-616 lines.
- Status breakdown (qualitative from initial `git status`):
  - Modified backend: `app/api/agent_run.py`, `app/api/embedded.py`, `app/api/platform_api_clients.py`, `app/api/usage.py`, `app/main.py`, `app/middleware/auth.py`, `app/models/__init__.py`, `app/models/oauth.py`, `app/models/run_history.py`, `tests/conftest.py`, `tests/test_api/test_phase4f_agent_run.py`
  - Modified frontend: `App.tsx`, `components/layout/Layout.tsx`, `i18n/locales.ts`, `tests/e2e/phase5_a4_embedded.spec.ts`
  - Modified packages: `icoder-embedded/{dist,src,package.json}`, `icoder-sdk/{README.md, package.json, src/*, tsconfig.json}`; `packages/icoder-sdk/package-lock.json` deleted.
  - New backend files: `alembic/versions/012..015` (4 migrations), `app/api/examples.py`, `app/api/preview_sessions.py`, `app/api/runs.py`, `app/middleware/partner_cors.py`, `app/models/idempotency_record.py`, `app/models/preview_session.py`, `app/services/{idempotency_service,preview_ticket,run_lifecycle,trace_token}.py`, `tests/test_api/test_phase7_gate1_examples_mount.py`, more under `tests/test_api/`.
- All 85 entries are **pre-existing Phase 7 in-flight work** that was already in the working tree before the comprehensive audit started (2026-07-15 16:15). They are not caused by the audit, and Pre-A0 will not commit them.

## 4. Audit Report Git Baseline

The 14 Gate reports under `reports/comprehensive-audit/` were written 2026-07-15 16:15 → 2026-07-16 00:00 against this same commit `c147d01`. No commit was made between audit start and audit closure.

## 5. Gate 14 ↔ Current Code Drift

- HEAD unchanged: `c147d01` (audit start) == `c147d01` (now).
- Working tree: same 85 modified entries, same +2,208/-616 line delta.
- Gate 14 conclusions were drawn from code at this HEAD; conclusions still valid.
- Verdict for this sub-item: **`NO_BASELINE_DRIFT`**.

## 6. Identified Agent Directories

| Path | Role (initial) | Layer |
|------|----------------|-------|
| `backend/app/agents/` | "Hierarchy A" expert-style agents (legacy entry surface) | App layer |
| `backend/app/agents/experts/` | 11 expert files (audit / cdi / denial / diagnosis / drg / evidence / hcc / homepage / procedure / report / timeline) | Hierarchy A |
| `backend/app/icoder/agent_runtime/experts/` | 5 MedCodER-stage experts (code_reconciler / coding / evidence_extractor / index_navigator / tabular_validator) | Hierarchy B |
| `backend/official_agents/` | 30 packaged agent directories (cdi-review, clinical-documentation-improvement-agent, code_reconciler, code_validation, compliance-guardrail, denial-appeals, diagnosis-extractor, discharge_edu, discharge_summary_structuring, documentation-gap, drg-analyzer, evidence_extractor, evidence-ranker, icd10_navigator, icu_summary, index_navigator, med_reconciliation, medcoder-coding-review, medical_coding, note_completeness, nursing_handoff, principal_diagnosis_review, prior_auth, procedure-extractor, referral_gen, rule_explainer, surgical_registry, tabular_validator, triage, …) | Hierarchy C |
| `backend/app/icoder/agent_runtime/cdi/` | CDI orchestrator + gates + real_runner | Hierarchy B sub-layer |

**Note**: 30 in `official_agents/` is greater than the 13 "metadata-only" agents claimed in Gate 4/14. Pre-A0 Gate 2 will reconcile the delta. Many `official_agents/` directories appear in both kebab-case and snake_case variants (e.g., `code_validation` and `code-validation`), suggesting either duplication or packaging artefact — must verify.

## 7. Identified Expert Directories

Three distinct hierarchies (confirms Gate 6 / Gate 14 historical claim, subject to deeper reverification in Pre-A0 Gate 3):

| Hierarchy | Location | Count | Sample |
|-----------|----------|-------|--------|
| A (legacy) | `backend/app/agents/experts/` | 11 | audit, cdi, denial, diagnosis, drg, evidence, hcc, homepage, procedure, report, timeline |
| B (MedCodER 5-stage) | `backend/app/icoder/agent_runtime/experts/` | 5 | code_reconciler, coding, evidence_extractor, index_navigator, tabular_validator |
| C (packaged agents as "experts") | `backend/official_agents/` | 30 | (see §6) |

Plus CDI internal pseudo-experts: `backend/app/icoder/agent_runtime/cdi/cdi_expert_router.py`, `claim_evidence_gate.py`, `necessity_gate.py`, `necessity_semantic.py`, `nlq_gate.py`, `nlq_semantic.py`, `orchestrator.py`, `query_eligibility_gate.py`, `real_runner.py`, `single_dimension_gate.py`.

## 8. Identified Tool / MCP Directories

| Path | Count | Notes |
|------|------|-------|
| `backend/app/tools/` | 11 files | analysis_tools, coding_tools, explore_code, extraction_tools, report_tools, retrieve_rules, safety_tools, search_codes, verification_tools, verify_sequence (legacy tool layer — Gate 6 claims MCP-disconnected) |
| `backend/app/icoder/mcp/` | top-level | server.py, tool_registry.py, auth.py, auth_resolver.py, errors.py, handlers/ |
| `backend/app/icoder/mcp/handlers/` | 12 MCP handlers | calibrate_confidence, check_documentation_gaps, evaluate_compliance, explore_code, get_differentiation_hint, get_guidelines, rerank_codes, search_codes, search_icd, validate_codes, verify_code |
| `backend/icoder_runtime/tool_registry.py` | 1 | Runtime-level tool registry |
| `backend/icoder_runtime/backends/tool_mcp_compat_layer.py` | 1 | Compatibility shim between legacy tools and MCP |
| `backend/tools/` (top-level tools/) | TBD | Pre-A0 Gate 2 will inventory |

## 9. Identified Runtime Directories

Confirms 3-layer claim (Gate 6/14). Each must be verified for live inbound calls in Pre-A0 Gate 3.

| Runtime | Path | Entry Artifacts | Claimed Role |
|---------|------|-----------------|--------------|
| Runtime-1 (icoder_runtime / runtime core) | `backend/icoder_runtime/` | core/, backends/, providers/, embedded/, m2a/, observability/ | "Runtime Core" per CLAUDE.md — AgentPackageV1 loader, LLMGateway, Registry |
| Runtime-2 (coding_runtime) | `backend/app/coding_runtime/` | base.py, dispatcher.py, fast_runtime.py, medcoder_runtime.py | MedCodER 5-stage execution + fast path |
| Runtime-3 (agent_runtime / corti-like) | `backend/app/icoder/agent_runtime/` | orchestrator/, experts/, a2a/, context/, cdi/, a2a_facade.py | Corti-style orchestrator + A2A surface + CDI orchestrator |

`icoder_runtime/embedded/platform_runtime.py` is the Corti-style "PlatformRuntime" entrypoint that AgentRunner dispatches into. Pre-A0 Gate 3 will confirm whether `coding_runtime` and `agent_runtime` are independently invoked, or whether `coding_runtime` is now a sub-component of `agent_runtime/orchestrator/corti_like_orchestrator.py`.

## 10. Identified Registries

| Registry | Path | Manages |
|----------|------|---------|
| RuntimeAgentRegistry | `backend/icoder_runtime/core/registry.py` + `registry_backend.py` + `registry_status.py` | Packaged `.icoder-agent` registration |
| CapabilityRegistry | `backend/app/icoder/agent_runtime/orchestrator/capability_registry.py` | Per-agent declared capabilities (Corti-style) |
| ToolRegistry (legacy) | `backend/app/tools/__init__.py` (likely) + `backend/app/icoder/mcp/tool_registry.py` | Dual home — Pre-A0 Gate 2 will verify |
| ToolRegistry (runtime) | `backend/icoder_runtime/tool_registry.py` | Runtime-level tool registry |
| Schema Registry (A2A) | `backend/app/icoder/agent_runtime/a2a/schema_registry.py` | A2A JSON-RPC schema dispatch |

Pre-A0 Gate 3 must answer: which registry is authoritative at run time, and which are read-only mirrors or stale duplicates.

## 11. Identified A2A Entry Points

| Surface | Path | Notes |
|---------|------|-------|
| A2A routes | `backend/app/icoder/agent_runtime/a2a/a2a_routes.py` | Top-level A2A router |
| Inbound (JSON-RPC) | `routes_inbound.py` | message/send, task/* etc. |
| Outbound | `routes_outbound.py` | Delegated calls to other agents |
| Task stub | `routes_task_stub.py` | Per Gate 6: tasks endpoint is a 501 stub |
| Discovery | `routes_discovery.py` | Agent Card / `.well-known/agent.json` |
| Envelope / Parts / Messages | `envelope.py`, `parts.py`, `messages.py` | A2A v0.3 message envelope |
| Agent Card | `agent_card.py` | Card serialization |
| Metadata | `icoder_metadata.py`, `version.py`, `errors.py` | A2A metadata plumbing |

A2A facade (shared with non-A2A entrypoints): `backend/app/icoder/agent_runtime/a2a_facade.py` (~345 LOC per memory).

## 12. Identified SDK Entry Points

| SDK | Path | Surface |
|-----|------|---------|
| `@icoder/sdk` (TypeScript) | `packages/icoder-sdk/src/` | client.ts, index.ts, types.ts + 11 resources: agents, billing, compliance, facts, marketplace, oauth, reviews, runs, runtime, speech-to-text, textgen |
| `@icoder/embedded` (Web Component) | `packages/icoder-embedded/src/icoder-assistant.ts` | iframe widget bootstrap |
| Python SDK | `packages/icoder-python/` | Pre-A0 Gate 2 will inventory scope |
| Web components | `packages/icoder-web/`, `packages/web-components/` | Pre-A0 Gate 2 will inventory |
| Examples | `packages/examples/` | Partner reference app etc. |

## 13. Corti Official Evidence Collection Checklist

The following Corti public doc pages must be re-verified per spec §4.1. Saved under `reports/comprehensive-audit/evidence/corti-foundation/official-docs/`. Each entry will record: page title, official identifier, access date, key claim, current API path, current schema, beta status, coming-soon status, login required, publicly verifiable, local evidence path, SHA-256.

| # | Topic | Source | Status |
|---|-------|--------|--------|
| 1 | Agent List | `docs.corti.ai/agentic/agents/list` | TODO |
| 2 | Agent Create | `docs.corti.ai/agentic/agents/create` | TODO |
| 3 | Agent Get | `docs.corti.ai/agentic/agents/get` | TODO |
| 4 | Agent Update | `docs.corti.ai/agentic/agents/update` | TODO |
| 5 | Agent Delete | `docs.corti.ai/agentic/agents/delete` | TODO |
| 6 | Agent Card | `docs.corti.ai/agentic/agents/card` | TODO |
| 7 | Send Message | `docs.corti.ai/agentic/agents/send-message` | TODO |
| 8 | Task | `docs.corti.ai/agentic/tasks` | TODO |
| 9 | Context | `docs.corti.ai/agentic/context` | TODO |
| 10 | Context Delete | `docs.corti.ai/agentic/context/delete` | TODO |
| 11 | Expert Registry | `docs.corti.ai/agentic/experts/overview` | TODO (seed URL provided in task prompt) |
| 12 | Prebuilt Experts | `docs.corti.ai/agentic/experts/prebuilt` | TODO |
| 13 | Bring Your Own Expert | `docs.corti.ai/agentic/experts/custom` | TODO |
| 14 | MCP Server | `docs.corti.ai/agentic/mcp/server` | TODO |
| 15 | MCP Authentication | `docs.corti.ai/agentic/mcp/auth` | TODO |
| 16 | Orchestrator | `docs.corti.ai/agentic/orchestrator` | TODO |
| 17 | Context and Memory | `docs.corti.ai/agentic/context/memory` | TODO |
| 18 | A2A | `docs.corti.ai/agentic/a2a` | TODO |
| 19 | SDK and Integrations | `docs.corti.ai/agentic/sdk` | TODO |
| 20 | Quickstart | `docs.corti.ai/agentic/quickstart` | TODO |
| 21 | Authentication | `docs.corti.ai/agentic/auth` | TODO |
| 22 | Project / Tenant / Client Credentials | `docs.corti.ai/agentic/projects` | TODO |

## 14. Currently Inaccessible Official Evidence

- Corti Console (console.corti.app) — only with authorized account; Pre-A0 will use public docs as primary, mark console-only behaviors `NOT_VERIFIED` per spec §4.3.
- Corti reference app keys — not available; will not be fabricated.
- Corti SDK runtime introspection — only via public SDK type definitions on npm.

If Console walkthrough is granted later in the session, the items marked `NOT_VERIFIED` will be promoted with explicit access-date stamp.

## 15. Historical Audit Claims to Reverify

From Gate 4 / Gate 6 / Gate 14 (must not inherit without code-level proof):

| ID | Claim | Verification Plan |
|----|-------|-------------------|
| HC-1 | Three parallel runtimes (`icoder_runtime`, `coding_runtime`, `agent_runtime`) | Pre-A0 Gate 3: import graph + run-count per runtime |
| HC-2 | Multiple Expert hierarchies (A / B / C + CDI pseudo-experts) | Pre-A0 Gate 3: per-hierarchy file listing + Runtime-call graph |
| HC-3 | Legacy `app/tools/` layer is MCP-disconnected | Pre-A0 Gate 3: grep for `from app.tools` imports in MCP / runtime / orchestrator |
| HC-4 | "13 metadata-only Agents" claim | Pre-A0 Gate 2: enumerate every agent in `official_agents/` + `agents_hub` API and decide status per-directory |
| HC-5 | A2A Tasks not fully implemented (stub) | Pre-A0 Gate 3: confirm `routes_task_stub.py` returns 501 |
| HC-6 | Agent Hub display vs Runtime reality mismatch | Pre-A0 Gate 6: cross-reference `icoder_agents_hub.py` entries against runtime calls |
| HC-7 | Corti parity = 11/32 (34%) | Pre-A0 Gate 7: rebuild V2 matrix with foundation dimensions |
| HC-8 | "Not hospital pilot ready" final verdict | **Not in scope** for Pre-A0 — Gate 14 verdict stands; Pre-A0 only reconciles foundation gaps |

## 16. Reports Expected to be Updated

**New deliverables (per spec §16):**

| File | Purpose |
|------|---------|
| `26_CORTI_DEVELOPER_FOUNDATION_GAP_RECONCILIATION.md` | Master Pre-A0 report |
| `26A_CORTI_OFFICIAL_EVIDENCE_CATALOG.md` | Corti doc evidence catalog |
| `26B_ICODER_AGENT_EXPERT_TOOL_RUNTIME_INVENTORY.md` | Full inventory |
| `26C_FOUNDATION_CAPABILITY_DECISION_MATRIX.md` | Per-capability decision |
| `26D_PARITY_MATRIX_V2_DELTA.md` | V1 → V2 delta |
| `PRE_A0_FINAL_DECISION.md` | Final verdict |

**Updates to existing (addendum only, original preserved):**

| File | Update Type |
|------|-------------|
| `19_CORTI_ICODER_PARITY_MATRIX.md` | Addendum linking to V2 |
| `21_ARCHITECTURE_DEBT_AND_DUPLICATION_LEDGER.md` | Addendum |
| `23_REMEDIATION_BACKLOG.md` | Addendum |
| `24_RECOMMENDED_ROADMAP.md` | Addendum |
| `evidence_manifest.json` | Append `pre_a0` section |

Note: `19_`, `21_`, `23_`, `24_` referenced by spec §16 do not yet exist as standalone files — their content currently lives inside the GATE reports. Pre-A0 will either create them as new files consolidating existing content, or insert addenda within the existing gate reports. Decision deferred to Pre-A0 Gate 8.

## 17. Actual Execution Order

```
Pre-A0 Gate 0 (this report)                                  [IN PROGRESS → COMPLETE]
  ↓
Pre-A0 Gate 1 — Corti Official Evidence Catalog              [NEXT]
  ↓
Pre-A0 Gate 2 — iCoDer Agent/Expert/Tool/Runtime Inventory
  ↓
Pre-A0 Gate 3 — Historical Claims Reverification
  ↓
Pre-A0 Gate 4 — Prebuilt Expert Business Relevance
  ↓
Pre-A0 Gate 5 — China Medical Scenario Mapping
  ↓
Pre-A0 Gate 6 — Agent Hub Convergence Review
  ↓
Pre-A0 Gate 7 — Parity Matrix V2 + Delta
  ↓
Pre-A0 Gate 8 — Issue Ledger Dedup + V2 Roadmap
  ↓
Pre-A0 Gate 9 — Canonical Architecture + Decision Matrix
  ↓
Pre-A0 Final Decision + Evidence Manifest Refresh
  ↓
Checkpoint A — Official Corti Evidence
Checkpoint B — Complete iCoDer Inventory
Checkpoint C — Correct Classification
Checkpoint D — No Feature Expansion
Checkpoint E — Ready for Phase A0
  ↓
PASS_PRE_A0_CORTI_FOUNDATION_RECONCILIATION_COMPLETE
READY_FOR_PHASE_A0_AUDIT_CLOSURE
```

## 18. Current Stage Verdict

```
PRE_A0_GATE_0_BASELINE_CAPTURED
NO_BASELINE_DRIFT
WORKING_TREE_UNCOMMITTED_PHASE_7_IN_FLIGHT (85 entries, pre-existing)
CORTI_EVIDENCE_COLLECTION_NOT_YET_STARTED
HISTORICAL_CLAIMS_PENDING_REVERIFICATION
```

Forbidden verdicts not claimed: `CORTI_FULL_PARITY`, `CORTI_AGENT_PARITY_COMPLETE`, `CORTI_EXPERT_PARITY_COMPLETE`, `FOUNDATION_IMPLEMENTED`, `PRODUCTION_READY`, `HOSPITAL_DEPLOYMENT_READY`, `PARTNER_PRODUCTION_READY`.

---

## Constraints Acknowledged (for the record)

- No new Agent / Expert / Tool / Runtime / Prompt edits.
- No Agent Hub card additions, removals, or content edits.
- No Registry refactor.
- No deletion of legacy code.
- No CDI prompt tuning.
- No Medical Coding model change.
- No bump of P0 count without meeting spec §13.2 strict criteria.
- No claim that anything is "already implemented" without code-level proof.
- No inheritance of historical verdicts without reverification.
- No third-party article as primary evidence.
- No fabrication of Corti Console results.

The only allowed code edits are (i) minimal tooling fixes that unblock evidence collection, (ii) emergency credential-leak止血, each as isolated commits with before/after evidence.

End of Pre-A0 Gate 0. Proceeding to Pre-A0 Gate 1 — Corti Official Evidence Catalog.
