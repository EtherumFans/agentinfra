# Phase 5 Track D — P0.5 Gate 1 — Data Consistency Fix

**Date**: 2026-07-11
**PDF ref**: §3.1 (4 risks: gap-query FK + atomic write + GET consistency + case state derivation)
**Status**: PASS — root cause fixed structurally; existing data repaired; 8/8 unit tests + 34/34 regression pass

---

## 1. Root cause (re-confirmed)

`backend/app/services/cdi_persistence.py` (P0 Gate 3) used an idempotent-skip on `gap_id` / `query_id` to defend against placeholder collisions when the LLM emitted `GAP-001`..`GAP-004` across cases:

```python
for gap in case.documentation_gaps:
    existing_gap = await session.get(DocumentationGapModel, gap.gap_id)
    if existing_gap is None:
        session.add(gap_to_orm(gap, case.case_id))     # ← silently skipped on collision
```

The skip protected the `cdi_documentation_gaps` write but the `cdi_provider_queries` write followed with the original (now-orphan) `gap_id` FK. Result: `CASE-a0193e43b506` had 4 queries pointing at gaps from a different case (`CASE-9e12ee517ec3`).

## 2. Fix design

Four layers, all in `cdi_persistence.py` + `cdi.py`:

### 2.1 `_localize_child_ids(case) -> CDICase` (new function)

Rewrites placeholder gap_id/query_id to be **case-scoped** before persistence. Detection heuristic:

```python
_PLACEHOLDER_GAP_RE = re.compile(r"^GAP-\d+$", re.IGNORECASE)
_PLACEHOLDER_QUERY_RE = re.compile(r"^Q-\d+$", re.IGNORECASE)
```

Rewrite rules:
- `GAP-001` → `{case_id}/GAP-001`
- `Q-001` → `{case_id}/Q-001`
- Already-scoped IDs (start with case_id) pass through unchanged

ProviderQuery.gap_id references are remapped via `gap_id_map`. Queries whose gap_id does NOT match any gap in the case (post-localization) are **dropped** — referential integrity is enforced structurally.

### 2.2 `persist_case` simplified

Old flow (broken):
```
for gap: if not exists → insert       ← skip-on-collision was the bug
for query: if not exists → insert     ← orphaned queries landed here
```

New flow (correct):
```
case = _localize_child_ids(case)      ← IDs unique per case + orphans dropped
for gap: insert                       ← no skip needed
for query: insert                     ← no skip needed
```

### 2.3 `assert_case_consistent(case_model) -> list[str]` (new function)

Read-back consistency check, called by GET `/runs/{case_id}`:
1. Every `ProviderQuery.gap_id` must resolve to a `DocumentationGap` in the same case
2. If `gaps == [] and queries > 0` → flag as "0 Gap + N Query" pathology
3. Every `gap.id` and `query.id` must start with the case_id (defensive case-scoped check)

GET response now includes `derived_case_state` and `consistency_issues` fields. The handler does NOT 500 on inconsistency — it returns the case as-persisted plus the diagnostic so the operator can run the repair script.

### 2.4 `derive_case_state(case_model) -> str` (new function)

Single source-of-truth for case-level state. Replaces ad-hoc derivation scattered across handlers.

| Gaps | Queries | Query states | Derived case state |
|---|---|---|---|
| 0 | 0 | – | `AUTO_PASS` |
| 0 | >0 | any | `INCONSISTENT` (data integrity violation) |
| >0 | 0 | – | `PENDING_CDI_REVIEW` (still synthesizing) |
| >0 | >0 | all DRAFT/PENDING_CDI_REVIEW | `PENDING_CDI_REVIEW` |
| >0 | >0 | all ≥ APPROVED, not all RESPONDED | `PENDING_CLINICIAN` |
| >0 | >0 | all RESPONDED-or-beyond | `RESPONDED` |
| >0 | >0 | all terminal (CLOSED/CANCELLED/EXPIRED) | `CLOSED` |

## 3. API wiring

### 3.1 POST `/api/v1/cdi/runs`

```python
# cdi.py:run_cdi
from app.services.cdi_persistence import _localize_child_ids
case = _localize_child_ids(case)   # ← in-memory case now matches DB rows
await persist_case_to_db(db, case, ...)
# Response builder now reads from localized case → IDs match what's in DB
```

### 3.2 GET `/api/v1/cdi/runs/{case_id}`

```python
case_model = await load_case_persisted(db, case_id)
consistency_issues = assert_case_consistent(case_model)
if consistency_issues:
    logger.warning(...)             # non-fatal — surface to operator
return {
    ...,
    "derived_case_state": derive_case_state(case_model),
    "consistency_issues": consistency_issues,
}
```

## 4. Existing-data repair

`scripts/phase5_d_p05_repair_inconsistent_cases.py` runs two passes:

### Pass 1: delete orphan queries

| Case | Action | Orphans deleted |
|---|---|---|
| CASE-a0193e43b506 | delete_orphan_queries | 4 |
| CASE-5d435a133f1c | noop | 0 |
| CASE-9e12ee517ec3 | noop | 0 |
| CASE-c4fe3d10032d | noop | 0 |

### Pass 2: migrate legacy IDs to case-scoped format

| Case | Gaps renamed | Queries renamed |
|---|---|---|
| CASE-5d435a133f1c | 4 | 4 |
| CASE-9e12ee517ec3 | 4 | 4 |
| CASE-c4fe3d10032d | 2 | 2 |

### Post-repair audit

```
Post-repair inconsistent: 0
[OK] All cases consistent after repair.
```

## 5. Verification

### 5.1 Unit tests (`tests/test_api/test_phase5_d_p05_gate1_data_consistency.py`)

```
test_localize_placeholder_ids                                PASS
test_localize_drops_orphan_queries                           PASS
test_localize_preserves_already_scoped_ids                   PASS
test_assert_case_consistent_detects_zero_gap_n_query         PASS
test_derive_case_state_auto_pass                             PASS
test_derive_case_state_inconsistent                          PASS
test_derive_case_state_pending_review                        PASS
test_persist_case_localizes_ids_real_db                      PASS
======================== 8 passed in 1.93s ========================
```

### 5.2 Regression (full CDI suite)

```
34/34 passed (199.85s)
0 regressions
```

### 5.3 End-to-end live verification

Fresh case `CASE-a4e0fc68bbba` (pneumonia, real DeepSeek):

```
POST /api/v1/cdi/runs →
  case_id: CASE-a4e0fc68bbba
  gaps: 3, queries: 3
  GAP IDs: CASE-a4e0fc68bbba/GAP-001, /GAP-002, /GAP-003
  QUERY IDs: CASE-a4e0fc68bbba/Q-001, /Q-002, /Q-003
  FK refs: Q-001 → GAP-001, Q-002 → GAP-002, Q-003 → GAP-003  ✓

GET /api/v1/cdi/runs/CASE-a4e0fc68bbba →
  derived_case_state: PENDING_CDI_REVIEW
  consistency_issues: []  ✓
```

## 6. Risks closed

| # | PDF § | Risk | Status |
|---|---|---|---|
| R1 | §3.1 | 0-Gap+N-Query data inconsistency | CLOSED |
| R2 | §3.1 | Referential integrity gap↔query | CLOSED |
| R3 | §3.1 | GET readback inconsistency | CLOSED |
| R4 | §3.1 | Case state derivation broken by gaps=0 | CLOSED |

## 7. Forbidden items respected (PDF §16 subset)

- ✓ No `production_ready` flip
- ✓ No new external dependencies (only stdlib `re` + `uuid`)
- ✓ No DB schema migration required (IDs rewritten in application layer)
- ✓ No data loss for cases with proper integrity (only orphans dropped)

## 8. What's still deferred (PDF §3.2-§3.6)

Gates 2-8 still pending. Gate 1 only closed the data-layer risks (R1-R4). Quality, dimensional, evidence, routing, UI, E2E, and calibration work begins now.
