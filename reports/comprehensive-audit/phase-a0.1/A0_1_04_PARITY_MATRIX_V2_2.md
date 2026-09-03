# Phase A0.1 Gate 4 — Parity Matrix V2.2

> Read-only repair of the Phase A0 v2.1 parity matrix. Produces
> `parity_matrix_v2_2.json` (machine-derived counts) and a Markdown
> summary generated from the JSON. Does NOT modify the v2.1 file.

Spec reference: Phase A0.1 §三 Gate 4.

---

## §1. Why V2.2 exists

Phase A0 v2.1 parity matrix shipped with three consistency defects
(per Gate 0 Finding 3):

1. **Summary count wrong.** `summary.total_dimensions = 51` but the
   `dimensions` array actually held **59** entries — undercount by 8.
2. **Status sum wrong.** `summary.by_status` summed to **55**, not 51
   and not 59. Neither total matched the array.
3. **Typo in field name.** Dimension A-05 had `icorer_evidence_grade`
   instead of `icoder_evidence_grade` — the iCoDer evidence grade was
   silently dropped from any code that read `icoder_evidence_grade`.

A fourth, more substantive defect:

4. **Advantage claims without threshold.** v2.1 listed 11
   `ICODER_ADVANTAGE` dimensions, but 9 of them sat at E2 or E3 —
   code-observed or unit-verified only. Calling those "advantages
   over Corti" without integration evidence (E4+) inflates the
   competitive picture. Phase A0.1 enforces explicit thresholds.

## §2. Evidence-grade thresholds for ADVANTAGE claims

Phase A0.1 §三 Gate 4 spec:

| Claim bucket | Minimum evidence grade |
|--------------|------------------------|
| Runtime advantage | **E4** (integration-verified) |
| Security advantage | **E7** (security-negative-verified) |
| Clinical advantage | **formal benchmark OR clinical audit on file** (in addition to E2 code-observed) |
| UX / Product advantage | E5 (browser-verified) — unchanged |
| Tool-catalog count advantage | E2 (code-observed) — unchanged; counting MCP handlers is not a runtime claim |

Rationale: an unverified advantage is not an advantage. Phase A0 v2.1
allowed E2/E3 entries to claim ADVANTAGE; v2.2 enforces the threshold
explicitly and regrades the 9 failing entries.

## §3. Regrade log — 9 entries downgraded

| ID | Class | Bucket | Old status | New status | Current grade | Threshold | Why |
|----|-------|--------|------------|------------|---------------|-----------|-----|
| A-09 | Foundation | Runtime | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E3 | E4 | E3 unit-verified only, not integration-verified |
| A-10 | Foundation | Runtime | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E3 | E4 | E3 unit-verified; also RunHistory table empty per A0-P0-008 |
| C-12 | Expert Surface | Clinical | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E2 | Benchmark | No benchmark on file; E2 code-observed only |
| C-13 | Expert Surface | Clinical | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E2 | Benchmark | No benchmark; DRG-DIP rules reserved not exercised |
| G-01 | Observability | Runtime | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E2 | E4 | RUNTRACE_STORE=memory per A0-P0-008; table empty |
| G-02 | Observability | Runtime | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E3 | E4 | E3 unit-verified only |
| G-03 | Observability | Runtime | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E3 | E4 | 235/240 rows NULL organization_id per A0-P0-012 |
| G-04 | Observability | Runtime | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E2 | E4 | E2 code-observed only |
| G-05 | Observability | Runtime | ICODER_ADVANTAGE | EVIDENCE_INSUFFICIENT | E2 | E4 | E2 code-observed only |

### Surviving ICODER_ADVANTAGE entries (2)

| ID | Class | Grade | Why it survives |
|----|-------|-------|-----------------|
| B-10 | Agent Surface | E5 | UX/Product advantage; browser-verified badge taxonomy meets E5 threshold |
| D-04 | Tool/MCP | E2 | Tool-catalog count (MCP handler count); threshold is E2 — counting handlers is not a runtime claim |

## §4. Field name typo fix

Dimension A-05 (Memory / RAG-like long-term) had `icorer_evidence_grade`
instead of `icoder_evidence_grade`. Any validator reading
`dimensions[*].icoder_evidence_grade` would silently default to None
for A-05. v2.2 fixes the field name and records the correction in a
`v2_2_typo_fix` sibling field for audit trail.

## §5. V2.2 summary (machine-derived)

Re-derived from the v2.2 `dimensions` array:

```
total_dimensions         = 59   (matches array length)
by_status sum            = 59   (matches total_dimensions)

by_status:
  CORTI_ADVANTAGE         17
  EVIDENCE_INSUFFICIENT   14   (was 5 in v2.1; +9 downgraded)
  PARITY                   9
  PARTIAL_PARITY           6   (was 7 in v2.1; v2.1 miscounted)
  NOT_IMPLEMENTED          4
  OUT_OF_SCOPE             3   (was 4 in v2.1; v2.1 miscounted)
  DIFFERENT_BY_DESIGN      3
  ICODER_ADVANTAGE         2   (was 11 in v2.1; -9 downgraded)
  ICODER_TECH_DEBT         1

by_evidence_grade_icoder:
  E0: 17   E1:  3   E2: 29   E3:  4   E4: 0
  E5:  6   E6:  0   E7:  0   E8:  0

by_evidence_grade_corti:
  E0: 16   E1: 22   E2:  0   E3:  0   E4: 0
  E5: 21   E6:  0   E7:  0   E8:  0
```

The asymmetry is the story: iCoDer has lots of E2 (code-observed) but
zero E4+ (integration-verified); Corti has 21 E5 (browser-verified in
their console). This is why so many v2.1 "advantage" claims fail
the v2.2 threshold — iCoDer simply has not produced integration evidence
for them yet.

## §6. What V2.2 does NOT report (inherited from v2.1)

- **No "favorable %" composite bucket.** Mixing PARITY + PARTIAL_PARITY
  + ICODER_ADVANTAGE into one number was the Pre-A0 sin (59%/77%); v2.1
  retired the practice; v2.2 inherits.
- **No "CN-scoped %" composite bucket.** Same reason.
- **No v1→v2 swing math.** Denominator changed between Pre-A0 and
  Phase A0 (30 → 59 dimensions); swing percentages are not meaningful.

## §7. Hard Checkpoint — Parity Matrix (provisional)

| Sub-check | Status |
|-----------|--------|
| PM-1: summary.total_dimensions equals len(dimensions) | ✅ 59 = 59 |
| PM-2: summary.by_status sums to total_dimensions | ✅ 59 = 59 |
| PM-3: every dimension has parity_status field | ✅ 59/59 |
| PM-4: every dimension has icoder_evidence_grade field (typo-free) | ✅ 59/59 (A-05 fixed) |
| PM-5: every ICODER_ADVANTAGE entry meets evidence threshold | ✅ 2/2 (B-10 E5, D-04 E2 catalog) |
| PM-6: regrade log covers every downgrade | ✅ 9/9 |
| PM-7: by_evidence_grade_icoder sums to total_dimensions | ✅ 17+3+29+4+0+6 = 59 |
| PM-8: by_evidence_grade_corti sums to total_dimensions | ✅ 16+22+21 = 59 |

**Hard Checkpoint PM: ✅ PASS (8/8 sub-checks) provisional — Gate 8 validator must machine-verify before final ratification.**

## §8. Findings raised in Gate 4

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G4-001** | P1 | Phase A0 v2.1 parity matrix `summary.total_dimensions = 51` did not match the `dimensions` array (actual: 59). v2.1 author hand-wrote the summary instead of deriving it. v2.2 retires the 51 figure. |
| **A0.1-G4-002** | P1 | Phase A0 v2.1 marked 9 dimensions as ICODER_ADVANTAGE without meeting any evidence-grade threshold. 7 of those dimensions (G-01 through G-05, A-09, A-10) are now downgraded to EVIDENCE_INSUFFICIENT; the underlying implementation work is real but the advantage claim is not yet supported. A1 must produce E4 (integration-verified) or E7 (security-negative-verified) evidence to re-open these claims. |
| **A0.1-G4-003** | P2 | Dimension A-05 had field name typo `icorer_evidence_grade`. Any automated reader of `icoder_evidence_grade` would silently default. v2.2 fixes the typo. |
| **A0.1-G4-004** | P2 | C-12 (ICD-10-CN coverage) and C-13 (DRG-DIP rules) claimed Clinical ICODER_ADVANTAGE at E2 with no formal benchmark on file. Phase A1 must run the 201-case gold standard (per A0-P0-013) and produce a benchmark report before these can return to ADVANTAGE. |
| **A0.1-G4-005** | P3 | Phase A0 v2.1 `by_status` sum was 55 — neither 51 nor 59. The v2.1 author wrote three different numbers in three places and none matched. v2.2 makes the count formula explicit. |

## §9. Gate 4 verdict

```
PHASE_A0_1_GATE_4_PARITY_MATRIX_V2_2_DERIVED
59_DIMENSIONS (machine-counted from array)
59_BY_STATUS_SUM (machine-derived; matches array)
9_ADVANTAGE_CLAIMS_REVOKED (evidence below threshold)
2_ICODER_ADVANTAGE_REMAINING (B-10 UX E5, D-04 tool-catalog E2)
14_EVIDENCE_INSUFFICIENT (5 original + 9 regraded)
0_NARRATIVE_NUMBERS_IN_SUMMARY
0_TYPED_FIELD_NAME_ERRORS
HARD_CHECKPOINT_PM_PROVISIONAL_PASS (8/8)
```

### Phase A0 v2.1 parity matrix NOT modified (preserved as audit trail).

End of Gate 4. Proceeding to Gate 5 — Product Maturity V2.
