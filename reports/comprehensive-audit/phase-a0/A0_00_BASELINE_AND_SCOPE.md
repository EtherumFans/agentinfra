# A0 Gate 0 — Baseline and Scope Re-capture

> Phase A0 (Audit Closure, Canonical Truth Baseline and Remediation Replanning) starts here.
> This gate SUPERSEDES the Pre-A0 deliverables (PRE_A0_GATE0_BASELINE.md, 26A–26I, PRE_A0_FINAL_DECISION.md).
> Pre-A0 produced a PASS verdict that cannot stand because of internal contradictions documented in §13 below.
> Phase A0 is a strictly read-only re-run that produces a machine-verifiable canonical baseline.

Spec reference: §23 (A0 Gate 0 first-round items), §3–§22 (hard constraints, checkpoints, verdicts).

---

## §1. Current Git HEAD

```
c147d015455017bc1d8420cbdbd813b3b8ec23ce
```

Short: `c147d01`
Subject: `feat(track-h): Tier 2 Corti controlled probes — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells`

This is the same baseline as Pre-A0. **No baseline drift occurred during Pre-A0.**

## §2. Current Branch

```
master
```

## §3. Current Remote

```
origin  https://github.com/EtherumFans/agentinfra.git (fetch)
origin  https://github.com/EtherumFans/agentinfra.git (push)
```

## §4. Current Workspace State

96 entries in `git status --short`. Categorized:

| Category | Count | Notes |
|----------|------:|-------|
| Pre-existing Phase 5/6/7 in-flight work (modified `backend/app/api/*.py`, `packages/icoder-*`, `frontend/src/*`) | 31 | Carried over from Phase 5/6/7 closure; NOT introduced by Pre-A0 |
| Pre-existing Phase 7 alembic migrations 012-015 (untracked) | 4 | Phase 7 Gate 3/4/5/13A |
| Pre-existing Phase 7 backend code (untracked) | 7 | idempotency_service.py, preview_ticket.py, run_lifecycle.py, trace_token.py, partner_cors.py, examples.py, preview_sessions.py, runs.py |
| Pre-existing Phase 7 tests (untracked) | 9 | test_phase7_gate* files |
| Pre-existing Phase 6/7 reports (untracked) | 2 dirs | `reports/phase6/`, `reports/phase7/` |
| Pre-A0 reports (untracked, this audit's predecessor) | 1 dir | `reports/comprehensive-audit/` (includes 01/02/GATE1-14 + 26A-26I + PRE_A0_* + evidence/) |
| Pre-A0 screenshots (untracked) | ~17 PNG | `audit-gate3-*.png`, `corti_console_*.png`, `corti_embedded_*.png` |
| Pre-A0 external consumer dir (untracked) | 1 | `phase7-external-consumer/` |
| Pre-A0 `.audit-chrome-profile/` (untracked) | 1 | Chrome profile used for Corti Console walkthrough |
| Pre-A0 `docs/audit/` + `docs/corti_parity/phase7_gate13a/` (untracked) | 2 | Doc artifacts |
| Other (examples/, packages/icoder-web/DEPRECATED.md, etc.) | ~20 | Mixed Phase 6/7 leftover |

**Workspace is dirty but the dirt is pre-existing.** Pre-A0 added only documentation + evidence; no business code was modified by Pre-A0 or by Phase A0.

## §5. Historical Audit Baseline Commit

The original 14-gate audit (GATE1–GATE14 + 01/02) was performed against the same HEAD `c147d01`. No intermediate commit was made. All reports under `reports/comprehensive-audit/` were left untracked at the time the audit verdicts were issued.

## §6. Current Review Commit

Phase A0 review commit: **none yet**. This is Gate 0 of Phase A0. The review is captured in this document and the subsequent A0_01–A0_09.

## §7. Baseline Drift Check

| Check | Expected | Observed | Drift? |
|-------|----------|----------|--------|
| HEAD at start of Pre-A0 | `c147d01` | `c147d01` | No |
| HEAD at end of Pre-A0 | `c147d01` | `c147d01` | No |
| HEAD at start of Phase A0 | `c147d01` | `c147d01` | No |
| Branch | `master` | `master` | No |
| Workspace dirty? | Yes (pre-existing) | Yes (pre-existing) | No new drift |
| Pre-A0 code changes | 0 | 0 | No drift |
| Phase A0 code changes (planned) | 0 | 0 (so far) | No drift |

**Verdict: NO BASELINE DRIFT.**

## §8. Gate 0–14 Reports — Complete List

All under `reports/comprehensive-audit/`:

| File | Lines | Gate verdict (extracted) |
|------|------:|----|
| `01_AUDIT_SCOPE_AND_METHOD.md` | 195 | (Methodology, no verdict) |
| `02_GIT_REPOSITORY_BASELINE.md` | 407 | (Baseline capture, no verdict) |
| `GATE1_REPOSITORY_STRUCTURE_AND_STARTUP.md` | 278 | (Repository structure) |
| `GATE2_PRODUCT_SURFACE_AND_ROUTE_INVENTORY.md` | 228 | (Surface inventory) |
| `GATE3_BROWSER_WALKTHROUGH.md` | 123 | (Browser walkthrough) |
| `GATE4_AGENT_CAPABILITY_AUDIT.md` | 305 | (Agent capability) |
| `GATE5_MEDICAL_CODING_CDI_DRG_DIP_DEEP_AUDIT.md` | 301 | (Clinical depth) |
| `GATE6_A2A_RUNTIME_EXPERT_TOOL_ARCHITECTURE.md` | 279 | (Runtime architecture) |
| `GATE7_RUN_TRACE_EVENT_USAGE_AUDIT.md` | 240 | (Observability) |
| `GATE8_EMBEDDED_SDK_API_CLIENT_PARTNER_APP.md` | 300 | (Embedded surface) |
| `GATE9_AUTH_SECURITY_PHI_MULTI_TENANT.md` | 395 | (Security/PHI/multi-tenant) |
| `GATE10_MODEL_DATA_EVALUATION_ASSETS.md` | 350 | (Model/data assets) |
| `GATE11_TEST_PERFORMANCE_DEPLOYMENT_DOCS.md` | 390 | (Test/deploy/docs) |
| `GATE12_CORTI_BENCHMARK_STRATEGIC_FIT.md` | 308 | (Corti benchmark/strategic fit) |
| `GATE13_COMMERCIAL_HOSPITAL_PILOT_READINESS.md` | 370 | (Commercial readiness) |
| `GATE14_ISSUE_GRADING_ROADMAP_FINAL_VERDICT.md` | 388 | (Issue grading + roadmap + 12 verdicts) |

**16 reports.** Gate 14's verdict is `NOT_HOSPITAL_PILOT_READY` with 16 P0 + ~23 P1 + ~24 P2 + ~10 P3 issues.

## §9. Phase 6 / Phase 7 / Gate 13A Reports — Complete List

### Phase 6 (9 reports under `reports/phase6/`)

| File |
|------|
| `PHASE6_FINAL_REPORT.md` |
| `PHASE6_GATE0_EMBEDDED_AND_SDK_BASELINE.md` |
| `PHASE6_GATE1_EMBEDDED_CONTRACT.md` |
| `PHASE6_GATE2_PATIENT_ENCOUNTER_CONTEXT_SAFETY.md` |
| `PHASE6_GATE3_UNIFIED_EMBEDDED_EVENT_CONTRACT.md` |
| `PHASE6_GATE4_SDK_API_CLIENT_PRODUCTIZATION.md` |
| `PHASE6_GATE5_RUNHISTORY_TRACE_COST_INTEGRATION.md` |
| `PHASE6_GATE7_THREE_EMBEDDED_DEMOS.md` |
| `PHASE6_GATE8_API_CLIENT_USAGE_PRODUCTIZATION.md` |

### Phase 7 (15 reports + screenshots under `reports/phase7/`)

| File |
|------|
| `PHASE7_FINAL_REPORT.md` |
| `PHASE7_GATE0_PHASE6_RUNTIME_BASELINE.md` |
| `PHASE7_GATE1_DEMO_STATIC_MOUNT.md` |
| `PHASE7_GATE2_SDK_TGZ_EXTERNAL_INSTALL.md` |
| `PHASE7_GATE3_SERVER_SIDE_IDEMPOTENCY.md` |
| `PHASE7_GATE4_RUN_CANCEL_TIMEOUT.md` |
| `PHASE7_GATE5_API_CLIENT_ATTRIBUTION.md` |
| `PHASE7_GATE6_ALLOWED_ORIGINS_CORS.md` |
| `PHASE7_GATE7_TRACE_URL_PARTNER_ACCESS.md` |
| `PHASE7_GATE8_USAGE_API_CLIENT_METERING.md` |
| `PHASE7_GATE9_SSE_RUN_STATE_EVENTS.md` |
| `PHASE7_GATE10_THREE_DEMOS_BROWSER_E2E.md` |
| `PHASE7_GATE11_PATIENT_CONTEXT_ISOLATION.md` |
| `PHASE7_GATE12_PARTNER_REFERENCE_APP.md` |
| `PHASE7_GATE13_EMBEDDED_ASSISTANT_PARITY.md` |
| `PHASE7_CORTI_EMBEDDED_PARITY_WALKTHROUGH.md` |

### Phase 7 Gate 13A (under `reports/phase7/gate13a/`)

| File |
|------|
| `PHASE7_GATE13A_BASELINE.md` |
| `PHASE7_GATE13A_FINAL_REPORT.md` |
| `PHASE7_GATE13A_THREAT_MODEL.md` |

Plus subdirs: `console-logs/`, `network-audit/`, `playwright-traces/`, `sanitized-har/`, `screenshots/`, `storage-audit/`, `test-results/`.

## §10. Pre-A0 Reports — Complete List (to be superseded)

All under `reports/comprehensive-audit/`:

| File | Lines | Status |
|------|------:|--------|
| `PRE_A0_GATE0_BASELINE.md` | 274 | SUPERSEDED by this document |
| `26A_CORTI_OFFICIAL_EVIDENCE_CATALOG.md` | 178 | SUPERSEDED by A0_03 |
| `26B_ICODER_AGENT_EXPERT_TOOL_RUNTIME_INVENTORY.md` | 359 | SUPERSEDED by A0_02 + A0_07 |
| `26C_GATE3_HISTORICAL_CLAIMS_REVERIFICATION.md` | 301 | Merged into A0_02 |
| `26D_GATE4_PREBUILT_EXPERT_BUSINESS_RELEVANCE.md` | 113 | Merged into A0_03 |
| `26E_GATE5_CHINA_MEDICAL_SCENARIO_MAPPING.md` | 160 | SUPERSEDED by A0_06 |
| `26F_GATE6_AGENT_HUB_CONVERGENCE_REVIEW.md` | 161 | Merged into A0_03 + A0_04 |
| `26G_GATE7_PARITY_MATRIX_V2_DELTA.md` | 222 | SUPERSEDED by A0_04 (math invalidated) |
| `26H_GATE8_ISSUE_LEDGER_DEDUP.md` | 195 | SUPERSEDED by A0_05 (incomplete) |
| `26I_GATE9_CANONICAL_ARCHITECTURE_DECISION_MATRIX.md` | 173 | SUPERSEDED by A0_07 (ontology errors) |
| `PRE_A0_FINAL_DECISION.md` | 185 | SUPERSEDED by A0_09 |

**11 Pre-A0 deliverables.** All are marked SUPERSEDED at the top of their Phase A0 replacement.

## §11. Missing Reports

| Gap | Description |
|-----|-------------|
| Phase 6/7 reports never committed | `git log --all -- reports/phase6/ reports/phase7/` returns empty; reproducibility from `origin/master` is broken. (Pre-A0 G0-001 noted this; Phase A0 does NOT fix it because Phase A0 is read-only.) |
| `reports/comprehensive-audit/` itself never committed | Same problem — the 14-gate audit lives only in working copy. |
| Phase 7 Gate 13A `screenshots/`, `console-logs/`, `playwright-traces/`, `sanitized-har/` | Exist as untracked dirs; not in any commit. |

Phase A0 will add `reports/comprehensive-audit/phase-a0/` to this same untracked state. **Phase A0 explicitly does NOT commit.** Commit is a Phase A1 action.

## §12. Unsubmitted Reports

All reports under `reports/comprehensive-audit/`, `reports/phase6/`, `reports/phase7/`, and the forthcoming `reports/comprehensive-audit/phase-a0/` are uncommitted and unpushed. This is consistent with the read-only constraint.

## §13. Current Evidence Manifest — All Contradictions

The current `reports/comprehensive-audit/evidence_manifest.json` (192 lines, last touched by Pre-A0) has these contradictions:

| # | Field at top | Field at bottom | Contradiction |
|---|--------------|-----------------|---------------|
| C-1 | `gates_completed: ["gate0"]` | `verdicts_so_far.pre_a0_final: "PASS_PRE_A0_..."` | Top says only gate0 done; bottom claims Pre-A0 closed |
| C-2 | `gates_pending: ["gate1" ... "gate14"]` | `verdicts_so_far.gate11/gate13/gate14` populated | Top says all 14 pending; bottom has 3 verdicts |
| C-3 | `gates_in_progress: []` | `verdicts_so_far.pre_a0_gate1..9` populated | Top says nothing in progress; bottom has 9 pre-A0 gates |
| C-4 | `evidence_index.commands: []` | `findings.P1[G0-001].evidence` quotes `git status` output | Commands ran but were never logged |
| C-5 | `evidence_index.test-results: []` | (Phase 7 has 88+ tests passing per memory) | Test runs not logged |
| C-6 | `evidence_index.browser: []`, `screenshots: []`, `playwright-traces: []`, `sanitized-har: []` | Phase 7 Gate 13A has `console-logs/`, `playwright-traces/`, `sanitized-har/`, `screenshots/` dirs; Pre-A0 has 10 Corti PNGs | Browser evidence exists but not indexed |
| C-7 | `evidence_index.console: []` | Pre-A0 walked 10 Corti Console pages | Console evidence not indexed |
| C-8 | `evidence_index.hashes: []` | `console-walkthrough/_hashes.json` has 16 SHA-256 entries | Hashes not indexed |
| C-9 | `forbidden_verdicts` list does NOT include `HOSPITAL_PILOT_READY` | Gate 14 verdict is `NOT_HOSPITAL_PILOT_READY` (which is fine) BUT Pre-A0 Final claimed `PASS_PRE_A0_CORTI_FOUNDATION_RECONCILIATION_COMPLETE` is one of 5 allowed verdicts per spec §13.3 — Phase A0 spec §15 expands forbidden list to include `HOSPITAL_PILOT_READY` and 8 others | Forbidden list incomplete |

**9 contradictions.** All must be resolved in A0 Gate 1.

## §14. `pending write` and Placeholder Hash List

From `26A_CORTI_OFFICIAL_EVIDENCE_CATALOG.md`:

| Line | Placeholder | Type |
|------|-------------|------|
| 29–35 | `(per-file)` × 7 (D-01 .. D-07 SHA-256 column) | Hash placeholder |
| 99 | (no placeholder, but uses "TBD pricing" as V1 status — OK) | — |
| 111–117 | `pending write` × 7 (`official-docs/experts_overview.md` through `sdks_integrations.md`) | File-not-yet-written marker |

From `evidence/corti-foundation/official-docs/_access_metadata.json`:
- Line 6: `"doc_index_sha256": "TODO"` — placeholder hash

From `evidence_manifest.json`:
- 9 empty arrays listed in §13 above — implicit placeholders.

**Total: 7 + 7 + 1 + 9 = 24 placeholders.** All must be either filled with real values or marked `NOT_VERIFIED` in A0 Gate 1.

## §15. Current Sensitive Evidence List

Files containing credentials, PII, or identifiers that must NOT be in any public manifest:

| File | Sensitive content |
|------|-------------------|
| `reports/comprehensive-audit/evidence/corti-foundation/console-walkthrough/00_console_access_metadata.md` | Email `songluhua@gmail.com`; username slug `songluhua-7ff972`; Project ID `4c4193c7-c6bb-4a71-a275-0ed6c53172d0`; credits balance |
| `reports/comprehensive-audit/evidence/corti-foundation/official-docs/_access_metadata.json` | Access metadata only — currently OK but no PII |
| `backend/.env` (existing committed file per Gate 9 K6.1) | `SECRET_KEY=change-me-in-production`, `DEBUG=true` — pre-existing Gate 9 finding G9-001 |
| `backend/.env.cloud.example` (if exists) | Should be sanitized; verify in Gate 1 |
| `.audit-chrome-profile/` (untracked) | Chrome profile cookies, session tokens — MUST NOT be committed |
| `reports/phase7/gate13a/console-logs/`, `sanitized-har/`, `playwright-traces/` | Already sanitized per Phase 7 Gate 13A; verify no leaks in Gate 1 |
| `corti_console_*.png` (17 PNGs) | Visual screenshots; verify no email/PII in frames in Gate 1 |

**Phase A0 action:** produce `evidence_manifest.public.json` (sanitized) and `evidence_manifest.v2.json` (restricted, with PII flagged).

## §16. Current Parity Matrix — Count and Math Problems

Pre-A0's `26G_GATE7_PARITY_MATRIX_V2_DELTA.md` reported:
- 51 dimensions total
- 30/51 = 59% "favorable to iCoDer" (PARITY + PARTIAL_PARITY + ICODER_ADVANTAGE lumped)
- 24/31 = 77% "CN-scoped favorable"
- Claimed V1 → V2 swing of +25 percentage points

**Math and methodology problems:**

| # | Problem | Detail |
|---|---------|--------|
| M-1 | Invalid composite bucket | "Favorable" lumps PARITY + PARTIAL_PARITY + ICODER_ADVANTAGE. PARTIAL_PARITY means "partially missing" — counting it as favorable obscures real gaps. Spec §13.2 requires mutually exclusive statuses; "favorable" is not a defined status. |
| M-2 | Denominator instability | 32 → 51 dimensions. Adding dimensions then recomputing % is not a delta, it is a redefinition. A real delta holds the denominator fixed. |
| M-3 | Agent name mirror rate ≠ product parity | "18/20 agents mirrored" counts identical display names. It does NOT verify that the iCoDer agent has the same runtime behavior, expert routing, MCP tools, or output schema. |
| M-4 | Asset existence ≠ workflow maturity | Counting `pii_redaction.py` exists as ICODER_ADVANTAGE for "Edge PHI redaction" — but Gate 9 K3.2 confirms redactor is EXPORT-PATH ONLY, not live-path. The advantage claim is false at runtime. |
| M-5 | Observability contract ≠ operational observability | "iCoDer emits patient.context.cleared" counts as ICODER_ADVANTAGE. But `RUNTRACE_STORE="memory"` default means the events vanish on restart (G7-001). Emitting is not persisting. |
| M-6 | Context store ≠ RAG memory | "iCoDer has agent_runtime/context/" counted as PARTIAL_PARITY for Memory. But context is per-run state, not long-term memory. Corti's Memory expert is a different concept. |
| M-7 | Counted but not weighted | A parity matrix without severity weighting is uninterpretable. 30/51 favorable could still be all P0 gaps. |
| M-8 | Corti-ADVANTAGE dimensions under-counted | Corti real billing (E-01..E-07) counted as 7 separate CORTI_ADVANTAGE dimensions, but iCoDer DRG-DIP (C-13) counted as single ICODER_ADVANTAGE. Asymmetric granularity biases the count. |
| M-9 | Out-of-scope used to inflate favorable | DIFFERENT_BY_DESIGN items (e.g., "iCoDer is CN-only so Corti's 9 ICD-10 variants are out-of-scope") implicitly excuse gaps. Per spec §13.2, OUT_OF_SCOPE and DIFFERENT_BY_DESIGN must be reported separately and NOT reduce the unfavorable count. |
| M-10 | No machine-verifiable JSON | The 26G matrix exists only as a markdown table. There is no `parity_matrix.json` that a validator can parse. |

**All 10 problems invalidate the 59% / 77% / 90% numbers.** Phase A0 Gate 4 rebuilds this as V2.1 machine-verifiable JSON.

## §17. Current Issue Ledger — Source Coverage

Pre-A0's `26H_GATE8_ISSUE_LEDGER_DEDUP.md` claims 55 unique issues after dedup. Sources covered:

| Source gate | Issues raised | In ledger? |
|-------------|---------------|------------|
| Gate 0 (G0-001..005) | 5 | Yes (1× P1, 4× P2) |
| Gate 11 (G11-001..009) | 9 | Yes |
| Gate 13 (G13-001..010) | 10 | Yes |
| Pre-A0 Gate 2 (G2-001..011) | 11 | Yes |
| Pre-A0 Gate 3 (G3-001..007) | 7 | Yes |
| Pre-A0 Gate 4 (G4-001..004) | 4 | Yes |
| Pre-A0 Gate 5 (G5-001..007) | 7 | Yes |
| Pre-A0 Gate 6 (G6-001..006) | 6 | Yes |
| Pre-A0 Gate 7 (G7-001..006) | 6 | Yes |

**Sources NOT covered:**

| Source gate | Issues raised | In Pre-A0 ledger? |
|-------------|---------------|-------------------|
| Gate 1 (G1-*) | Repository structure | NO |
| Gate 2 (G2-* original) | Product surface | NO |
| Gate 3 (G3-* original) | Browser walkthrough | NO |
| Gate 4 (G4-* original) | Agent capability | NO |
| Gate 5 (G5-001..012) | 12 issues incl. G5-001 cost=0 + G5-004 CDI open loop | **PARTIAL** — only G5-004 carried; G5-001 (P0 cost bug) missing |
| Gate 6 (G6-* original) | Runtime architecture | NO |
| Gate 7 (G7-001..007) | 7 issues incl. G7-001 trace store dormant | **PARTIAL** — referenced but not in ledger |
| Gate 8 (G8-*) | Embedded surface | NO |
| Gate 9 (G9-001..006) | 6 P0 security issues | **NO** — entire security domain missing |
| Gate 10 (G10-001) | no-f1-baseline P0 | NO |
| Gate 12 (G12-001..002) | parity-overclaim + strategic-incoherence P0 | NO |
| Gate 14 (16 P0 + 23 P1) | Consolidated | **NO** — Pre-A0 only covered Gate 13's 10 issues, not Gate 14's 16 P0 |
| Phase 7 Gate 13A | HMAC Bootstrap Ticket risks | NO |

**Pre-A0 ledger is missing at least 16 P0 issues that Gate 14 already graded.** This is a critical coverage gap. Phase A0 Gate 5 rebuilds the ledger inheriting ALL Gate 0–14 + Gate 13A findings.

## §18. Currently Missing Gate 14 High-Risk Findings

The 16 P0 issues from `GATE14_ISSUE_GRADING_ROADMAP_FINAL_VERDICT.md` §P1.1. Cross-referenced against Pre-A0 ledger coverage:

| Gate 14 P0 ID | Title | Domain | In Pre-A0 ledger? |
|---------------|-------|--------|-------------------|
| G3-001 | `/ai-studio` 13 Corti external links | product-integrity | NO |
| G5-001 | `fast_runtime.py:307` hardcodes `cost={"amount": 0.0}` | cost-bug | NO |
| G5-004 | CDI loop open — 443 queries, 0 responses | cdi-open-loop | PARTIAL (as P1-10 dup of P0-01) |
| G7-001 | `RUNTRACE_STORE="memory"` — table empty | trace-store-dormant | NO |
| G8-001 | `@icoder/sdk@1.0.0-beta.2` + `@icoder/embedded@2.0.0` 404 on npm | npm-unpublished | NO |
| G9-001 | Committed `backend/.env` with `SECRET_KEY=change-me-in-production` + `DEBUG=true` | secrets-footgun | NO |
| G9-002 | `audit_logs` records only 5 actions | audit-coverage-broken | NO |
| G9-003 | 235/240 run_history rows have NULL `organization_id` | tenancy-broken | NO |
| G10-001 | Only F1@1=0.15 on 5-case smoke; no 201 baseline | no-f1-baseline | NO |
| G11-001 | Cloud SaaS docs-only; 6 critical features Phase 2+ | cloud-docs-only | **YES** (as P0-03) |
| G12-001 | Corti parity 11/32 = 34%, not "Corti-competitive" | parity-overclaim | NO (Pre-A0 instead claimed V2 = 59%) |
| G12-002 | 5 product framings + 13 Corti redirects | strategic-incoherence | NO |
| G13-001 | Billing theater — 0 transactions | billing-theater | **YES** (as P0-04) |
| G13-002 | Zero compliance certifications | no-certifications | **YES** (as P0-01) |
| G13-003 | Zero legal docs | no-legal-docs | **YES** (as P0-02) |
| G13-004 | Zero shippable deployment paths | no-deployment-path | **YES** (as P0-03, merged with G11-001) |

**Coverage: 4/16 P0 carried into Pre-A0 ledger.** **12/16 P0 MISSING.**

Additionally, these Phase 7 / Phase 7 Gate 13A findings are missing:

| Finding | Source |
|---------|--------|
| Embedded Preview Token — pre-13A design had URL-JWT PHI risk | Phase 7 Gate 13A threat model |
| `postMessage('*')` origin risk in embedded widget | Phase 7 Gate 13A |
| Patient A/B isolation never exercised in multi-tenant prod | Phase 7 Gate 11 |
| External package consumer supply chain | Phase 7 Gate 2 |

## §19. Current Agent / Expert / Runtime Ontology Conflicts

Pre-A0's 26B + 26I made these ontological claims that conflict with the code:

| # | Pre-A0 claim | Code reality | Conflict type |
|---|--------------|--------------|---------------|
| O-1 | "`icoder_runtime/` is a Registry Shell that raises NotImplementedError on run_agent" | `icoder_runtime/` contains: Registry, LLMGateway, DataPolicy, PII Redactor, RunHistory, AuditLog, FallbackTracker, ShadowDiffService, AgentPackageV1, CircuitBreaker, Guardrails — **Platform Core**, NOT shell | Misclassification |
| O-2 | "`official_agents/` is Hierarchy C — Packaged Agents (canonical expert hierarchy)" | `official_agents/` is the **Agent Pack Catalog** (manifest packages). It is NOT an Expert Registry nor an Expert Hierarchy. | Misclassification |
| O-3 | "4 expert hierarchies: app/agents/experts, agent_runtime/experts, official_agents, agent_runtime/cdi" | Only `agent_runtime/experts` (MedCodER stages) is a real "expert" collection in the Corti sense. `official_agents/` is Agent Packs. `app/agents/experts` is legacy. `agent_runtime/cdi` are **workflow gates** not experts. | Misclassification |
| O-4 | "30 unique agents" | The number "30" is used loosely across at least 14 distinct count dimensions (see §20). | Ambiguity |
| O-5 | "MedCodER is an agent" | MedCodER is a **5-stage pipeline inside Medical Coding Agent**. The agent is one pack; the pipeline is internal. | Misclassification |
| O-6 | "CDI internal 12 pseudo-experts" | CDI has 12 **workflow gates** (nlq_gate, eligibility gate, etc.). They are NOT Corti-style Experts. | Misclassification |
| O-7 | "3 parallel runtimes: icoder_runtime, coding_runtime, agent_runtime" | `icoder_runtime` = Platform Core (libraries); `coding_runtime` = Medical Coding domain runtime (a module, not a separate process); `agent_runtime` = Execution Plane (canonical). **1 canonical execution layer + 1 domain runtime + 1 platform core library** — NOT "3 parallel runtimes". | Misclassification |
| O-8 | "5 registries (RG-1..RG-5)" implied duplication | Multiple registries serve **bounded contexts** (RuntimeAgentRegistry for runtime, CapabilityRegistry for capability discovery, A2A SchemaRegistry for protocol schemas, etc.). They are NOT duplicates. | Misclassification |

**8 ontology conflicts.** All must be corrected in A0 Gate 2 and A0 Gate 7.

## §20. The 14 Agent Count Dimensions

The phrase "agent count" is ambiguous. Phase A0 defines 14 distinct count dimensions. Every agent count claim must specify which dimension.

| # | Dimension | Definition | Current iCoDer value |
|---|-----------|------------|---------------------|
| D-1 | Raw filesystem entries | Any directory under agent roots | ~60+ |
| D-2 | Physical directories with `agent_pack.json` | Valid Agent Pack dirs | TBD Gate 2 |
| D-3 | Valid `agent_pack.json` files | Manifest-validity passed | TBD Gate 2 |
| D-4 | Distinct `agent_id` values | Unique string keys | TBD Gate 2 |
| D-5 | Aliases / redirects | kebab↔snake duplicate ids | 3 pairs (per Pre-A0 G2-001) |
| D-6 | Semantic capabilities | After merging duplicates by capability | TBD Gate 2 |
| D-7 | Hub-visible | Returned by `/api/v1/agents/hub` | TBD Gate 2 |
| D-8 | Runtime-resolvable | Loadable by RuntimeAgentRegistry | TBD Gate 2 |
| D-9 | Specialized domain agents | Medical Coding, CDI, DRG, etc. | TBD Gate 2 |
| D-10 | Generic / utility agents | Templates, examples | TBD Gate 2 |
| D-11 | Metadata-only | No runnable backend | TBD Gate 2 |
| D-12 | Deprecated | Marked DEPRECATED.md | TBD Gate 2 |
| D-13 | Internal / not user-facing | MedCodER stages, CDI gates | TBD Gate 2 |
| D-14 | Corti-mirrored | Display name matches Corti prebuilt | TBD Gate 2 |

Pre-A0's "30 unique agents" claim corresponds to **roughly D-7 (Hub-visible)** but was used as if it were D-1, D-4, D-6, D-8. Phase A0 Gate 2 will publish all 14 values precisely.

## §21. Files Phase A0 Will Create

```
reports/comprehensive-audit/phase-a0/
├── A0_00_BASELINE_AND_SCOPE.md                  ← this file
├── A0_01_EVIDENCE_MANIFEST_CLOSURE.md
├── A0_02_CAPABILITY_ONTOLOGY_AND_COUNTS.md
├── A0_03_CORTI_EVIDENCE_REGRADING.md
├── A0_04_PARITY_MATRIX_V2_1.md
├── A0_05_CANONICAL_ISSUE_LEDGER.md
├── A0_06_PRODUCT_MATURITY_TRUTHFULNESS.md
├── A0_07_CANONICAL_ARCHITECTURE_V2.md
├── A0_08_REMEDIATION_ROADMAP_AND_PHASE_A1_ENTRY.md
├── A0_09_EXECUTIVE_SUMMARY_AND_FINAL_DECISION.md
├── evidence_manifest.v2.json                    (restricted; full)
├── evidence_manifest.public.json                 (sanitized; no PII)
├── evidence_manifest.pre_a0.snapshot.json         (snapshot of current manifest)
├── parity_matrix_v2_1.json                       (machine-verifiable)
├── issue_ledger.json                             (machine-verifiable)
├── capability_ontology.json                      (machine-verifiable)
├── architecture_v2.json                          (machine-verifiable)
├── product_maturity.json                         (machine-verifiable)
└── phase_a0_validation.json                      (machine validation output)

scripts/audit/
├── validate_phase_a0.py                          (validator)
├── capture_git_baseline.py                       (baseline snapshotter)
├── compute_evidence_hashes.py                    (SHA-256 computer)
├── sanitize_evidence_manifest.py                 (PII sanitizer)
├── parity_matrix_validator.py                    (parity checker)
└── issue_ledger_validator.py                     (ledger checker)
```

**~30 files total.** All read-only with respect to business code.

## §22. Phase A0 Actual Execution Order

```
Gate 0  (this document)            → A0_00_BASELINE_AND_SCOPE.md
Gate 1  Evidence Manifest Closure  → A0_01 + 3 manifest JSONs
Gate 2  Capability Ontology        → A0_02 + capability_ontology.json
Gate 3  Corti Evidence Re-grading  → A0_03 (applies E0-E8)
Gate 4  Parity Matrix V2.1         → A0_04 + parity_matrix_v2_1.json
Gate 5  Canonical Issue Ledger     → A0_05 + issue_ledger.json
Gate 6  Product Maturity           → A0_06 + product_maturity.json
Gate 7  Canonical Architecture V2  → A0_07 + architecture_v2.json
Gate 8  Remediation Roadmap        → A0_08
Gate 9  Executive Summary + Final  → A0_09
Validator                          → scripts/audit/validate_phase_a0.py + phase_a0_validation.json
```

Gates execute sequentially (each depends on prior). No parallelism. No pauses for confirmation per the user directive: "第一轮完成后，持续执行 A0 Gate 1–9，不要停留在计划阶段，不要要求对每个 Gate 单独确认".

## §23. Current Interim Verdict

Per spec §15, only these interim verdicts are allowed during Phase A0 in-progress state:

- `AUDIT_BASELINE_RECAPTURE_IN_PROGRESS_PRE_A0_FINDINGS_UNDER_REVIEW`
- `PARTIAL_BLOCKED_BY_*` (4 variants, only at Gate 9)
- `INVALIDATED_BY_PHASE_A0_SCOPE_EXPANSION` (only if scope violated — NOT expected)
- `PASS_PHASE_A0_AUDIT_CLOSURE_AND_READY_FOR_PHASE_A1_*` (only at Gate 9 if all 8 checkpoints pass)

**Interim verdict at Gate 0:**

```
AUDIT_BASELINE_RECAPTURE_IN_PROGRESS_PRE_A0_FINDINGS_UNDER_REVIEW
```

Justification:
- Baseline re-captured (Git HEAD, workspace, drift check) ✓
- Pre-A0 deliverables inventoried ✓
- 9 manifest contradictions documented (§13) ✓
- 24 placeholders listed (§14) ✓
- 8 ontology conflicts identified (§19) ✓
- 12/16 Gate 14 P0 missing from current ledger (§18) ✓
- Pre-A0's `PASS_PRE_A0_...` verdict is **not yet invalidated** — it remains the standing claim until Gate 9 either ratifies or supersedes it. Phase A0 treats Pre-A0 deliverables as **input evidence under review**, not as canonical truth.

## §24. Hard Constraints Honored So Far

| Constraint | Status |
|------------|--------|
| Read-only (zero business code changes) | ✅ This gate wrote to `reports/` and `scripts/audit/` only |
| No new Agent/Expert/Tool/Runtime/Prompt | ✅ None added |
| No Registry refactor | ✅ None |
| No legacy deletion | ✅ None |
| No CDI prompt tuning | ✅ None |
| No Medical Coding model change | ✅ None |
| No bump of P0 count | ✅ P0 count inheritance will happen in Gate 5 (expected: 16 from Gate 14, possibly +new from Phase A0 re-grading) |
| No inheritance of historical verdicts without reverification | ✅ All Pre-A0 claims marked under review |
| No third-party article as primary evidence | ✅ Primary = Corti docs + Console + iCoDer code |
| No fabrication of Corti Console results | ✅ Console observations in 26A will be regraded in Gate 3 |

## §25. Hard Checkpoint Status

Per spec §20 / §22, Phase A0 has 8 hard checkpoints A–H:

| Checkpoint | Title | Status at Gate 0 |
|------------|-------|------------------|
| A | Reproducible Baseline | ✅ Captured (§1–§7) |
| B | Evidence Manifest Integrity | ⏳ Pending Gate 1 |
| C | Ontology / Count Integrity | ⏳ Pending Gate 2 |
| D | Parity Integrity | ⏳ Pending Gate 4 |
| E | Canonical Issue Ledger Integrity | ⏳ Pending Gate 5 |
| F | Product Maturity Truthfulness | ⏳ Pending Gate 6 |
| G | Architecture Integrity | ⏳ Pending Gate 7 |
| H | Roadmap Actionability | ⏳ Pending Gate 8 |

**1/8 checkpoints provisionally closed (pending validator).** Gate 9 will ratify.

End of Gate 0. Proceeding to Gate 1 — Evidence Manifest Closure.
