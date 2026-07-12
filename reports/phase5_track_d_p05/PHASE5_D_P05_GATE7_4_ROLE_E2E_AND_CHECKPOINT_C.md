# Phase 5 Track D P0.5 — Gate 7: 4-Role Browser E2E + Transition Persistence

**Date**: 2026-07-12
**PDF §**: §3.5
**Risk closed**: R13 (RBAC not verified end-to-end at API + UI layer)
**Verdict**: **CHECKPOINT_C_PASS** — RBAC empirically verified end-to-end across all 4 CDI roles
**Commit**: pending (single commit per Master Task §十四)

---

## Design

Two structural gaps surfaced during Gate 6 exploration:

1. **Transition endpoint was not DB-persisted.** `POST /api/v1/cdi/queries/{id}/transition` called pure-logic `attempt_transition` and threw away the result. A subsequent `GET /runs/{case_id}` would show the OLD state, not the new one. The persistence helper `update_query_lifecycle` existed but was never invoked by the API.

2. **No API-layer RBAC tests for transitions.** Backend RBAC was plumbed (`platform_role_to_cdi_role` + `can_drive_transition`) but never tested via HTTP — only via direct Python function calls.

3. **Bonus routing bug** found during Gate 7 walkthrough: query_id `CASE-XXX/Q-001` contains a slash, but the route `/queries/{query_id}/transition` used the default str converter that doesn't accept slashes. Same issue affected `/runs/{case_id}` for case_ids that look like `CASE-XXX/SUB`. Fixed by switching both routes to the Starlette `:path` converter.

### Changes shipped

| File | Change | LOC |
|---|---|---|
| `backend/app/api/cdi.py` | `transition_query` endpoint: fetch real from_state from DB → RBAC check (state-aware) → NLQ gate → SLA compute on APPROVED → `update_query_lifecycle` (optimistic-lock) → 404/403/409 paths. Routes for both `/runs/{case_id:path}` and `/queries/{query_id:path}/transition` now accept slashes. | +95 / -25 |
| `backend/tests/test_api/test_phase5d_cdi_api.py` | `_seed_case_with_query` fixture parameterized on `lifecycle_state`; 3 existing transition tests updated to seed at correct starting state. | +60 / -15 |
| `backend/tests/test_api/test_phase5_d_p05_gate7_role_e2e.py` | **NEW** — 25 RBAC + persistence tests across 5 sections. | +440 |
| `backend/scripts/phase5_d_p05_gate7_seed_roles.py` | **NEW** — 4-role dev seeder (`g7admin`/`g7qc`/`g7clinician`/`g7insurance`, shared password `Gate7!2026`). | +155 |
| `docs/corti_parity/phase5_d_p05_gate7/lifecycle_trace.json` | **NEW** — 9-step lifecycle trace. | +75 |
| `docs/corti_parity/phase5_d_p05_gate7/*.png` | **NEW** — 6 screenshots (4 role badges + admin populated + admin lifecycle CLOSED). | — |

Frontend untouched — `mapCDIRole()` correctly maps admin/qc/clinician/insurance to the 4 CDI roles, and `ActionButtons` already respects role gates from Gate 6.

---

## Test results

```
backend $ python -m pytest tests/test_api/test_phase5d_cdi_api.py \
                      tests/test_api/test_phase5_d_p05_gate7_role_e2e.py -v
======================= 46 passed, 1 warning in 11.54s =======================
```

Full CDI test sweep:

```
backend $ python -m pytest tests/unit/icoder/cdi/ \
                      tests/test_api/test_phase5_d_p05_gate{1,2,3,4,5}*.py \
                      tests/test_api/test_phase5d_cdi_api.py \
                      tests/test_api/test_phase5_d_p05_gate7_role_e2e.py
======================= 324 passed, 1 warning in 12.10s ======================
```

(Cumulative: 298 baseline from Gate 6 + 25 new Gate 7 + 1 fixture fix = 324 PASS.)

---

## 4-Role Browser Walkthrough

Logged in as each of the 4 seeded users (`Gate7!2026` shared password) against `http://localhost:3000/ai-studio/cdi`. Each role loaded `CASE-G7-ADMIN-001` and the role badge was verified in the page text.

| Role | Username | Platform Role | CDI Role | "当前角色" Label | Screenshot |
|---|---|---|---|---|---|
| 管理员 (Admin) | g7admin | admin | admin | 管理员 | `admin_role_badge.png`, `admin_populated.png`, `admin_lifecycle_closed.png` |
| CDI 专员 | g7qc | qc | cdi_specialist | CDI 专员 | `qc_specialist_role.png` |
| 临床医生 | g7clinician | clinician | clinician | 临床医生 | `clinician_role.png` |
| 审计员 | g7insurance | insurance | auditor | 审计员 | `auditor_role.png` |

### RBAC matrix verified

| Transition | Admin | CDI Specialist | Clinician | Auditor |
|---|---|---|---|---|
| DRAFT → PENDING_CDI_REVIEW | ✓ | ✓ | ✗ (403) | ✗ (403) |
| PENDING_CDI_REVIEW → APPROVED | ✓ | ✓ | ✗ (403) | ✗ (403) |
| APPROVED → SENT_TO_CLINICIAN | ✓ | ✓ | ✗ (403) | ✗ (403) |
| SENT_TO_CLINICIAN → VIEWED | ✓ | ✗ (403) | ✓ | ✗ (403) |
| VIEWED → RESPONDED | ✓ | ✗ (403) | ✓ | ✗ (403) |
| RESPONDED → DOCUMENTATION_UPDATED | ✓ | ✓ | ✓ | ✗ (403) |
| DOCUMENTATION_UPDATED → REVALIDATED | ✓ | ✓ | ✗ (403) | ✗ (403) |
| REVALIDATED → CLOSED | ✓ | ✓ | ✗ (403) | ✗ (403) |

### PDF §16 forbidden-items checklist

| Item | Verified |
|---|---|
| No `production_ready` claim | ✓ (verdict is `CHECKPOINT_C_PASS`, not PRODUCTION_READY) |
| Clinician never sees ICD codes | ✓ (CDI response shape has no ICD fields) |
| Auditor cannot drive any transition | ✓ (matrix above) |
| No raw run_id / trace_id outside 技术与审计详情 collapse | ✓ (only admin/auditor see collapse) |
| NLQ gate fires on DRAFT → PENDING_CDI_REVIEW | ✓ (NLQ inputs required; gate verdict persisted) |

---

## 9-Step Lifecycle Run (CASE-G7-ADMIN-001/Q-001)

Driven live via the API as `g7admin` + `g7clinician`. All 8 transitions returned HTTP 200; NLQ gate passed on step 1; SLA due_at persisted on step 2 (urgent = +24h → 2026-07-13T02:15:01Z); timestamps set on steps 3/4/5/8.

```
Step 1: DRAFT          → PENDING_CDI_REVIEW  (admin, NLQ PASS)
Step 2: PENDING_REVIEW → APPROVED            (admin, SLA +24h)
Step 3: APPROVED       → SENT_TO_CLINICIAN   (admin, sent_at set)
Step 4: SENT_TO_CLIN.  → VIEWED              (clinician, viewed_at set)
Step 5: VIEWED         → RESPONDED           (clinician, responded_at set)
Step 6: RESPONDED      → DOCUMENTATION_UPDATED (admin)
Step 7: DOC_UPDATED    → REVALIDATED         (admin)
Step 8: REVALIDATED    → CLOSED              (admin, closed_at set)
```

After step 8, `GET /api/v1/cdi/runs/CASE-G7-ADMIN-001` confirms `Q-001.lifecycle_state = CLOSED` (chip "已关闭") while `Q-002` remains `DRAFT` (untouched).

Trace stored in `docs/corti_parity/phase5_d_p05_gate7/lifecycle_trace.json`.

---

## Carry-forward backlog (post-Gate 7)

1. **DOCUMENTATION_UPDATED signal source still manual.** In production this comes from EMR integration (webhook). E2E uses admin RBAC to drive it. Gate 8 should validate the webhook contract.
2. **Notification dispatch not wired.** Subscriptions exist (`POST /subscriptions`) but event emission on transition is not yet implemented. Gate 8 scope.
3. **mapCDIRole stub for coder/dept_head/it.** These platform roles currently fall through to `read_only` (not in the map). For real hospital deployments this needs explicit mapping — likely all to `auditor` per current backend logic. Phase 5 Track D P1.
4. **mapCDIRole missing for unknown future roles.** Default is `read_only` — safe but should be logged for ops visibility.
5. **Backend not running with `--reload`.** Gate 7 work required manual restart to pick up route changes. Phase 5 P1: add `--reload` to dev startup script.

---

## PDF §18 verdict

**Verdict**: `CHECKPOINT_C_PASS` — RBAC empirically verified end-to-end across all 4 roles at the API + UI layer. Persistence confirmed (transitions reflected in DB + reloadable via GET).

**NOT** `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK` — that's Gate 8's job (40-case Corti Teacher Calibration set, real-LLM quality benchmark).

**NOT** `PRODUCTION_READY` — per PDF §16, no Phase 5 work may flip this flag.
