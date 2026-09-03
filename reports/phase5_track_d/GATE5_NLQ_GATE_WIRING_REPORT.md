# Gate 5 — Provider Query Data Model + Non-leading Query Gate Wiring Report

**Date**: 2026-07-11
**PDF ref**: §7 Gate 5 — Provider Query data model + non-leading gate
**Status**: `PASS_GATE5_NLQ_GATE_WIRED`
**Commit**: `feat(track-d5): add non-leading query compliance gate`

---

## 1. What changed

| Before (Gate 4) | After (Gate 5) |
|---|---|
| Domain models + DB tables exist, but no state machine service | `app/services/cdi_query_lifecycle.py` — pure-logic state machine + NLQ gate wiring |
| NLQ gate runs only in orchestrator stub | NLQ gate ENFORCED on every DRAFT → PENDING_CDI_REVIEW transition |
| No SLA computation | SLA computed on APPROVED transition (routine=72h, urgent=24h) |
| No transition audit events | Per-transition audit events emitted for downstream trace store |
| 55 tests | 90 tests (35 new in Gate 5) |

## 2. State machine (12 states + 3 terminal)

```
DRAFT
  ↓ (NLQ gate runs here)
PENDING_CDI_REVIEW
  ↓ (CDI specialist approves)
APPROVED                  ← SLA computed here
  ↓ (send to clinician)
SENT_TO_CLINICIAN
  ↓
VIEWED
  ↓
RESPONDED
  ↓
DOCUMENTATION_UPDATED
  ↓
REVALIDATED
  ↓
CLOSED                     ← terminal
```

Side states: `CANCELLED` (terminal), `ESCALATED` (can return to PENDING_CDI_REVIEW), `EXPIRED` (terminal).

Total: 9 main states + 3 side states = 12 states. 3 are terminal (CLOSED, CANCELLED, EXPIRED).

## 3. NLQ gate wiring (THE key Gate 5 deliverable)

The state machine REFUSES to transition from DRAFT to PENDING_CDI_REVIEW unless the NLQ gate returns PASS verdict.

```python
def attempt_transition(from_state, to_state, *, query_text, response_options, evidence_quote, topic, ...):
    # 1. State machine check
    if not validate_transition(from_state, to_state):
        return TransitionResult(accepted=False, reason=...)

    # 2. NLQ gate check (ONLY on DRAFT → PENDING_CDI_REVIEW)
    if from_state == "DRAFT" and to_state == "PENDING_CDI_REVIEW":
        nlq_result = gate_draft_to_pending_review(query_text, response_options, ...)
        if nlq_result.verdict == "BLOCK":
            # audit event: query.nlq_gate.blocked
            return TransitionResult(accepted=False, nlq_gate_result=nlq_result, ...)

    # 3. SLA computation (on APPROVED)
    if to_state == "APPROVED":
        sla_due_at = compute_sla_due_at(now, priority)

    # 4. Emit transition audit event
    return TransitionResult(accepted=True, ...)
```

This means a query that fails NLQ gate is STRUCTURALLY PREVENTED from reaching CDI specialist review. The query stays in DRAFT, the block reasons are recorded, and the orchestrator must regenerate the query before retrying.

## 4. SLA policy

| Priority | SLA hours | Example |
|---|---|---|
| `routine` | 72 | Elapsed business days across a weekend |
| `urgent` | 24 | Same business day |

Computed from the moment of APPROVED transition (not SENT_TO_CLINICIAN — the SLA clock starts when CDI specialist signs off, since that's when the query becomes the org's responsibility to deliver).

`compute_sla_due_at(approved_at, priority)` is exported for the audit dashboard (Gate 8) to compute overdue queries.

## 5. Audit events

Every transition emits 1-3 audit events:

| Event | When |
|---|---|
| `query.nlq_gate.passed` | DRAFT → PENDING_CDI_REVIEW with compliant query |
| `query.nlq_gate.blocked` | DRAFT → PENDING_CDI_REVIEW attempt with leading query (transition rejected) |
| `query.sla.set` | On APPROVED transition |
| `query.transition` | Every accepted transition |

Event fields: `event`, `from`, `to`, `ts` (ISO 8601 UTC), plus context-specific fields (`rules_failed`, `priority`, `sla_due_at`).

## 6. Tests (35 new)

### 6.1 `tests/unit/icoder/cdi/test_query_lifecycle.py`

- **18-way parametrized state machine matrix** (`test_state_machine_transition_matrix`): covers every allowed + several disallowed paths
- `test_validate_transition_returns_human_readable_reason`: error messages name the path
- `test_gate_draft_to_pending_review_passes_compliant_query`: 9/9 NLQ rules pass
- `test_gate_draft_to_pending_review_blocks_leading_query`: NLQ-001/004/005 fail
- `test_attempt_transition_draft_to_pending_with_compliant_query_accepted`: full integration
- `test_attempt_transition_draft_to_pending_with_leading_query_rejected`: BLOCK prevents transition
- `test_attempt_transition_to_approved_sets_sla`: routine SLA = 72h
- `test_attempt_transition_to_approved_urgent_priority_sla_24h`
- `test_attempt_transition_illegal_path_rejected`: DRAFT → SENT_TO_CLINICIAN blocked
- `test_attempt_transition_emits_transition_audit_event`
- `test_terminal_states_cannot_transition_out`: CLOSED/CANCELLED/EXPIRED × 4 targets
- `test_compute_sla_due_at_routine_72h`, `_urgent_24h`, `_unknown_priority_defaults_routine`
- `test_exported_exceptions_are_value_error_subclasses`
- **Full compliant lifecycle happy path**: DRAFT → CLOSED in 8 transitions, SLA respected

### 6.2 Test results

```
======================== 90 passed, 1 warning in 1.55s ========================
```

All 90 CDI tests pass (29 Gate 3 + 26 Gate 4 + 35 Gate 5). 0 regressions.

## 7. Verification

- ✅ 12 states (9 main + 3 side) with explicit transition table
- ✅ 3 terminal states (CLOSED, CANCELLED, EXPIRED) cannot transition out
- ✅ NLQ gate ENFORCED on DRAFT → PENDING_CDI_REVIEW (cannot bypass)
- ✅ SLA computed on APPROVED transition (routine=72h, urgent=24h)
- ✅ Audit events emitted for every state change + NLQ gate result
- ✅ Pure-logic service (no FastAPI/HTTP) — easy to test, easy to wire into REST later

## 8. What is NOT in Gate 5 (deferred)

- **DB persistence wiring**: `attempt_transition` returns `TransitionResult` with new state + audit events, but does not write to DB yet. Gate 6 adds an async DB session variant. Gate 9 wires it to REST API.
- **Notification emission**: SENT_TO_CLINICIAN transition should fire clinician notification (webhook/email). Gate 8.
- **SLA breach detection**: cron job to find queries past `sla_due_at` and transition to EXPIRED. Gate 8.

## 9. Boundary enforcement

| Boundary | Gate 5 enforcement |
|---|---|
| Every query non-leading | NLQ gate REFUSES transition to PENDING_CDI_REVIEW if BLOCK |
| Every query evidence-anchored | NLQ-007 (evidence required) blocks empty `evidence_quote` |
| CDI specialist must approve before send | APPROVED requires PENDING_CDI_REVIEW prior state |
| Clinician must respond before chart modification | DOCUMENTATION_UPDATED requires RESPONDED prior state |
| Audit trail complete | Every transition emits audit event with timestamp + actor |

## 10. Next: Gate 6 — CDI Orchestrator + clarification lifecycle wiring

PDF §8 Gate 6 — full orchestrator with real DeepSeek runner:
- Replace `stub_runner` with DeepSeek-backed runner
- Wire CapabilityRegistry for 4 Experts
- Thread CDI case through all 6 stages with real LLM calls
- Persist ProviderQuery in DB via Gate 5 service on query_generation completion

Commit: `feat(track-d6): add cdi clarification lifecycle and clinician response workflow`
