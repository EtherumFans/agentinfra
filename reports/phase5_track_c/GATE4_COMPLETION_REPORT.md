# Phase 5 Track C — Gate 4 Completion Report

**Date**: 2026-07-11
**Gate**: 4 — Coding compliance orchestrator mainline + Human Review Gate (§9)
**Verdict**: `PASS_GATE4_CODING_COMPLIANCE_MAINLINE_READY`

---

## 1. Gate 4 scope (from PDF §9)

PDF §9 mandates a 7-stage coding compliance mainline that threads CaseState through 7 agents and ends in a Human Review Gate decision.

| § | Requirement | Status |
|---|---|---|
| §9.1 | Implement CodingComplianceOrchestrator composing 7 stage agents | ✅ Closed |
| §9.2 | Stage order: discharge → medical-coding → principal-dx → evidence → compliance → note-completeness → drg | ✅ Closed |
| §9.3 | CaseState accumulator threaded through all stages | ✅ Closed |
| §9.4 | Human Review Gate (AUTO_PASS / REVIEW_RECOMMENDED / REVIEW_REQUIRED / BLOCKED_*) | ✅ Closed |
| §9.5 | Idempotent per case_id | ✅ Closed |

## 2. Implementation

**File**: `backend/app/icoder/agent_runtime/orchestrator/coding_compliance_orchestrator.py` (~450 LOC)

### Stage pipeline

```
input_text (raw discharge summary)
    │
    ▼
[Stage 1] discharge-summary-structuring
    │  → structured_sections{diagnoses, procedures, treatment_summary}
    ▼
[Stage 2] medical-coding-agent
    │  → result.codes[{code, type, confidence, evidence, ...}]
    ▼
[Stage 3] principal-diagnosis-review
    │  → recommended{code, display} + coding_draft_consistent + rationale
    ▼
[Stage 4] evidence-extractor
    │  → supported_codes / uncertain_candidates / rejected_candidates
    ▼
[Stage 5] compliance-guardrail
    │  → violations[{rule_id, severity, ...}] + risk_level + compliant
    ▼
[Stage 6] note-completeness
    │  → required/present/missing/incomplete_sections + completeness_score
    ▼
[Stage 7] drg-analyzer
    │  → risk_points + drg_dip_rule_reservation_note
    ▼
CaseState.normalized + CaseState.conflicts
    │
    ▼
Human Review Gate
    │
    ▼
{AUTO_PASS | REVIEW_RECOMMENDED | REVIEW_REQUIRED | BLOCKED_*}
```

### CaseState accumulator

```python
@dataclass
class CaseState:
    case_id: str
    input_text: str
    agent_id: str = "coding-compliance-mainline"
    stage_outputs: dict[str, dict]        # raw per-stage result dicts
    stage_errors: dict[str, str]          # "" on success
    stage_latencies_ms: dict[str, int]
    normalized: dict[str, NormalizedExpertResult]
    conflicts: list[ConflictResolution]
    completion: CompletionDecision | None
    review_gate_status: str               # AUTO_PASS | REVIEW_* | BLOCKED
    review_gate_reasons: list[str]
    review_gate_blocker: str              # BLOCKED_* code
```

### Human Review Gate matrix (§9.4)

| Blocker code | Trigger |
|---|---|
| `BLOCKED_MISSING_DISCHARGE` | Stage 1 produced no output |
| `BLOCKED_NO_CODES_EXTRACTED` | Stage 2 emitted zero ICD codes |
| `BLOCKED_PRIMARY_DX_CONFLICT` | Stage 2 primary ≠ Stage 3 recommended |
| `BLOCKED_CRITICAL_RULE_VIOLATION` | Stage 5 raised R001/R002/R004/R009/R010 (critical/high) |
| `BLOCKED_NOTE_SEVERELY_INCOMPLETE` | Stage 6 `completeness_score < 0.30` |

Non-blocking outcomes:
- `AUTO_PASS` — clean run, completion status `COMPLETED`
- `REVIEW_RECOMMENDED` — `COMPLETED_WITH_WARNINGS`
- `REVIEW_REQUIRED` — `NEEDS_HUMAN_REVIEW` or `INCOMPLETE`

## 3. Files added (Gate 4)

| File | LOC | Purpose |
|---|---|---|
| `backend/app/icoder/agent_runtime/orchestrator/coding_compliance_orchestrator.py` | 450 | 7-stage mainline + Human Review Gate |
| `backend/tests/unit/icoder/orchestrator/test_coding_compliance_orchestrator.py` | 290 | 16 tests |
| `backend/scripts/phase5_track_c_gate4_smoke.py` | 90 | Real-DeepSeek smoke driver |

## 4. Test evidence

```
tests\unit\icoder\orchestrator\test_coding_compliance_orchestrator.py ................
======================== 16 passed, 1 warning in 1.32s ========================
```

Coverage:
- Happy path AUTO_PASS (1)
- Case ID determinism (2)
- Empty input rejection (1)
- Stage failure → downstream skip (2)
- BLOCKED_NO_CODES_EXTRACTED (1)
- BLOCKED_PRIMARY_DX_CONFLICT (1)
- BLOCKED_CRITICAL_RULE_VIOLATION (1)
- BLOCKED_NOTE_SEVERELY_INCOMPLETE (1)
- REVIEW_RECOMMENDED non-blocking (1)
- Disabled blockers pass-through (1)
- Stage ordering + accumulation (2)
- Real-agent shape (`result.codes` instead of `extracted_diagnoses`) (1)
- Idempotent case_id (1)

## 5. Real-DeepSeek smoke (7 stages × live backend)

```
[OK]   discharge-summary-structuring           3562ms cost=¥0.000178
[OK]   medical-coding-agent                    5172ms cost=¥0.000000 (corti_like_fast)
[OK]   principal-diagnosis-review              5437ms cost=¥0.000258
[OK]   evidence-extractor                      4655ms cost=¥0.000281
[OK]   compliance-guardrail                      32ms cost=¥0.000000 (deterministic rule engine)
[OK]   note-completeness                         46ms cost=¥0.000000 (cached/fast path)
[OK]   drg-analyzer                            5266ms cost=¥0.000203
                                             ─────────
                              pipeline total: ~24s   ¥0.000920
```

All 7 stages returned 200 OK on a representative T12 fracture sample. Real DeepSeek latencies: 4.5–5.5s per LLM stage; compliance-guardrail + note-completeness fall through to RuleEngineProvider fast path (32–46ms).

Medical-coding agent emits `result.codes[]` (not `extracted_diagnoses[]`). Orchestrator's `_extract_codes_for_principal` and `_extract_primary_dx_code` were updated to handle both shapes (synthetic test shape + real production shape).

## 6. What this closes

- ✅ §9.1–§9.5 explicit pipeline with named stages
- ✅ CaseState accumulator threaded through all stages
- ✅ Cross-stage conflict detection (medical-coding primary vs principal-dx-review recommended)
- ✅ Human Review Gate with 5 specific blockers + 3 non-blocking outcomes
- ✅ Real-agent shape support (`result.codes[]` from production medical-coding-agent)
- ✅ Idempotent per case_id (Gate 7 / browser walkthrough can rerun same case)

## 7. Deferred to Gate 5/6

- **Gate 5**: UI workbench that surfaces `CaseState` to clinicians (one screen per stage + gate decision banner)
- **Gate 6**: Trace + A2A + Embedded integration (parent-child run tree, 16 event types, A2A Card)
- **Production wiring**: Replace the stub `agent_runner` with real HTTP calls to `/api/v1/agents/{id}/run` (the smoke script already does this ad-hoc; Gate 6 makes it the production path)

## 8. Next: Gate 5 — Agent-specific UI workbenches

Gate 5 builds UI workbenches for the 7 coding-compliance agents. Each workbench shows:
- Stage input (the previous stage's output, or raw text for stage 1)
- Stage output (rendered structured_output)
- Stage latency + cost
- Conflicts (if any) + resolution path
- Human Review Gate decision banner

Plus a top-level CaseState viewer showing the full pipeline state.
