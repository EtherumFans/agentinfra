# 01 — Audit Scope and Method

**Audit start:** 2026-07-15
**Auditor:** Independent audit pass driven by `iCoDer Comprehensive Product Audit` prompt (42-page PDF).
**Trusted commit baseline:** `c147d01` (`feat(track-h): Tier 2 Corti controlled probes — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells`)
**Branch:** `master` (tracks `remotes/origin/master`)
**Total repo commits at baseline:** 278

## 1. Audit Purpose

The audit is **not** a feature-development pass. It answers:

1. What does iCoDer actually deliver today?
2. What capabilities exist only in reports, pages, API surfaces, enums or tests, but have **no real closed loop**?
3. Does the product truly fit the declared strategic positioning (Corti-like AI Studio + China healthcare revenue-compliance vertical)?
4. How far is the Corti parity actually mature?
5. What is the real maturity of Medical Coding, CDI, DRG/DIP respectively?
6. Do A2A, Runtime, AI Studio, Embedded, SDK, Trace, Usage form a **single unified spine** — or are they fragmented?
7. What are the most severe product / architecture / security / quality / delivery risks today?
8. What should the next phase continue, stop, merge, delete?
9. How far is iCoDer from real partner integration, hospital pilot, commercialization?

## 2. Hard Audit Rules

These come directly from the audit PDF (§三) and **bind every gate**:

### 2.1 Code-fact priority

Evidence credibility, highest first:

1. Live run evidence
2. Repeatable browser E2E
3. Repeatable integration test
4. Unit test
5. Production code
6. Configuration / data
7. Reports
8. README
9. Comments
10. Task prompt

A report cannot be its own proof. A test whose name contains `real` / `e2e` / `integration` is **not** automatically live — the audit must open it and check for Mock, Monkeypatched provider, hard-coded output, skipped auth, skipped DB, skipped A2A, workspace-source masquerading as installed package, static Usage data, fabricated Trace.

### 2.2 No production-code changes during audit

**Allowed**

- New audit scripts
- New read-only analysis tools
- New Playwright audit tests
- New evidence collection scripts
- Minimal environment fixes blocking audit execution
- New reports and the Evidence Manifest

**Forbidden**

- Refactoring while auditing
- Rewriting systems because a problem was found
- Tweaking business logic so a test passes
- Counting "planned fix" as "done"
- Editing historical reports to change their verdict
- Deleting failure evidence
- Loosening test thresholds
- Rewriting `Blocked` items as `Deferred` and then marking `PASS`

If a minimal fix is unavoidable, the audit must log: original problem, file modified, reason, before-evidence, after-evidence, independence impact.

### 2.3 Maturity ladder — must tag every capability

`ABSENT` · `DOCUMENTED_ONLY` · `UI_ONLY` · `STUB` · `MOCK_ONLY` · `PARTIAL_IMPLEMENTATION` · `CODE_COMPLETE` · `UNIT_VERIFIED` · `INTEGRATION_VERIFIED` · `BROWSER_VERIFIED` · `EXTERNAL_CONSUMER_VERIFIED` · `SECURITY_VERIFIED` · `PARTNER_STAGING_VERIFIED` · `PRODUCTION_OBSERVED` · `DEPRECATED` · `DUPLICATED` · `BLOCKED`

`CODE_COMPLETE` ≠ `BROWSER_VERIFIED` ≠ `PARTNER_STAGING_VERIFIED` ≠ `PRODUCTION_READY`.

### 2.4 No CDI prompt tuning this round

Per PDF §一.4 and §十五, the audit is bound by the standing decision: **CDI prompt tuning is paused**. The audit may evaluate CDI productization, workflow, compliance boundary and integration maturity, but must **not** start new CDI prompt tuning iterations.

### 2.5 No model training this round

Per PDF §二.6 and §十五, the audit must distinguish the production Runtime model (actually invoked) from training-experiment assets (B0 / V18 / V24-v2 / LoRA / Adapter / frozen / research-only / shadow / offline-only). "Training experiment passes" must not be described as "product capability live".

## 3. Audit Gates (executed in order)

| Gate | Focus | Track coverage |
|------|-------|----------------|
| 0 | Git, workspace, evidence baseline | A1 (partial) |
| 1 | Repository structure + startup reproduction | A1, A2, A3 |
| 2 | Product surface & route inventory | B1, B3 |
| 3 | Full browser walkthrough | B2 |
| 4 | Agent capability audit | D1–D5 |
| 5 | Medical Coding / CDI / DRG-DIP deep audit | E, F, G |
| 6 | A2A, Runtime, Expert, Tool architecture | H1, H2, H3 |
| 7 | Run, Trace, Event, Usage | I1–I6 |
| 8 | Embedded, SDK, API Client, Partner App | J1–J5 |
| 9 | Auth, Security, PHI, Multi-tenant | K1–K6 |
| 10 | Model, data, evaluation assets | (E4 extended) |
| 11 | Test, performance, deployment, docs | L, M, N |
| 12 | Corti benchmark + strategic fit | Track C + §五 |
| 13 | Commercial + hospital pilot readiness | O1–O5 |
| 14 | Issue grading, roadmap, final verdict | §九 – §十三 |

## 4. Report Deliverables (27)

```
00_EXECUTIVE_SUMMARY.md
01_AUDIT_SCOPE_AND_METHOD.md           ← this file
02_GIT_REPOSITORY_BASELINE.md          ← Gate 0 output (alongside this file)
03_PRODUCT_SURFACE_INVENTORY.md
04_INFORMATION_ARCHITECTURE_AND_UX_AUDIT.md
05_STRATEGIC_POSITIONING_AUDIT.md
06_AGENT_CAPABILITY_INVENTORY.md
07_MEDICAL_CODING_AUDIT.md
08_CDI_AUDIT.md
09_DRG_DIP_AUDIT.md
10_A2A_AND_RUNTIME_ARCHITECTURE_AUDIT.md
11_EXPERT_TOOL_AND_ORCHESTRATION_AUDIT.md
12_RUN_TRACE_EVENT_USAGE_AUDIT.md
13_EMBEDDED_SDK_AND_PARTNER_INTEGRATION_AUDIT.md
14_AUTH_SECURITY_AND_PHI_AUDIT.md
15_MODEL_DATA_AND_EVALUATION_AUDIT.md
16_TEST_AND_QUALITY_AUDIT.md
17_PERFORMANCE_RELIABILITY_AND_OPERATIONS_AUDIT.md
18_DOCUMENTATION_AND_DEVELOPER_EXPERIENCE_AUDIT.md
19_CORTI_ICODER_PARITY_MATRIX.md
20_COMMERCIAL_AND_DELIVERY_READINESS.md
21_ARCHITECTURE_DEBT_AND_DUPLICATION_LEDGER.md
22_PRODUCT_GAPS_AND_DEAD_SURFACES.md
23_REMEDIATION_BACKLOG.md
24_RECOMMENDED_ROADMAP.md
25_FINAL_DECISION.md
evidence_manifest.json
```

## 5. Evidence directory layout

```
evidence/
├── git/            ← HEAD, workspace status, last-50 commits
├── commands/       ← captured shell-command outputs used as proof
├── test-results/   ← pytest / vitest / playwright raw outputs
├── browser/        ← per-page snapshots (markdown accessibility tree)
├── screenshots/    ← per-page screenshots
├── playwright-traces/
├── sanitized-har/
├── console/        ← browser console logs
├── network/        ← request/response annotations
├── storage/        ← localStorage / sessionStorage / cookie dumps
├── security/       ← negative-test outputs
├── packages/       ← build / external-consumer install proof
├── external-consumer/
├── architecture/   ← module-maps, dep-graphs
└── hashes/         ← file hashes for replay
```

## 6. Mandatory real-browser paths (§六)

These paths must be exercised in real Chrome via Playwright MCP:

1. **Console product path** — Login → Dashboard → Agent Hub → Agent Detail → Agent Settings → Agent Code → Experts → Tools → Embedded Assistant → Runs → Trace → Usage → API Clients.
2. **Medical Coding** — Set Patient Context → Submit record → Run → Inspect evidence → Inspect coding → Human Review boundary → RunHistory → Trace → Usage.
3. **CDI** — Set Patient Context → Run CDI → Documentation Gap → Provider Query Draft → Human Review → Verify **no auto-send** → Verify **no chart write-back** → RunHistory → Trace. (No prompt tuning this round.)
4. **DRG/DIP** — Load synthetic front-page data → Run → Group result → Risk → Coding impact → Trace → Usage.
5. **Embedded / Partner App** — External package install → Auth → Configure Session → Patient A → Run → Clear Context → Patient B → Run → Restart → Trace → Usage → Error Center.
6. **Security negative paths** — Expired token / Disabled API Client / Missing scope / Wrong origin / Cross-org trace / Reused idempotency-key + different payload / Concurrent dup / Expired trace token / Forged postMessage / Wrong nonce / Patient switch mid-run / Client abort / Backend timeout / Provider failure.

## 7. Problem severity rubric (§九)

- **P0 — Blocking** — PHI / Secret leak, cross-org access, auth bypass, dual Runtime main line, idempotency double-billing, core agent cannot actually run, data chain, severe report–code mismatch, clean-env boot impossible, external package unusable.
- **P1 — Critical Product Gap** — Core workflow broken, API Client incomplete, Trace inaccessible, Usage unattributable, important UI ops are stubs, three-agent integration inconsistent, Partner App unrunnable, model capability disconnected from Runtime.
- **P2 — Important** — UX inconsistency, doc gaps, weak error handling, weak tests, weak observability, version drift, tech debt.
- **P3 — Improvement** — Visual details, non-blocking Corti parity, minor perf, DevEx polish.

Every problem record must include: ID, Severity, Domain, Evidence, Root Cause, User Impact, Security Impact, Business Impact, Recommended Fix, Dependency, Verification Gate, fix-now?, delete-not-fix?

## 8. Final verdict template (§十二)

Twelve verdicts, each on its own ladder:

`PRODUCT_STRATEGY_VERDICT` · `CORE_AGENT_VERDICT` · `A2A_RUNTIME_VERDICT` · `MEDICAL_CODING_VERDICT` · `CDI_VERDICT` · `DRG_DIP_VERDICT` · `EMBEDDED_SDK_VERDICT` · `PARTNER_INTEGRATION_VERDICT` · `SECURITY_VERDICT` · `MODEL_QUALITY_VERDICT` · `HOSPITAL_PILOT_VERDICT` · `OVERALL_VERDICT`

Allowed overall verdicts:

- `AUDIT_COMPLETE_READY_FOR_FOCUSED_REMEDIATION`
- `AUDIT_COMPLETE_READY_FOR_PARTNER_STAGING_VALIDATION`
- `PARTIAL_BLOCKED_BY_CRITICAL_SECURITY_GAPS`
- `PARTIAL_BLOCKED_BY_RUNTIME_FRAGMENTATION`
- `PARTIAL_BLOCKED_BY_CORE_AGENT_INTEGRATION_GAPS`
- `PARTIAL_BLOCKED_BY_UNVERIFIED_PRODUCT_CLAIMS`
- `PARTIAL_BLOCKED_BY_NON_REPRODUCIBLE_DELIVERY`

`PRODUCTION_READY`, `HOSPITAL_DEPLOYMENT_READY`, `PARTNER_PRODUCTION_READY`, `CORTI_FULL_PARITY`, `PUBLIC_NPM_PUBLISHED`, `SECURITY_CERTIFIED` are **forbidden** unless backed by external evidence — not self-attestation.

## 9. Audit independence

This audit is conducted against `c147d01` plus the uncommitted workspace state at the moment of audit start. Historical reports (`reports/phase4h/`, `reports/phase5_*`, `reports/phase6/`, `reports/phase7/`, `reports/track_h/`) are treated as **claims to re-verify**, not as proof.
