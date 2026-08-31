# Phase A0.1 Gate 5 — Product Maturity V2

> Multi-axis per-scenario maturity. Replaces Phase A0 v1's single-L
> scale with five orthogonal axes so that "code runs" no longer
> implies "workflow closed" or "quality benchmarked".

Spec reference: Phase A0.1 §三 Gate 5.

---

## §1. Why V2 exists

Phase A0 v1 product_maturity.json assigned each of 16 China scenarios a
**single** maturity level from L1 to L11. Two problems with that:

1. **CN-01 Medical Coding was labeled L8_QUALITY_BENCHMARKED**, but
   A0-P0-013 in the same audit's issue ledger says
   *"Only F1@1=0.15 on 5-case smoke; no 201-case baseline"*. The two
   Phase A0 deliverables contradict each other. The L8 number was
   self-attested by the maturity author and is not machine-derivable
   from any test fixture.

2. **Single-axis labels hide orthogonal truths.** CN-02 CDI at L4
   (runtime reachable) is correct on the code axis, but the *workflow*
   is OPEN_LOOP (443 queries / 0 clinician responses per A0-P0-007).
   A single L-number cannot express "code runs but workflow not closed".

V2 introduces 5 orthogonal axes so each scenario carries an honest
profile rather than a single rosy number.

## §2. Multi-axis model

| Axis | Values | What it captures |
|------|--------|------------------|
| `code_maturity` | L1..L11 (same as v1) | Does the code exist / is it wired / is it reachable / browser-verified / etc. |
| `quality_evidence` | NONE / SMOKE_ONLY / FORMAL_BENCHMARK / CLINICAL_AUDIT | Is there real quality evidence (F1 report, clinician sign-off) or just a smoke run? |
| `partner_validation` | NONE / SYNTHETIC_E2E / REAL_PARTNER / PRODUCTION_PARTNER | Has any real partner exercised this, or only the internal reference app with synthetic data? |
| `regulatory` | NONE / SELF_ATTESTED / CERTIFIED | Is there a real cert (等保2.0 三级, GB/T 35273) or just a claim in CLAUDE.md? |
| `workflow_closure` | N_A / OPEN_LOOP / CLOSED_LOOP | Does the workflow produce an effect on the downstream system (e.g., writeback)? |

Two scenarios can share a code_maturity level but differ on every other
axis. That is the point.

## §3. CN-01 Medical Coding — L8 → SMOKE_ONLY regrade

| Axis | v1 claim | v2 correction | Reason |
|------|----------|---------------|--------|
| code_maturity | (implicit L8) | L4_RUNTIME_REACHABLE | HybridCodingAdapter runs end-to-end with real DeepSeek; L5 not met because primary path integration test is a 5-case smoke |
| quality_evidence | (implicit L8 = "FORMAL_BENCHMARK") | **SMOKE_ONLY** | A0-P0-013 in the same Phase A0 ledger states "no 201-case baseline". v1 L8 was self-attested; v2 treats the issue ledger (machine-derivable from fixtures) as authoritative |
| partner_validation | (implicit) | SYNTHETIC_E2E | Phase 7 Gate 12 ran a synthetic fracture case; real partner = 0 |
| regulatory | (implicit) | NONE | No 等保2.0 三级, no NMPA classification |
| workflow_closure | (implicit) | OPEN_LOOP | Output produced; no clinician sign-off; no HIS writeback |

Severity of the v1 overclaim: **P0-C (clinical safety)**. Calling
Medical Coding L8_QUALITY_BENCHMARKED when the issue ledger in the
same audit says otherwise is exactly the kind of self-attestation
inflation that triggers the forbidden verdicts list.

## §4. CN-02 CDI — open loop made explicit

| Axis | v1 claim | v2 value | Reason |
|------|----------|----------|--------|
| code_maturity | L4_RUNTIME_REACHABLE | L4_RUNTIME_REACHABLE | Confirmed; 12-state lifecycle runs |
| quality_evidence | (unstated) | SMOKE_ONLY | Track H 40-case Corti calibration; no formal benchmark |
| partner_validation | (unstated) | NONE | No partner has run CDI in any form |
| regulatory | (unstated) | NONE | No certification, no clinical audit |
| workflow_closure | (unstated) | **OPEN_LOOP** | A0-P0-007: 443 queries emitted / 0 clinician responses / 0 document revisions |

v1 was correct on the code axis but did not loudly enough mark the
workflow as OPEN_LOOP. v2 makes it an explicit axis value so it cannot
be missed.

## §5. V2 distribution (machine-derived)

```
total_scenarios = 16

code_maturity_distribution:
  L1_ASSET_PRESENT           4   (CN-04/05/06/10)
  L2_CONTRACT_PRESENT        1   (CN-09 billing)
  L3_CODE_PRESENT            4   (CN-03/08/12/16)
  L4_RUNTIME_REACHABLE       4   (CN-01/02/07/15)
  L5_INTEGRATION_VERIFIED    0
  L6_BROWSER_VERIFIED        3   (CN-11/13/14)
  L7_WORKFLOW_CLOSED         0
  L8_QUALITY_BENCHMARKED     0   ← v1 had 1 here (CN-01); v2 regrades
  L9-L11                     0

quality_evidence_distribution:
  NONE                       13
  SMOKE_ONLY                  3   (CN-01/02/07)
  FORMAL_BENCHMARK            0
  CLINICAL_AUDIT              0

partner_validation_distribution:
  NONE                       11
  SYNTHETIC_E2E               3   (CN-01/11/13)
  REAL_PARTNER                0
  PRODUCTION_PARTNER          0

regulatory_distribution:
  NONE                       16   ← 100% of scenarios
  SELF_ATTESTED               0
  CERTIFIED                   0

workflow_closure_distribution:
  N_A                        10   (scenarios where workflow closure is not meaningful)
  OPEN_LOOP                   6   (CN-01/02/07/11/13/14)
  CLOSED_LOOP                 0

scenarios_at_L7_plus                  : 0
scenarios_with_quality_benchmark     : 0
scenarios_with_real_partner          : 0
```

The headline: **zero scenarios have formal benchmark evidence; zero
scenarios have a real partner; 100% lack regulatory certification;
zero workflows are closed-loop**.

## §6. Readiness tracks v2

| Track | Achieved | Blockers (if not) |
|-------|----------|-------------------|
| INTERNAL_DEMO | ✅ | — (CN-01/11/13/14 with synthetic data + real DeepSeek) |
| CUSTOMER_DEMO | ❌ | A0-P0-005 Corti redirects visible; A0-P0-015 strategic incoherence; A0-P0-006 cost=0 visible |
| PARTNER_TECHNICAL_STAGING | ❌ | A0-P0-009 npm unpublished; A0-P0-021 supply chain unsigned |
| HOSPITAL_RESEARCH_SANDBOX | ❌ | A0-P0-001 no cert; A0-P0-002 no legal docs; A0-P0-016 no encryption; A0-P0-017 PHI export-only |
| HOSPITAL_CLINICAL_WORKFLOW_PILOT | ❌ | All P0-S + P0-C + P0-D; CN-01 SMOKE_ONLY + OPEN_LOOP cannot enter clinical workflow |
| COMMERCIAL_GA | ❌ | All P0; A0-P0-004 billing theater; A0-P0-009 npm unpublished |

## §7. Hard Checkpoint — Product Maturity (provisional)

| Sub-check | Status |
|-----------|--------|
| MA-1: every scenario has all 5 axis values | ✅ 16/16 |
| MA-2: no scenario claims FORMAL_BENCHMARK without a benchmark report on file | ✅ 0/0 (zero claims; v1 CN-01 regrade removes the only false claim) |
| MA-3: no scenario claims CLOSED_LOOP without writeback integration | ✅ 0/0 |
| MA-4: no scenario claims CERTIFIED regulatory status | ✅ 0/0 (none claimed) |
| MA-5: v1 CN-01 L8 regraded | ✅ downgraded to code=L4 / quality=SMOKE_ONLY |
| MA-6: CN-02 CDI workflow_open_loop explicit | ✅ |
| MA-7: readiness track blockers reference real issue IDs | ✅ all blockers cross-reference A0-P0-* |
| MA-8: code_maturity_distribution sums to 16 | ✅ 4+1+4+4+0+3+0+0+0+0+0 = 16 |

**Hard Checkpoint MA: ✅ PASS (8/8 sub-checks) provisional — Gate 8 validator must machine-verify before final ratification.**

## §8. Findings raised in Gate 5

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G5-001** | P0-C | Phase A0 v1 product_maturity labeled CN-01 Medical Coding `L8_QUALITY_BENCHMARKED`. The same Phase A0 issue ledger (A0-P0-013) explicitly states "no 201-case baseline" and "F1@1=0.15 on 5-case smoke". v1 L8 was self-attested; Phase A1 must produce a real 201-case F1 report before any L8+ claim can return. |
| **A0.1-G5-002** | P0-C | Phase A0 v1 did not surface CN-02 CDI's `workflow_closure: OPEN_LOOP` loudly enough. 443 queries emitted / 0 clinician responses is not a closed loop. Phase A1 must capture at least one clinician response and one document revision before any "CDI loop closed" claim. |
| **A0.1-G5-003** | P1 | Phase A0 v1 used a single-axis L1-L11 scale, which conflates "code runs" with "quality benchmarked" with "workflow closed". v2 splits into 5 orthogonal axes. |
| **A0.1-G5-004** | P2 | 16/16 scenarios report `regulatory: NONE`. The 等保2.0 三级 mention in CLAUDE.md is not a certification. Phase A1 must either pursue certification or stop mentioning 等保 in marketing-adjacent docs. |
| **A0.1-G5-005** | P2 | 13/16 scenarios report `quality_evidence: NONE`. The audit cannot opine on quality for scenarios that have no smoke, no benchmark, and no audit. Phase A1 must produce at least SMOKE_ONLY evidence for every L4+ scenario. |

## §9. Gate 5 verdict

```
PHASE_A0_1_GATE_5_PRODUCT_MATURITY_V2_DERIVED
16_SCENARIOS (5-axis profile each)
0_SCENARIOS_AT_L7_PLUS (was 1 in v1 — CN-01 regraded)
0_SCENARIOS_WITH_FORMAL_BENCHMARK
0_SCENARIOS_WITH_REAL_PARTNER
0_SCENARIOS_WITH_CLOSED_LOOP
6_SCENARIOS_OPEN_LOOP (made explicit)
16_SCENARIOS_REGULATORY_NONE
CN_01_MEDICAL_CODING_L8_REVERTED (v1 self-attested; v2 = code L4 + SMOKE_ONLY)
CN_02_CDI_OPEN_LOOP_EXPLICIT
HARD_CHECKPOINT_MA_PROVISIONAL_PASS (8/8)
```

### Phase A0 v1 product_maturity NOT modified (preserved as audit trail).

End of Gate 5. Proceeding to Gate 6 — Gate 13A Security Evidence Regrading.
