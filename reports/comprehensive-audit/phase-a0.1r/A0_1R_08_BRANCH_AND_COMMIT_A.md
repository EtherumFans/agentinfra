# Phase A0.1R Gate 8 — Branch & Commit A (Bucket A Product Snapshot)

> Creates the first of three commits on the audit-only branch
> `audit/phase-a0.1r-freeze`. Bucket A captures the audited product
> substrate: the exact state on which the Phase A0.1R audit package
> opines. Phase A0.1R is **read-only with respect to product code** —
> no Medical Coding or CDI prompts, no agent logic, no runtime
> semantics were modified. The only product-state changes are the
> Gate 1 redaction and Gate 6 Bucket D closure.
>
> Verdict: `PHASE_A0_1_R_GATE_8_BRANCH_AND_COMMIT_A_CREATED_REGRESSION_PASSED`
> Hard Checkpoint D: **CLOSED**

Spec reference: Phase A0.1R charter §3.Gate8.

---

## §1. Branch creation

```
Base ref:    c147d015455017bc1d8420cbdbd813b3b8ec23ce
             (= Phase 5 Track H Tier 2 commit; Phase A0.1 trusted HEAD)
Branch:      audit/phase-a0.1r-freeze
Created at:  2026-07-17 (this gate)
```

The branch is named `audit/phase-a0.1r-freeze` per charter §4 naming
convention (prefix `audit/` distinguishes audit-only branches from
feature branches). The branch was created **before** any staging
so that the master branch remains untouched and the audit work is
isolated.

**Charter constraint honored**: not on master, no force-push, no PR
opened.

## §2. Regression gate (must pass BEFORE Commit A)

Charter §3.Gate8 SC-2 requires that the product state at the moment
of Commit A is regression-clean. We ran:

| Regression | Result |
|---|---|
| `pytest backend/tests/test_api/test_phase7_gate13a_audit.py` | 1/1 PASS |
| `pytest backend/tests/test_api/test_phase7_gate3_agent_run_idempotency.py` | 16/16 PASS |
| `python -c "from backend.app.main import app; print(len(app.routes))"` | 237 routes import OK |
| `npm run -s tsc` (frontend/packages/icoder-embedded) | 0 errors |

Total: 17/17 pytest PASS + clean imports + clean tsc.

**No regression introduced by Phase A0.1R** — expected, since Phase
A0.1R did not modify product code paths beyond the Gate 1 redaction
(documents only) and Gate 6 Bucket D closure (file moves + .gitignore).

## §3. Commit A contents

```
commit 87754abd1f8dd351731bac495518fd9e05ed2a72
Author: SONG Luhua
Date:   2026-07-17
Subject: audit/phase-a0.1r: audited product snapshot (Bucket A) — Phase A0.1R Gate 8
Files:  122 changed, 13738 insertions(+), 616 deletions(-)
```

### §3.1 Composition by category

| Category | Files | Bucket-A role |
|---|---|---|
| `.gitignore` (Bucket D patches) | 1 | Gate 6 product-state change |
| Backend alembic migrations | 4 | Phase 7 gates 3-5 / 13A schema |
| Backend app/api | 6 | Phase 7 examples + preview_sessions + runs |
| Backend app/middleware | 1 | Phase 7 Gate 6 partner_cors |
| Backend app/models | 5 | Phase 7 models + Phase A0.1 modifications |
| Backend app/services | 4 | Phase 7 idempotency/preview_ticket/run_lifecycle/trace_token |
| Backend tests (test_api + unit) | 13 | Phase 7 gates 1,3,4,5,6,7,8,9,13A |
| Backend tests (modified) | 2 | Phase A0.1 conftest + test_phase4f_agent_run |
| Frontend src | 5 | Phase 7 EmbeddedAssistantPage + App + Layout + locales + e2e |
| packages/icoder-embedded (src + demos) | 10 | Phase 6 widget 2.0 + Phase 7 demos (no dist/, no .tgz) |
| packages/icoder-sdk (src + README) | 14 | Phase 6 SDK beta.2 (no dist/, no .tgz) |
| packages/icoder-web + web-components DEPRECATED | 2 | Phase A0.1 archival markers |
| examples/partner-reference-app | 7 | Phase 7 Gate 12 reference app |
| phase7-external-consumer | 7 | Phase 7 external consumer build (no dist/) |
| 35 relocated PNGs | 35 | Gate 6 relocation target |
| 2 Phase A0.1 reports (redacted) | 2 | Gate 1 redaction recipients |
| **TOTAL** | **122** | |

### §3.2 Gate 1 + Gate 6 product-state footprint

The **only** product-state changes authored by Phase A0.1R are:

1. `examples/partner-reference-app/.env` — redacted compromised secret quotation (Gate 1)
2. `reports/comprehensive-audit/phase-a0.1/A0_1_01_*.md` — redacted 2 inline secret quotations (Gate 1)
3. `reports/comprehensive-audit/phase-a0.1/A0_1_09_*.md` — redacted 2 inline secret quotations (Gate 1)
4. `.gitignore` — appended Gate 6 Bucket D patches (specific .tgz + dist/ paths, no global *.tgz)
5. 35 root PNGs relocated under `reports/comprehensive-audit/evidence/screenshots/relocated-from-root/`
6. 14 previously-tracked root PNGs deleted from root (their content now lives at the relocated path)
7. `packages/icoder-sdk/package-lock.json` deletion accepted

Everything else in Commit A was already in the working tree as part of
Phase A0.1 or Phase 7 deliverables. Phase A0.1R does not introduce new
product code.

## §4. Safety audits before commit

| Check | Result |
|---|---|
| No `.env` files staged | ✅ (only `.env.example`) |
| No `.audit-chrome-profile/` staged | ✅ |
| No `*.bak` / `*.db` / `*.db-journal` staged | ✅ |
| No `dist/` staged except `packages/icoder-embedded/dist/` (preserved by Gate 6 §1.2) | ✅ |
| No `.tgz` staged | ✅ |
| No Phase A0.1R audit-package files staged (those go in Commit B) | ✅ |
| Compromised-secret fingerprint absent from staged diff | ✅ |

The single intentionally-preserved `dist/` is
`packages/icoder-embedded/dist/{icoder-assistant.js,icoder-assistant.d.ts}`
— preserved per Gate 6 §1.2 as KEEP_HISTORICALLY_TRACKED. A future
policy change may migrate this to SOURCE_ONLY_AND_REBUILD but that
is out of Phase A0.1R scope.

## §5. Hard Checkpoint D — Branch + Commit A

| Sub-check | Status |
|---|---|
| SC-1: branch `audit/phase-a0.1r-freeze` created from trusted HEAD `c147d01` | ✅ |
| SC-2: regression passed BEFORE commit (17/17 pytest + clean imports + clean tsc) | ✅ |
| SC-3: Bucket A contents clearly separated from Bucket B (audit package) | ✅ |
| SC-4: no secrets / PHI / .env / chrome-profile in Commit A | ✅ |
| SC-5: Gate 1 redaction + Gate 6 Bucket D closure land in Commit A (product state) | ✅ |
| SC-6: Phase A0.1R audit package (under `reports/comprehensive-audit/phase-a0.1r/`) NOT staged in Commit A | ✅ |
| SC-7: commit message documents exact contents + trusted HEAD + regression result | ✅ |
| SC-8: master branch untouched (Commit A is on `audit/phase-a0.1r-freeze` only) | ✅ |
| SC-9: no force-push, no PR opened | ✅ |
| SC-10: commit hash recorded for traceability (`87754ab`) | ✅ |

**Hard Checkpoint D: ✅ CLOSED (10/10 sub-checks)**

## §6. Findings raised in Gate 8

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G8-001** (closed) | P1 | Branch `audit/phase-a0.1r-freeze` created from trusted HEAD `c147d01`. |
| **A0.1R-G8-002** (closed) | P1 | Regression clean before commit: 17/17 pytest + imports + tsc. |
| **A0.1R-G8-003** (closed) | P1 | Commit A `87754ab` created with 122 files; Bucket A isolated from Bucket B. |
| **A0.1R-G8-004** | P3 | packages/icoder-embedded/dist/ preserved in Commit A; future SOURCE_ONLY_AND_REBUILD migration is out of scope. |

---

## §7. Gate 8 verdict

```
PHASE_A0_1_R_GATE_8_BRANCH_AND_COMMIT_A_CREATED_REGRESSION_PASSED

Hard Checkpoint D: CLOSED
  - Branch:        audit/phase-a0.1r-freeze (from c147d0154550)
  - Regression:    17/17 pytest PASS + clean imports + tsc 0 errors
  - Commit A:      87754abd1f8dd351731bac495518fd9e05ed2a72 (122 files)
  - Bucket split:  Commit A = product substrate; Commit B = audit package

NEXT_GATE: GATE_9_COMMIT_B_AND_C_AND_ANNOTATED_TAG
NEXT_ALLOWED_VERDICT:
  PASS_PHASE_A0_1_R_SECURE_FREEZE_RECONCILED_AND_BASELINE_IMMUTABLE
```

End of Gate 8.
