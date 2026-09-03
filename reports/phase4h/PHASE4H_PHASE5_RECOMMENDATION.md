# Phase 4-H §19 — Phase 5 Recommendation (Gap Prioritization + Roadmap)

**Purpose:** Consolidate P0/P1/P2 gaps from §11-§14 audits + recommend Phase 5 scope. Per PDF §2.3 capability decisions: MUST_MATCH / LOCALIZE_FOR_CHINA / ICODER_ADVANTAGE / DEFER / DO_NOT_COPY.

**Theme recommendation:** **Phase 5 = Quality at Scale**

---

## 1. Gap Inventory (consolidated from §11-§14)

### P0 — Critical (AUDIT_BLOCKER_FIX before Phase 5 starts)

| ID | Title | Source | Location | Fix | Estimate |
|---|---|---|---|---|---|
| **P0-1** | BUG-12-01: Trace step duration double-count | §12 | `backend/app/api/agent_run.py:537,644` | De-duplicate trace_events emission so each step appears once with single duration. 3-step run currently shows 7 steps × 3020ms = 9060ms phantom total. | 1-2 hours |
| **P0-2** | BUG-12-02: Currency mismatch across TopBar/billing/usage | §12 | `frontend/src/components/layout/TopBar.tsx` + `/billing` + `/usage` | Unify currency. Recommend CNY ¥ (CN-focused) for all surfaces, or USD $ if matching Corti globally. Document choice in CLAUDE.md. | 1-2 hours |

**P0 total:** 2 commits, ~2-4 hours.

---

### P1 — Major (Phase 5 scope)

| ID | Title | Source | Location | Fix | Estimate |
|---|---|---|---|---|---|
| **P1-1** | GAP-12-01: `/usage` page not wired to `run_history.cost` | §12 | `backend/app/api/usage.py` | Update `usage.py` to aggregate `run_history.cost` grouped by day + API Client. Currently shows ¥0.00 despite 1+ run with non-zero cost existing in DB. | 4-6 hours |
| **P1-2** | GAP-11-01: Web Component API surface differs from Corti | §10, §11 | `packages/icoder-embedded/src/icoder-assistant.ts` | Refactor from attribute-based (`baseURL/access-token/agent-ref/theme`) to method-based (`auth({access_token, refresh_token, token_type, mode})/configureSession({defaultTemplateKey})/configure({features, locale})/show()/addEventListener('embedded-event')`). Match Corti `<corti-embedded>` API exactly. | 4-6 hours |
| **P1-3** | GAP-11-02: `@icoder/embedded` not published to npm | §10, §11 | `packages/icoder-embedded/package.json` | Publish package to npm registry. Config already exists. Requires npm login + `npm publish`. | 2-4 hours |
| **P1-4** | GAP-12-02/03: RunHistory Date filter + daily chart missing | §12 | `frontend/src/pages/RunHistoryPage.tsx` + `frontend/src/pages/UsagePage.tsx` | Add Date range picker on `/runs/history` (7d/30d/custom). Add daily cost chart on `/usage` (30-day bar chart). Corti has both. | 2-3 hours |

**P1 total:** 4 commits, ~12-19 hours.

---

### P2 — Polish (backlog, can extend into Phase 5+)

| ID | Title | Source | Fix | Estimate |
|---|---|---|---|---|
| **P2-1** | Build 4 more pre-built agents to reach 12 (Corti has 20) | §5 | Suggested: Coding Audit + Charge Compliance + Insurance Audit + Discharge Summary Quality. Each ~3-4 hours. | 12-16 hours |
| **P2-2** | Wire DRG/DIP rule engine + insurance audit KBs | §8 | Rule structures reserved in `compliance_services/`. Wire CN-DRG + DIP rule sets + insurance audit KBs. | 16-24 hours |
| **P2-3** | API Client action buttons (Regenerate secret, Delete, Copy ID) | §10 | Add 3 buttons on `/admin/clients` per-client row. | 2-3 hours |
| **P2-4** | Publish Agent Skills to `.well-known/agent-skills/{slug}/SKILL.md` | §10, §11 | iCoDer has 4 SKILL.md in-repo. Publish to public URI matching Corti `docs.corti.ai/.well-known/agent-skills/` pattern. | 2-3 hours |
| **P2-5** | Localize Corti tools to CN equivalents (DrugBank→CN pharmacy, PubMed→CNKI, web search→Baidu) | §8 | Wire CN medical KBs as MCP tools. | 16-24 hours |

**P2 total:** 5 items, ~48-70 hours.

---

### iCoDer ADVANTAGES — KEEP, do not remove

Per ICODER_ADVANTAGE decision (PDF §2.3):

1. Server-persisted RunHistory table (`run_history` alembic 010) — Corti has client-only.
2. RunTrace page UI (`/runs/{run_id}/trace`) — Corti has inline drawer only.
3. trace_events with api_client_id metadata — Corti does not persist this.
4. Forked-from badge (config.source_agent_ref) — Corti has no upstream link.
5. Auto-copied Name + Toast on fork — Corti's template-instantiation is silent.
6. API Playground tab in DeveloperQuickstart — Corti has only static docs.

**Decision:** Do NOT remove these to "match Corti more closely". They are product differentiators.

---

### DO NOT_COPY — Explicitly do not add

Per DO_NOT_COPY decision (PDF §2.3):

1. **Full version control on agents** — Corti doesn't have it. Template-instantiation is the Corti model. Do not add git-style versioning.
2. **Marketplace** — Corti doesn't have it. iCoDer correctly deleted in Phase 1.2 (memory `project_p1_2_corti_parity_deletion_2026_06_30`). Do not re-add.

---

## 2. Phase 5 Recommendation — Quality at Scale

### 2.1 Theme

Phase 5 theme: **Quality at Scale**

Phase 4 (A-G + 4-H audit) closed structural parity. iCoDer now matches Corti on all product-defining surfaces. Phase 5 should pivot from **structural parity** to **quality benchmarking + scale**.

### 2.2 Phase 5 scope (proposed)

#### Track A — Close P0 + P1 (mandatory, ~16-23 hours)

| Step | Tasks | Hours |
|---|---|---|
| A1 | P0 AUDIT_BLOCKER_FIX: BUG-12-01 (trace emission) + BUG-12-02 (currency) | 2-4 |
| A2 | P1-1: Wire `/usage` to `run_history.cost` | 4-6 |
| A3 | P1-2: Refactor Web Component API to Corti method-based | 4-6 |
| A4 | P1-3: Publish `@icoder/embedded` to npm | 2-4 |
| A5 | P1-4: RunHistory Date filter + daily chart | 2-3 |

**Track A total:** ~14-23 hours (1-2 dev days).

#### Track B — Quality benchmark (mandatory, ~16-24 hours)

| Step | Tasks | Hours |
|---|---|---|
| B1 | §16 (deferred): Build 10 multi-specialty test fixtures (orthopedics/cardiology/GI/pulm/neuro/OB-GYN/urology/endocrine/oncology/peds) | 4-6 |
| B2 | Run 100-case benchmark on Medical Coding Agent (sample from `ccl2026_train_gold.json` 1800 cases, seed=42) | 2-4 |
| B3 | Compute metrics: per-case micro-F1 + aggregate micro-pooled + F1@1/F1@5 + subdivision-tolerant | 1-2 |
| B4 | Compare to Corti reported quality (if available) or to baseline (Phase 4-G) | 1-2 |
| B5 | §6 (deferred): Per-agent 8×8 dual-system walkthrough (8 agents × 8 cases × 2 systems = 128 runs) | 8-10 |

**Track B total:** ~16-24 hours (2-3 dev days).

#### Track C — P2 polish (optional, can extend to Phase 5+)

| Step | Tasks | Hours |
|---|---|---|
| C1 | P2-1: Build 4 more pre-built agents (Coding Audit + Charge Compliance + Insurance Audit + Discharge Summary Quality) | 12-16 |
| C2 | P2-2: Wire DRG/DIP + insurance audit KBs | 16-24 |
| C3 | P2-3: API Client action buttons | 2-3 |
| C4 | P2-4: Publish Agent Skills to `.well-known` URI | 2-3 |
| C5 | P2-5: Localize CN tools (CN pharmacy, CNKI, Baidu) | 16-24 |

**Track C total:** ~48-70 hours (6-9 dev days, optional).

### 2.3 Phase 5 success criteria

1. **P0 bugs closed** — Trace shows 3 steps for 3-step run; currency unified across TopBar/billing/usage.
2. **P1 gaps closed** — `/usage` wired; Web Component API matches Corti; npm published; Date filter+chart added.
3. **Quality benchmark executed** — 100-case F1 measured; 10 test fixtures built; 8×8 dual-system walkthrough done.
4. **No regressions** — tsc 0; backend tests pass; 75+ frontend vitest pass; no UI_ONLY shells introduced.
5. **iCoDer ADVANTAGES preserved** — 6 ADVANTAGES still present (RunHistory table + RunTrace page + trace_events metadata + Forked-from badge + auto-copied Name + API Playground tab).

### 2.4 Phase 5 NOT in scope

- Adding full version control on agents (DO_NOT_COPY).
- Re-adding marketplace (DO_NOT_COPY).
- Removing iCoDer ADVANTAGES (do not remove).
- Migrating to Supabase (LOCALIZE_FOR_CHINA — stay on self-managed Postgres).
- Major UI redesign (Phase 4 redesign + taste-skill already polished).

---

## 3. Priority Decision Matrix

| Priority | Action | Decision | When |
|---|---|---|---|
| 🔴 P0 | Fix BUG-12-01 (trace) + BUG-12-02 (currency) | AUDIT_BLOCKER_FIX | Before Phase 5 starts (immediate) |
| 🟡 P1 | Close 4 gaps (usage wiring + Web Component + npm + Date filter) | Phase 5 Track A | First 1-2 dev days |
| 🟢 P2 (quality) | Build fixtures + 100-case benchmark + 8×8 walkthrough | Phase 5 Track B | Next 2-3 dev days |
| 🔵 P2 (polish) | 4 more agents + DRG/DIP KBs + Client buttons + Skills pub + CN tools | Phase 5 Track C (optional) | Extend as bandwidth allows |

---

## 4. Resource Estimates

| Track | Hours | Dev Days |
|---|---|---|
| Track A (P0+P1) | 14-23 | 2-3 |
| Track B (quality benchmark) | 16-24 | 2-3 |
| Track C (polish, optional) | 48-70 | 6-9 |
| **Total Phase 5 (A+B)** | **30-47** | **4-6** |
| **Total Phase 5 (A+B+C)** | **78-117** | **10-15** |

---

## 5. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| BUG-12-01 fix breaks existing trace_events consumers | Run regression tests on RunTrace page + Event Inspector before commit |
| BUG-12-02 currency choice (¥ vs $) may surprise users | Document in CLAUDE.md + show both in DevTools during transition |
| Web Component API refactor breaks existing embeds | Version package as `@icoder/embedded@2.0.0` + provide migration guide. Existing attribute-based config deprecated but functional for 1 minor version. |
| 100-case benchmark takes ~100×10s = 17 min compute time | Run off-peak; cache results; parallel where possible |
| 8×8×2 = 128 runs may exceed Corti free tier | Use iCoDer dev env for iCoDer side; Corti side use existing credits |
| DRG/DIP rule engine is 16-24h estimate, may grow | Time-box to 24h; if not complete, defer rule engine to Phase 6 |

---

## 6. Deferred from Phase 4-H Audit

These items were not done in Phase 4-H audit per dev-FREEZE + priority decisions:

| Task ID | Description | Defer to |
|---|---|---|
| #53 | §16: Build 10 test fixtures | Phase 5 Track B1 |
| #60 | §6: Per-agent 8×8 walkthrough | Phase 5 Track B5 |

Both are quality benchmark tasks, not structural parity tasks. Phase 4-H audit captured the structural findings; Phase 5 executes the quality measurement.

---

## 7. Phase 5 Backlog (forward reference)

After Phase 5 closes (P0 fixed, P1 closed, quality benchmark done), backlog candidates for Phase 6+:

1. **Phase 6 candidate — Real-time collaboration** — multi-user editing on same agent (Corti does not have this either — greenfield).
2. **Phase 6 candidate — Workflow automation** — chain agents into pipelines (e.g. extract facts → code → audit). Corti does not have this.
3. **Phase 6 candidate — Agent versioning light** — track name + description changes over time (NOT full version control, just audit log).
4. **Phase 6 candidate — Plugin marketplace** — community-contributed agents (iCoDer differentiator vs Corti; but DO NOT_COPY means: do not add unless clearly adds value).
5. **Phase 6 candidate — Mobile responsive** — current iCoDer desktop-only; Corti has mobile Web Component (not full mobile console).
6. **Phase 6 candidate — SOC 2 / ISO 27001 certification** — for enterprise sales; Corti has these.

---

## 8. Audit Closure

**Phase 4-H audit deliverables:**
- 17 markdown reports in `reports/phase4h/`
- 5 machine-readable outputs in `outputs/phase4h/` (JSON + CSV)
- 14 HTML dumps in `outputs/phase4h/` (Corti expert page snapshots)
- 3 synthesis deliverables (Executive Summary + Walkthrough Log + Final Report)
- This Architecture Inference + Phase 5 Recommendation (§18+§19)

**Final verdict:** **PASS WITH GAPS** — iCoDer has achieved structural parity with Corti. 2 P0 bugs + 4 P1 gaps documented. 6 iCoDer ADVANTAGES preserved. 0 UI_ONLY shells (major improvement vs Phase 4-E3).

**Recommended next phase:** Phase 5 — Quality at Scale (~30-47 dev hours for mandatory tracks; ~78-117 hours including polish).

**Audit closed:** 2026-07-10.

---

## Appendix: Phase 5 Roadmap One-Pager

```
PHASE 5 — QUALITY AT SCALE

Track A — Close P0+P1 (2-3 dev days):
  A1. Fix BUG-12-01 trace double-count           [1-2h]
  A2. Fix BUG-12-02 currency mismatch            [1-2h]
  A3. Wire /usage to run_history.cost            [4-6h]
  A4. Refactor Web Component API to Corti shape  [4-6h]
  A5. Publish @icoder/embedded to npm            [2-4h]
  A6. RunHistory Date filter + daily chart       [2-3h]

Track B — Quality benchmark (2-3 dev days):
  B1. Build 10 multi-specialty test fixtures      [4-6h]
  B2. Run 100-case benchmark on Medical Coding    [2-4h]
  B3. Compute F1 metrics (per-case + pooled)      [1-2h]
  B4. Compare to baseline + Corti (if available) [1-2h]
  B5. Per-agent 8×8 dual-system walkthrough       [8-10h]

Track C — Polish (optional, 6-9 dev days):
  C1. Build 4 more pre-built agents               [12-16h]
  C2. Wire DRG/DIP + insurance KBs                [16-24h]
  C3. API Client action buttons                   [2-3h]
  C4. Publish Agent Skills to .well-known         [2-3h]
  C5. Localize CN tools (CN pharmacy, CNKI, etc.) [16-24h]

KEEP (iCoDer ADVANTAGES, do not remove):
  - Server-persisted RunHistory table
  - RunTrace page UI
  - trace_events with api_client_id
  - Forked-from badge
  - Auto-copied Name + Toast
  - API Playground tab

DO NOT COPY:
  - Full version control on agents
  - Marketplace (deleted in P1.2, do not re-add)

Total: 30-47 hours mandatory / 78-117 hours incl. polish
```

---

**Phase 4-H audit complete.** Ready for user review of Phase 5 plan.
