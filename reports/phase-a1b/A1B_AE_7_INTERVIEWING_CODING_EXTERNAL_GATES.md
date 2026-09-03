# A1B-AE.7 — Interviewing + Coding wrapper + external-Expert gates (filed, not verified)

**Sub-gate**: A1B-AE.7 (Commit 8 of 12)
**Branch**: `phase-a1b/agent-expert-clean-room` (local-only)
**Worktree**: `E:/Corti4C-agent-expert`
**Baseline HEAD**: `3d50b11` (inherited from A1A Gate 4R-I.11)
**Prior commit**: `cb6be91` (A1B-AE.6)

## Scope

Complete the remaining 5 Corti public §3.2 Expert Registry entries plus the
centralized external-Expert gate. After A1B-AE.7 the iCoDer Expert Registry
covers all 9 Corti public keys:

| Corti §3.2 key | canonical_key | Landed | Corti alignment |
|---|---|---|---|
| 1/9 | `memory` | A1B-AE.5 | CORTI_REFERENCE (lexical-only) |
| 2/9 | `coding-expert` | **A1B-AE.7** | CORTI_ALIGNED (delegates to medical-coding-agent) |
| 3/9 | `medical-calculator` | A1B-AE.6 | CORTI_ADAPTED (BMI + Cockcroft-Gault subset) |
| 4/9 | `drugbank` | **A1B-AE.7** | CORTI_REFERENCE (licence-required stub) |
| 5/9 | `posos` | **A1B-AE.7** | CORTI_REFERENCE (licence-required stub) |
| 6/9 | `web-search` | **A1B-AE.7** | CORTI_REFERENCE (policy-gated stub) |
| 7/9 | `pubmed` | A1B-AE.6 | CORTI_REFERENCE (offline stub) |
| 8/9 | `clinical-trials` | A1B-AE.6 | CORTI_REFERENCE (offline stub) |
| 9/9 | `interviewing` | **A1B-AE.7** | CORTI_ALIGNED (schema-driven interviewer) |

## §1 Coding Expert wrapper — `coding_expert.py`

**Corti alignment**: `CORTI_ALIGNED`. iCoDer's existing `icoder/medical-coding-agent@2.0.0`
Pack (Phase 5 Track C/D) matches Corti public §3.2 key 2's contract surface
(diagnosis + procedure code assignment from notes, evidence-first,
human-review-required). A1B-AE.7 lands a thin Expert wrapper that:

- Captures delegation metadata (`delegates_to`, `runtime_mode`, `output_contract`).
- Surfaces a Pack output verbatim when the caller supplies one (`extracted_from_pack=True`).
- Returns an empty pack_output with a "caller must invoke the Pack" notice otherwise.

The wrapper does NOT duplicate clinical logic. MedCodER 5-stage pipeline
stays inside `icoder_runtime.providers.medical_coding`.

Red lines preserved (from Pack agent_pack.json):
- `human_review_required = True`
- `phi_redacted = True`
- `production_writeback_blocked = True`

## §2 DrugBank stub — `drugbank_expert.py`

**Corti alignment**: `CORTI_REFERENCE` (no DrugBank licence). Licence-required.
`DRUGBANK_LLM_FALLBACK_ALLOWED = False` — explicit patient-safety red line:
drug-interaction data must come from a licensed source; LLM-guessed interactions
are forbidden.

Stub returns `live_lookup_performed=False` + empty result + STUB notice. Caller
MUST check the flag before clinical use.

## §3 POSOS stub — `posos_expert.py`

**Corti alignment**: `CORTI_REFERENCE` (no POSOS licence). Same red line as
DrugBank: prescribing guidance requires a licensed source, no LLM fallback.

## §4 Web Search Expert — `web_search_expert.py`

**Corti alignment**: `CORTI_REFERENCE`. Default policy is `DISABLED_BY_DEFAULT`
(live web egress is a PHI-leak risk; not needed for core coding/CDI/DRG-DIP flows).

3-value policy gate:
- `DISABLED_BY_DEFAULT` — default, no live call.
- `OPT_IN_PER_PROVIDER` — one of tenant/provider has opted in.
- `ENABLED_FOR_TENANT` — both tenant + provider opted in.

A1B-AE.7 NEVER performs a live web call, even when policy is `ENABLED_FOR_TENANT`.
The policy field tells the caller what *would* be allowed under the central gate.

## §5 Interviewing Expert — `interviewing_expert.py`

**Corti alignment**: `CORTI_ALIGNED` (schema-driven loop matches Corti public
§3.2 key 9 contract: present question → collect answer → branch → emit transcript).

Components:
- `QuestionSpec` — key, prompt, kind (text/number/choice/boolean), optional
  `ask_if` predicate for branching, required flag.
- `InterviewState` — questionnaire key, ordered questions, answers map, cursor.
- `start_interview(questions)` — validates non-empty, returns state.
- `advance(state, answer=None)` — prime or step. When `answer` is provided,
  records it at the current cursor, increments cursor, then walks forward
  skipping questions whose `ask_if` returns False (or unmet). Returns the next
  askable question or `complete=True`.
- `record_answer(state, key, value)` — out-of-band write for callers driving
  their own loop.
- `transcript(state)` — deterministic `{questionnaire_key, answers,
  question_count, answered_count}`.

Out of scope: LLM-driven adaptive prompting, multi-language scripting, audio
STT. These are A1B-AE.9 or later-phase candidates.

## §6 External-Expert Gate — `external_expert_gate.py`

Centralizes policy for the 5 external-touching Experts
(`pubmed`, `clinical-trials`, `drugbank`, `posos`, `web-search`). Individual
Experts stay thin; the gate is the single source of truth.

Resolution (first failure wins):
1. Expert not in `GATED_EXPERTS` → `OK` (gate doesn't apply).
2. Licence-required Experts (`drugbank`, `posos`) without `licence_tokens` → `LICENCE_REQUIRED`.
3. Any external Expert with `egress_enabled=False` → `EGRESS_DISABLED` (Charter §6 default).
4. Region not in `CN/EU/US` → `REGION_BLOCKED`.
5. `web-search` without both `provider_opt_in` and `tenant_opt_in` → `PROVIDER_OPT_IN_MISSING`.
6. All checks pass → `OK`.

Return value: `GateDecision(expert_key, permitted, reason, notes)`. Even when
`permitted=True`, the caller MUST still consult the Expert's own
`live_*_performed` flag — the gate does not perform the call, it only rules
on what would be allowed.

## Provenance (Charter Amendment 1 §7)

| Artifact | Tier | Source |
|---|---|---|
| `coding_expert.py` | `ICODER_INTERNAL` | Delegation descriptor; canonical_key aligned to Corti §3.2 key 2 |
| `drugbank_expert.py` | `CLEAN_ROOM_PUBLIC` | Corti §3.2 key 4 public description; no live API; no Console RE |
| `posos_expert.py` | `CLEAN_ROOM_PUBLIC` | Corti §3.2 key 5 public description; no live API; no Console RE |
| `web_search_expert.py` | `CLEAN_ROOM_PUBLIC` | Corti §3.2 key 6 public description; no live API; no Console RE |
| `interviewing_expert.py` | `CLEAN_ROOM_PUBLIC` + `ICODER_INTERNAL` | Corti §3.2 key 9 contract surface; iCoDer schema-driven loop implementation |
| `external_expert_gate.py` | `ICODER_INTERNAL` | Centralized policy service (Charter §6) |
| Test file | `ICODER_INTERNAL` | Deterministic assertions |
| Report + INDEX update | `ICODER_INTERNAL` | This document |

## Test coverage — `tests/test_api/test_a1b_ae_7_interviewing_coding_external_gates.py`

**36 tests in 1.36s. All PASS.**

| Section | Tests | Coverage |
|---|---|---|
| §1 Coding wrapper | 4 | constants; delegate w/o pack output; surfaces pack output verbatim; runtime_mode passthrough |
| §2 DrugBank | 4 | constants + LLM-fallback red line; stub empty+flag; empty query; red-line marker |
| §3 POSOS | 3 | constants; stub empty+flag; empty query |
| §4 Web Search | 6 | constants; default-disabled; partial opt-in; dual opt-in; explicit-policy-wins; invalid policy raises; still-empty-when-enabled |
| §5 Interviewing | 5 | constants; requires questions; linear progression; branching skip; transcript |
| §6 External-Expert Gate | 12 | constants; non-gated passthrough; drugbank/posos licence-required; drugbank egress-disabled; drugbank region-blocked; drugbank all-conditions-met; pubmed egress; pubmed permits; web-search dual-opt-in required + met; is_gated helper |
| §7 Charter | 1 | forbidden verdicts preserved |

**§7 forbidden verdicts preserved**: 8 forbidden ∩ 1 allowed = ∅.

Combined regression A1B-AE.3..7: **106 tests PASS in 3.06s**.

## Explicit parity gaps (recorded as tech debt, not closure)

| Corti public capability | iCoDer A1B-AE.7 scope | Gap |
|---|---|---|
| DrugBank live lookup | Stub | Requires commercial licence; no LLM fallback (red line) |
| POSOS live lookup | Stub | Same — requires commercial licence |
| Web Search live lookup | Stub + 3-value policy | Disabled by default; future privacy-preserving provider integration |
| Interviewing adaptive LLM prompts | Schema-driven loop only | LLM-driven branching deferred |

These are A1B-AE.9 (tech-debt liquidation) candidates or later-phase work.
They are NOT closure claims.

## Acceptance

```
A1B-AE.7_PARTIAL = FILED
```

- Expert Registry entries now cover all 9 Corti public §3.2 keys.
- Centralized external-Expert gate enforces Charter §6 egress policy.
- 36 new tests PASS; 106 combined A1B-AE.3..7 tests PASS in 3.06s.
- No forbidden verdict used.
- All work in `phase-a1b/agent-expert-clean-room` branch (local-only, not pushed, not merged).

## Forbidden verdicts honoured

```
PRODUCTION_READY                              ∉ filed verdicts
FULLY_VERIFIED                                ∉ filed verdicts
PHI_BOUNDED                                   ∉ filed verdicts
CORTI_PARITY_VERIFIED                         ∉ filed verdicts
PASS_A1A_GATE4_FINAL                          ∉ filed verdicts
READY_FOR_HOSPITAL_DEPLOYMENT                 ∉ filed verdicts
CLINICAL_GRADE_VERIFIED                       ∉ filed verdicts
CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED      ∉ filed verdicts
```

## Verdict

```
PARTIAL_A1B_AE_7_INTERVIEWING_CODING_WRAPPER_EXTERNAL_EXPERT_GATES_FILED
```

Next: A1B-AE.8 — iCoder Preset Agents (5 clean-room agents).
