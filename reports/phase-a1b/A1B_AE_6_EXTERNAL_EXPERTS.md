# A1B-AE.6 — Calculator + PubMed + Clinical Trials Experts (filed, not verified)

**Sub-gate**: A1B-AE.6 (Commit 7 of 12)
**Branch**: `phase-a1b/agent-expert-clean-room` (local-only)
**Worktree**: `E:/Corti4C-agent-expert`
**Baseline HEAD**: `3d50b11` (inherited from A1A Gate 4R-I.11)
**Prior commit**: `b253388` (A1B-AE.5)

## Scope

Land Expert Registry entries + deterministic offline implementations for the
three Corti public §3.2 external/reference Experts:

| # | Corti §3.2 key | canonical_key | Corti alignment | A1B-AE.6 scope |
|---|---|---|---|---|
| 3 | Medical Calculator Expert | `medical-calculator` | `CORTI_ADAPTED` | BMI + Cockcroft-Gault (2 of N calculators) |
| 7 | PubMed Expert | `pubmed` | `CORTI_REFERENCE` | Offline stub (no live E-utilities call) |
| 8 | Clinical Trials Expert | `clinical-trials` | `CORTI_REFERENCE` | Offline stub (no clinicaltrials.gov call) |

## Provenance (Charter Amendment 1 §7)

| Artifact | Tier | Source |
|---|---|---|
| `medical_calculator_expert.py` — BMI + Cockcroft-Gault | `ICODER_INTERNAL` | iCoDer clinical formulas; canonical_key aligned to Corti §3.2 key 3 |
| `pubmed_expert.py` — offline stub | `CLEAN_ROOM_PUBLIC` | Corti §3.2 key 7 public description only; no live API call |
| `clinical_trials_expert.py` — offline stub | `CLEAN_ROOM_PUBLIC` | Corti §3.2 key 8 public description only; no live API call |
| Test file | `ICODER_INTERNAL` | Deterministic offline assertions |

No Corti Console reverse-engineering was used for the stub bodies. The
canonical_keys (3/9, 7/9, 8/9) are Corti public §3.2 surface; the implementations
are either iCoDer-side formulas (Calculator) or explicit no-egress stubs
(PubMed, Clinical Trials).

## Implementation

### §1 Medical Calculator Expert — `app/agents/experts/medical_calculator_expert.py`

**Corti alignment**: `CORTI_ADAPTED` (iCoDer ships a subset of Corti's calculator catalogue).

**Implemented calculators** (SUPPORTED_CALCULATORS):
- `bmi` — BMI + category (underweight / normal / overweight / obese)
- `cockcroft-gault` (aliases: `cockcroft_gault`, `crcl`) — Cockcroft-Gault creatinine clearance (mL/min)

**Dispatch behaviour**:
- `calculate("bmi", weight_kg=70, height_m=1.75)` → BMI 22.86, category "normal"
- `calculate("cockcroft-gault", age_years=50, weight_kg=70, serum_creatinine_mg_dl=1.0, sex="male")` → CrCl 87.5 mL/min
- Females multiply by 0.85 (per Cockcroft-Gault 1976)
- Warnings emitted when CrCl < 30 (renal dose adjustment) or age ≥ 65 (frailty-adjusted dosing)

**Explicit boundary**: unsupported calculator keys (e.g. `CHA2DS2-VASc`, `MELD-Na`, `CURB-65`) raise `NotImplementedError`, so callers know the boundary explicitly rather than receiving a silent fallback.

### §2 PubMed Expert — `app/agents/experts/pubmed_expert.py`

**Corti alignment**: `CORTI_REFERENCE` (Expert Registry entry exists; live PubMed E-utilities integration is deferred).

**Stub behaviour**:
- `search("diabetes type 2 metformin")` → `PubMedResult(articles=[], total=0, live_search_performed=False, notes="STUB: …")`
- Empty query → `notes="empty query"`

**Why no live call**:
1. No API key configured in dev/CI.
2. Live external API egress requires Charter §6 region-routing compliance (not yet wired).
3. A1B-AE.6 scope is Expert Registry entry only.

**Caller contract**: caller MUST check `live_search_performed` before treating results as actionable. A `False` flag means "treat as empty for clinical decision-making."

### §3 Clinical Trials Expert — `app/agents/experts/clinical_trials_expert.py`

**Corti alignment**: `CORTI_REFERENCE` (same rationale as PubMed).

**Stub behaviour**: identical offline-empty pattern with `live_search_performed=False`.

**Parameters accepted but ignored** (forward-compatibility for when live integration lands): `condition`, `location`, `max_results`.

## Test coverage — `tests/test_api/test_a1b_ae_6_external_experts.py`

**17 tests in 1.32s. All PASS.**

| Section | Tests | Coverage |
|---|---|---|
| §1 Calculator | 9 | constants; BMI normal/categories/non-positive rejection; Cockcroft-Gault male/female-multiplier/renal-warning/age-warning; unknown NotImplementedError; invalid sex ValueError |
| §2 PubMed | 3 | canonical_key; stub returns empty + STUB flag; empty query |
| §3 Clinical Trials | 3 | canonical_key; stub returns empty + STUB flag; empty query |
| §4 Charter | 1 | forbidden verdicts preserved (8 forbidden ∩ allowed = ∅) |

**§4 forbidden verdicts preserved** (Charter Amendment 1 §7.4): the `forbidden` set (PRODUCTION_READY, FULLY_VERIFIED, PHI_BOUNDED, CORTI_PARITY_VERIFIED, PASS_A1A_GATE4_FINAL, READY_FOR_HOSPITAL_DEPLOYMENT, CLINICAL_GRADE_VERIFIED, CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED) remains disjoint from the only permitted final verdict (`PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED`).

## Explicit parity gaps (recorded as tech debt, not closure)

| Corti public capability | iCoDer A1B-AE.6 scope | Gap |
|---|---|---|
| Medical Calculator (CHA2DS2-VASc, MELD-Na, CURB-65, …) | BMI + Cockcroft-Gault only | Calculator catalogue subset → `CORTI_ADAPTED` (not `CORTI_ALIGNED`) |
| PubMed live search | Stub returns empty | Live E-utilities integration deferred (Charter §6 egress gating needed first) |
| Clinical Trials live search | Stub returns empty | clinicaltrials.gov API v2 integration deferred (same egress gate) |

These gaps are candidates for A1B-AE.9 (tech-debt liquidation) or later phases. They are NOT closure claims.

## Acceptance

```
A1B-AE.6_PARTIAL = FILED
```

- Expert Registry entries exist for 3 additional Corti §3.2 keys (3, 7, 8).
- iCoDer's canonical Expert Registry (A1B-AE.2 catalog) now covers 4 of 9 Corti public Expert keys (memory from A1B-AE.5; calculator + pubmed + clinical-trials here).
- 17 new tests PASS; 70 combined A1B-AE.3..6 tests PASS in 3.07s.
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
PARTIAL_A1B_AE_6_CALCULATOR_PUBMED_CLINICAL_TRIALS_EXPERTS_FILED
```

Next: A1B-AE.7 — Interviewing Expert + Coding wrapper + external-Expert gates.
