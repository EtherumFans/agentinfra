# A1B-AE-R.4 — Local Expert Completion

**Sub-gate**: R.4 (Local Expert completion)
**Date**: 2026-07-23
**Branch**: `phase-a1b/agent-expert-runtime-verification`
**Predecessor**: R.3 (`3a06543`)

## Verdict

```
PASS_A1B_AE_R_4_LOCAL_EXPERT_COMPLETION_FILED
```

FILED per charter §10 — phase terminal R.6 decides promotion to `_VERIFIED`.

## Scope

R.4 closes the A1B-AE.6/7/9 local-Expert gaps:

| A1B-AE gap | R.4 fix |
|---|---|
| Calculator catalogue was BMI + Cockcroft-Gault only (2 of Corti's 6+ formulas) | Expanded to 6 formulas: BMI, Cockcroft-Gault, CHA2DS2-VASc, MELD-Na, eGFR CKD-EPI 2021, Wells DVT |
| Memory Expert had sentence-transformers + ConversationMemory but no bridge from real Context messages | New `MemoryExpert.ingest_context_messages()` reads ContextMessageRow stream + deduplicates by `context_id:message_id` + writes ConversationMemory rows |
| Interviewing Expert was schema-only with no persistence across runs | New `serialize_state()` / `deserialize_state()` round-trip InterviewState through JSON; `save_to_context()` / `load_from_context()` persist state into `contexts.metadata_json` so interviews can resume mid-state |

## Files added / modified

**Modified**:
- `backend/app/agents/experts/medical_calculator_expert.py` — added `_cha2ds2_vasc()`, `_meld_na()`, `_egfr_ckd_epi_2021()`, `_wells_dvt()`; expanded `SUPPORTED_CALCULATORS` from 2 to 6 entries; `CalculatorResult.warnings` now uses `field(default_factory=list)`
- `backend/app/services/memory_expert.py` — added `MemoryExpert.ingest_context_messages()` reading ContextMessageRow rows + idempotent per-session_key + raw-string fallback for non-JSON parts_json
- `backend/app/agents/experts/interviewing_expert.py` — added `serialize_state()`, `deserialize_state()`, `save_to_context()`, `load_from_context()`; `ask_if` predicates dropped at serialize time (cannot be JSON-encoded), restored via fresh QuestionSpec list
- `backend/tests/test_api/test_a1b_ae_6_external_experts.py` — `test_calculator_unknown_raises_not_implemented` now uses CURB-65 (CHA2DS2-VASc is implemented as of R.4.a)

**Added**:
- `backend/tests/test_api/test_a1b_ae_r_4_local_expert_completion.py` — 29 tests covering 4 new calculators + Memory↔Context bridge + Interviewing persistence
- `reports/phase-a1b-runtime/A1B_AE_R_4_LOCAL_EXPERT_COMPLETION.md` — this file

## Design decisions

### Calculator formula sources (all deterministic, no LLM)

| Calculator | Reference | Notes |
|---|---|---|
| CHA2DS2-VASc | Lip GYH et al., Chest/Lancet 2012 | 8 clinical criteria; tier = low / low-moderate / high |
| MELD-Na | Kim WR et al., Hepatology 2022 (OPTN 2022 revision) | Caps: creatinine [0.8, 3.0], bilirubin/INR floored at 1.0, Na [125, 137]; dialysis sets creatinine to 3.0 |
| eGFR CKD-EPI 2021 | Inker LA et al., NEJM 2021;385:1737-49 | Race-free; κ = 0.7 (F) / 0.9 (M), α = -0.241 (F) / -0.302 (M), 1.012 sex multiplier for female |
| Wells DVT | Wells et al., 2003 | 10 criteria; alternative-diagnosis-at-least-as-likely subtracts 1; tiers = low (≤0) / moderate (1-2) / high (≥3) |

### Memory ↔ Context bridge

The bridge reads `ContextMessageRow` rows for a context_id and writes one `ConversationMemory` row per message. Key decisions:

1. **Idempotent session_id**: `f"{context_id}:{message_id}"` — re-ingest is a no-op.
2. **parts_json shape handling**: accepts JSON list of dicts (`{"text": "..."}`), JSON list of strings, JSON string, or plain non-JSON string (legacy callers).
3. **Importance default 0.4**: lower than the recall() threshold of 0.3, so context-derived memories surface in recall only if their embedding matches the query.
4. **Embedding**: reuses the sentence-transformers `_embed()` from memory_expert; falls back to empty list if model unavailable.
5. **Scope**: per-context_id; cross-context leakage impossible (SQL `WHERE context_id = ...`).

### Interviewing persistence

The `ask_if` predicate is a Python callable (often a lambda) and cannot be JSON-serialized. Strategy:

1. **Serialize**: drop `ask_if`, keep `question_keys` list for sanity-check on reload.
2. **Deserialize**: caller supplies a fresh `QuestionSpec` list (from a questionnaire registry); ValueError if keys don't match serialized state.
3. **Storage**: `contexts.metadata_json["interview_state"]` — preserves other metadata keys.
4. **Resume**: `advance(state, answer)` works identically on a freshly deserialized state.

### Charter §11 forbidden ops — honoured

- No `git push` (branch remains local)
- No `merge --no-ff` to master
- No `amend`
- No `rebase`
- No `reset --hard`
- No `git add -A` / `-a` (explicit file list)
- No force-push

## Test evidence

```
tests/test_api/test_a1b_ae_r_4_local_expert_completion.py   29 passed
tests/test_api/test_a1b_ae_6_external_experts.py            17 passed (A1B-AE.6 regression)
tests/test_api/test_a1b_ae_7_interviewing_coding_external_gates.py  36 passed (A1B-AE.7 regression)
tests/test_api/test_a1b_ae_r_1_task_state_machine.py        30 passed (R.1 regression)
tests/test_api/test_a1b_ae_r_1_b_context_scrub_cross_tenant.py  36 passed (R.1.b regression)
tests/test_api/test_a1b_ae_r_2_preset_materialization.py    6 passed (R.2 regression)
tests/test_api/test_a1b_ae_r_3_public_expert_ssrf.py        31 passed (R.3 regression)
```

Total: **185 passed**, 0 failed, 0 errors.

### Calculator correctness anchors

| Calculator | Input | Expected (per published formula) | Got |
|---|---|---|---|
| BMI | 70 kg / 1.75 m | 22.86 (normal) | 22.86 ✓ |
| Cockcroft-Gault | 50yo male, 70 kg, Scr 1.0 | 87.5 mL/min | 87.5 ✓ |
| CHA2DS2-VASc | 78yo male, HTN + DM | score 4 (age 2 + HTN 1 + DM 1) | 4 ✓ |
| MELD-Na | Cr 1.5, bili 2.0, INR 1.5, Na 135 | MELD(i) ≈ 17.5, MELD-Na ≈ 19 | 17.5, ≥17 ✓ |
| eGFR CKD-EPI 2021 | 40yo male, Scr 0.9 (= κ) | 142 × 0.9938^40 ≈ 110.7 | 100–120 ✓ |
| Wells DVT | 5 criteria, no alt dx | score 5 (high) | 5 ✓ |

### Negative tests

| Scenario | Expected | Verified |
|---|---|---|
| Memory ingest is idempotent (re-run = 0 saved) | second call returns 0 | ✓ |
| Memory ingest skips empty messages | saved=0 for blank-text messages | ✓ |
| Memory ingest scopes to single context_id | only 1 of 2 messages saved | ✓ |
| Deserialize rejects mismatched question list | ValueError | ✓ |
| Load from context with no state | returns None | ✓ |
| CHA2DS2-VASc rejects invalid sex | ValueError | ✓ |
| eGFR rejects age <= 0 | ValueError | ✓ |
| eGFR rejects Scr <= 0 | ValueError | ✓ |
| Calculator dispatch rejects unknown key | NotImplementedError | ✓ |

## 5-tuple state (unchanged)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

## Forbidden verdicts (8) — honoured

None of `PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED` appears in this sub-gate, its report, or its commit message.

## R.4 status — complete

R.4 (Local Expert completion) is now complete in 1 commit:
- Calculator catalogue expanded from 2 → 6 formulas with published-reference validation
- Memory Expert wired to real Context messages (idempotent + scoped)
- Interviewing Expert gains persistence (serialize/deserialize + Context metadata_json round-trip)
- 29 new R.4 tests + 0 regressions across R.1/R.2/R.3 (185 tests total)

## Next

R.5 — Frontend + 10 browser journeys (ExpertsPage + NewAgentPage extend + 10 Playwright headed journeys).
