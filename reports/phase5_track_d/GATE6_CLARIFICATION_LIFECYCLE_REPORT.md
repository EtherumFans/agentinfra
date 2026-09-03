# Gate 6 — CDI Clarification Lifecycle + Clinician Response Workflow Report

**Date**: 2026-07-11
**PDF ref**: §8 Gate 6 — CDI Orchestrator + clarification lifecycle
**Status**: `PASS_GATE6_CLARIFICATION_LIFECYCLE_WIRED`
**Commit**: `feat(track-d6): add cdi clarification lifecycle and clinician response workflow`

---

## 1. What changed

| Before (Gate 5) | After (Gate 6) |
|---|---|
| Query state machine enforces NLQ gate on DRAFT → PENDING_CDI_REVIEW | + Clinician response workflow closes the loop |
| No revalidation logic | `revalidate_gap()` decides GAP_CLOSED / PARTIAL / STILL_OPEN / NEW / REJECTED |
| No document diff | `compute_document_diff()` produces SHA-256 hashes + delta metadata for before/after snapshots |
| 90 tests | 107 tests (17 new in Gate 6) |

## 2. Clinician response workflow

The full CDI loop (PDF §7) is now executable end-to-end:

```
1. CDI Agent runs against chart excerpt
   → emits DocumentationGaps + ProviderQueries (DRAFT)
2. CDI specialist reviews (NLQ gate enforces)
   → query state: PENDING_CDI_REVIEW → APPROVED
3. Query sent to clinician
   → query state: APPROVED → SENT_TO_CLINICIAN → VIEWED
4. Clinician responds
   → process_clinician_response() drives VIEWED → RESPONDED
5. Response category decides next state:
   - specific_clinical_answer → DOCUMENTATION_UPDATED
   - free_text_fallback → DOCUMENTATION_UPDATED (LLM validation deferred)
   - colonization_or_non_pathological → DOCUMENTATION_UPDATED
   - escape_hatch → ESCALATED (no chart modification)
6. Chart is revised (manual or assisted, default manual)
7. CDI re-run on revised chart
   → revalidate_gap() decides gap closure
   → query state: DOCUMENTATION_UPDATED → REVALIDATED → CLOSED
```

## 3. Response category → action matrix

| Category | Next state after RESPONDED | Why |
|---|---|---|
| `specific_clinical_answer` | DOCUMENTATION_UPDATED | Direct answer; chart gets updated |
| `free_text_fallback` | DOCUMENTATION_UPDATED | Free-text answer; LLM validation happens in revalidation |
| `colonization_or_non_pathological` | DOCUMENTATION_UPDATED | Lab result is rejected; chart gets updated to reflect |
| `escape_hatch` | ESCALATED | Clinician cannot answer; no chart change; needs human follow-up |

This matrix is encoded in `process_clinician_response()` and is the
single decision point for the workflow.

## 4. Revalidation outcomes

`revalidate_gap(gap, response)` returns one of:

| Outcome | Trigger | Action |
|---|---|---|
| `GAP_CLOSED` | specific answer matches gap.minimal_clarification_needed | Gap marked RESOLVED; query advances to REVALIDATED → CLOSED |
| `GAP_PARTIALLY_CLOSED` | free-text response | Gap stays OPEN; LLM validates free text in next CDI run |
| `GAP_STILL_OPEN` | colonization response | Gap stays OPEN; chart revised but different gap remains |
| `NEW_GAP_RAISED` | revalidation LLM finds new gap | New gap created; original may be closed |
| `RESPONSE_REJECTED` | escape_hatch response | Cannot close gap; query ESCALATED |

Real implementation in production re-runs the CDI LLM against the
updated chart; this Gate 6 stub uses response-category heuristics.
Gate 9+ wires the real revalidation call.

## 5. Document diff

`compute_document_diff(document_id, before_text, after_text)`:

- SHA-256 hash of each version (32-byte hex)
- Delta metadata: `before_length`, `after_length`, `delta_chars`
- Unchanged detection: same hash → `{unchanged: True}`
- Span-level diff (added_sections, modified_spans) deferred to Gate 7 UI

Stored in `cdi_document_versions.diff_summary` (JSON column).

## 6. Tests (17 new)

### 6.1 `tests/unit/icoder/cdi/test_clinician_response.py`

- **5-way parametrized** ClinicianResponseValue.category classification
- `test_process_clinician_response_specific_answer_advances_to_documentation_updated`
- `test_process_clinician_response_escape_hatch_escalates` (escape hatch does NOT update chart)
- `test_process_clinician_response_colonization_advances_to_documentation_updated`
- `test_process_clinician_response_free_text_advances_to_documentation_updated`
- `test_revalidate_gap_specific_answer_closes_gap`
- `test_revalidate_gap_escape_hatch_rejected`
- `test_revalidate_gap_free_text_partial_close`
- `test_revalidate_gap_colonization_keeps_gap_open`
- `test_compute_document_diff_unchanged_returns_unchanged_summary`
- `test_compute_document_diff_changed_records_delta`
- `test_compute_document_diff_hash_is_sha256_hex`
- `test_integration_response_to_diff_charts_revised_correctly` (e2e Gate 6 scenario)

### 6.2 Test results

```
======================= 107 passed, 1 warning in 1.63s ========================
```

All 107 CDI tests pass (29 Gate 3 + 26 Gate 4 + 35 Gate 5 + 17 Gate 6).

## 7. Verification

- ✅ Full CDI loop is executable end-to-end (DRAFT → CLOSED)
- ✅ Escape hatch responses correctly ESCALATE rather than marking chart updated
- ✅ Revalidation covers 4 response categories with distinct outcomes
- ✅ Document diff produces stable hashes + delta metadata
- ✅ All transitions emit audit events (Gate 5 wiring inherited)
- ✅ NLQ gate still enforced on DRAFT → PENDING_CDI_REVIEW (Gate 5 not regressed)

## 8. What is NOT in Gate 6 (deferred)

- **Real DeepSeek runner for orchestrator**: Gate 3 `stub_runner` still in place; production runner arrives when LLM prompts are finalized in Gate 7+ integration testing
- **LLM-based revalidation**: `revalidate_gap()` uses response-category heuristics; real CDI LLM re-run deferred until backend CDI run endpoint exists (Gate 9)
- **Span-level diff**: `compute_document_diff()` produces hash + delta only; difflib-based span diff arrives with Gate 7 UI (frontend concern)
- **DB persistence**: Service-layer functions return TransitionResults but do not write to DB yet; Gate 9 REST API wires async DB session

## 9. Boundary enforcement audit

| Boundary | Gate 6 enforcement |
|---|---|
| AI cannot modify chart without clinician confirmation | `process_clinician_response` REQUIRES VIEWED state + clinician response before DOCUMENTATION_UPDATED |
| Escape hatch responses are not used to update charts | escape_hatch → ESCALATED (not DOCUMENTATION_UPDATED) |
| Audit trail complete | Every response + revalidation emits audit events |
| Production writeback still blocked | No writeback tools called in any Gate 6 code path |

## 10. Next: Gate 7 — CDI Workbench (3-pane) + Physician Response Panel

PDF §11 Gate 7 — frontend implementation:
- 3-pane workbench (Case | Gaps+Queries | Physician Response)
- Provider Query review UI (CDI specialist)
- Physician Response Panel (clinician)
- Document diff view (before/after clarification)
- zh-CN primary UI

Commit: `feat(track-d7): add cdi workbench and physician response panel`
