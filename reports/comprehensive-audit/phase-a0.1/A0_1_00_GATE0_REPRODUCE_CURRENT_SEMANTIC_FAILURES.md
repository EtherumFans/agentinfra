# Phase A0.1 Gate 0 — Reproduce Current Semantic Failures

> Read-only diagnostic. Does NOT inherit `overall_pass=true` from Phase A0.
> Does NOT modify product code. Does NOT commit. Does NOT create tag.
> Does NOT start Phase A1 product development.

Spec reference: Phase A0.1 §一 (current confirmed failure conditions), §三 (Gate 0 first-round output).

---

## §0. Methodology and evidence handling

The Phase A0 audit package is treated as **a failing test fixture**. Every claim
in `phase_a0_validation.json` is re-derived from the underlying JSON artifacts
and gate docs. Where the validator's recorded claim diverges from the underlying
data, both are reported.

Evidence for this gate was gathered by reading:
- `reports/comprehensive-audit/phase-a0/phase_a0_validation.json` (validator output)
- `scripts/audit/validate_phase_a0.py` (validator source)
- All 10 Phase A0 gate markdown deliverables
- All 8 JSON artifacts (manifest, ledger, parity matrix, maturity, architecture,
  ontology)
- Live working-tree state via `git status --porcelain` and directory listings
- Live `backend/.env` content

No new code, no commit, no tag.

---

## §1. Sixteen required findings

### Finding 1 — Git HEAD, Branch, Remote

```
HEAD    = c147d015455017bc1d8420cbdbd813b3b8ec23ce
Branch  = master
Remote  = origin → https://github.com/EtherumFans/agentinfra.git
```

The HEAD commit message is
`feat(track-h): Tier 2 Corti controlled probes — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells`.
This is a **Phase 5 Track H** commit. Phase 6, Phase 7, Comprehensive Audit,
Pre-A0, and Phase A0 are therefore all **uncommitted**. The Phase A0 validator
treats HEAD as the trusted commit, but no audit deliverable is actually anchored
to the commit graph yet.

### Finding 2 — Working tree classification (97 entries)

`git status --porcelain | wc -l` = **97** entries (manifest claims 96 — minor
discrepancy from off-by-one when the v2 manifest was authored; not material).

Breakdown by category:

| Category | Count | Examples |
|----------|------:|----------|
| Modified product code — backend | 9 | `backend/app/api/agent_run.py`, `backend/app/main.py`, `backend/app/middleware/auth.py`, … |
| Modified product code — frontend | 4 | `frontend/src/App.tsx`, `frontend/src/components/layout/Layout.tsx`, `frontend/src/i18n/locales.ts`, … |
| Modified packages (SDK + embedded) | 12 | `packages/icoder-sdk/src/client.ts`, `packages/icoder-embedded/src/icoder-assistant.ts`, … |
| Modified tests | 2 | `backend/tests/conftest.py`, `backend/tests/test_api/test_phase4f_agent_run.py` |
| Deleted | 1 | `packages/icoder-sdk/package-lock.json` |
| New backend code (Phase 7) — untracked | 12 | `backend/alembic/versions/012..015_*.py`, `backend/app/api/{runs,examples,preview_sessions}.py`, `backend/app/middleware/partner_cors.py`, `backend/app/services/{idempotency,preview_ticket,run_lifecycle,trace_token}.py`, `backend/app/models/{idempotency_record,preview_session}.py` |
| New backend tests (Phase 7) — untracked | 10 | `backend/tests/test_api/test_phase7_gate{1,3,4,5,6,7,8,9}_*.py`, `backend/tests/unit/.../test_phase7_gate13a_*.py` (4 files) |
| New frontend page — untracked | 1 | `frontend/src/pages/EmbeddedAssistantPage.tsx` |
| New partner app — untracked dir | 1 | `examples/` (Corti-style partner reference app + 3 demo HTMLs) |
| New external consumer harness — untracked dir | 1 | `phase7-external-consumer/` |
| New SDK dist + tgz — untracked | 2 | `packages/icoder-sdk/dist/`, `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` |
| New embedded tgz — untracked | 1 | `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` |
| New embedded demos — untracked | 1 | `packages/icoder-embedded/demos/` |
| New DEPRECATED markers — untracked | 4 | `packages/icoder-web/DEPRECATED.md`, `packages/web-components/DEPRECATED.md`, `web-components/DEPRECATED.md`, `packages/icoder-sdk/README.md` (modified) |
| New reports (Phase 6 + 7 + audit + A0) — untracked | 4 | `reports/phase6/`, `reports/phase7/`, `reports/comprehensive-audit/`, `docs/audit/` |
| New audit scripts — untracked | 1 | `scripts/audit/` |
| New Corti parity docs — untracked | 2 | `docs/corti_parity/phase7_gate13a/` (1 file), `docs/audit/` |
| Screenshots (audit-gate3-*, corti_console_*, corti_embedded_*) — untracked | 21 | root-level PNGs |
| Browser profile — untracked dir | 1 | `.audit-chrome-profile/` (Chrome user-data-dir, cookies and session state inside) |
| New backend source/SDK resources | 1 | `packages/icoder-sdk/src/resources/runs.ts` |

**Total** = 97 entries.

**Categories that MUST NOT be committed as-is**:
- `.audit-chrome-profile/` (browser profile — likely contains cookies,
  session tokens, browsing history; must be `.gitignore`'d, not committed)
- Root-level screenshots (intermediate work product; should move to
  `evidence/` or delete)
- Any file containing real backend secrets (verified below — `backend/.env`
  still has `SECRET_KEY=change-me-in-production` and `DEBUG=true`)

### Finding 3 — Has business code changed after Phase A0?

Phase A0 is **not committed**. Therefore nothing can be said to have changed
"after" Phase A0 on the commit graph. However, the working tree contains
**both** the audit deliverables **and** mixed product changes that Phase A0
itself declared to be out of scope (read-only).

Phase A0 declared the following constraints honored (v2 manifest
`phase_a0_constraints_honored`):
- `read_only: true`
- `no_new_agent_expert_tool_runtime_prompt: true`
- `no_cdi_prompt_tuning: true`
- `no_medical_coding_model_change: true`

The working tree contains:
- New Phase 7 backend code (12 new files) — this predates Phase A0 (Phase A0
  references it as evidence), but it is **uncommitted**, so the trusted-commit
  guarantee is already broken before Phase A0 starts
- New alembic migrations `012..015_*.py` — schema changes that **materially
  alter** the product (idempotency, run cancel/status, api client attribution,
  preview sessions)
- No new agent/expert/tool/runtime/prompt files introduced by Phase A0 itself
  (confirmed — Phase A0 deliverables are all `.md` and `.json`)
- No CDI prompt edits (confirmed by file-listing)

**Conclusion**: The Phase A0 deliverables honor the read-only constraint
internally, but they sit on top of an uncommitted substrate (Phase 7 +
comprehensive audit + Pre-A0) that was never frozen. The "no baseline drift"
claim (Finding 6 of v2 manifest) is therefore unsound.

### Finding 4 — The ten current gate reports

All 10 gate markdown deliverables exist on disk under
`reports/comprehensive-audit/phase-a0/`:

| # | File | Size (bytes) | Last modified |
|--:|------|-------------:|---------------|
| 0 | `A0_00_BASELINE_AND_SCOPE.md` | 29,371 | 2026-07-16 16:48 |
| 1 | `A0_01_EVIDENCE_MANIFEST_CLOSURE.md` | 11,484 | 2026-07-16 16:54 |
| 2 | `A0_02_CAPABILITY_ONTOLOGY_AND_COUNTS.md` | 13,910 | 2026-07-16 17:00 |
| 3 | `A0_03_CORTI_EVIDENCE_REGRADING.md` | 16,213 | 2026-07-16 17:03 |
| 4 | `A0_04_PARITY_MATRIX_V2_1.md` | 9,066 | 2026-07-16 17:07 |
| 5 | `A0_05_CANONICAL_ISSUE_LEDGER.md` | 8,586 | 2026-07-16 17:11 |
| 6 | `A0_06_PRODUCT_MATURITY_TRUTHFULNESS.md` | 6,087 | 2026-07-16 17:13 |
| 7 | `A0_07_CANONICAL_ARCHITECTURE_V2.md` | 13,229 | 2026-07-16 17:15 |
| 8 | `A0_08_REMEDIATION_ROADMAP_AND_PHASE_A1_ENTRY.md` | 12,947 | 2026-07-16 17:17 |
| 9 | `A0_09_EXECUTIVE_SUMMARY_AND_FINAL_DECISION.md` | 14,666 | 2026-07-16 17:30 |

**All ten files are uncommitted** (their parent directory
`reports/comprehensive-audit/` is `??` in `git status`).

### Finding 5 — JSON artifacts the validator actually parsed

The validator source (`scripts/audit/validate_phase_a0.py` lines 47-56)
declares **8** artifacts:

```
evidence_manifest.v2.json
evidence_manifest.public.json
evidence_manifest.pre_a0.snapshot.json
capability_ontology.json
parity_matrix_v2_1.json
issue_ledger.json
product_maturity.json
architecture_v2.json
```

The validator's recorded output (`phase_a0_validation.json` line 58-224) lists
exactly 8 parse entries.

**Contradicts**: Gate 9 executive summary §1 says "9 JSON artifacts"; §11
machine-validation bullet list also says "9 JSON artifacts"; the Gate 9 §2
table lists 9 rows because it counts `architecture_v2.json` separately from the
other JSONs AND implicitly counts `phase_a0_validation.json` itself as the
9th — but `phase_a0_validation.json` is the validator OUTPUT, not an input
artifact. This is the source of the "9 vs 8" discrepancy.

### Finding 6 — Where 51, 55, 59 come from (parity matrix)

Source: `reports/comprehensive-audit/phase-a0/parity_matrix_v2_1.json`.

**59** is the truth. The `dimensions` array literally contains 59 objects
(`A-01..A-10`, `B-01..B-10`, `C-01..C-13`, `D-01..D-05`, `E-01..E-07`,
`F-01..F-08`, `G-01..G-06`).

**51** is what the JSON `summary.total_dimensions` field claims (line 652).

**55** is what the `summary.by_status` map sums to (line 653-664):
```
PARITY=9 + PARTIAL_PARITY=7 + ICODER_ADVANTAGE=11 + CORTI_ADVANTAGE=12
+ DIFFERENT_BY_DESIGN=3 + OUT_OF_SCOPE=4 + NOT_IMPLEMENTED=4
+ EVIDENCE_INSUFFICIENT=4 + ICODER_TECH_DEBT=1 = 55
```

**Actual status counts from re-reading `parity_status` field of each of 59
dimensions**:

| Status | JSON summary claims | Actual from array |
|--------|--------------------:|------------------:|
| PARITY | 9 | 9 |
| PARTIAL_PARITY | 7 | **6** |
| ICODER_ADVANTAGE | 11 | 11 |
| CORTI_ADVANTAGE | 12 | **17** |
| DIFFERENT_BY_DESIGN | 3 | 3 |
| OUT_OF_SCOPE | 4 | **3** |
| NOT_IMPLEMENTED | 4 | 4 |
| EVIDENCE_INSUFFICIENT | 4 | **5** |
| ICODER_TECH_DEBT | 1 | 1 |
| **Sum** | **55** | **59** |

**Summary block is internally inconsistent with the array.** Three numbers are
wrong in the same direction (under-claiming Corti advantages and
over-claiming PARTIAL_PARITY).

The validator reads `dim.get("status")` (validate_phase_a0.py line 304) but
the JSON field is named `parity_status`. The validator's status_counts map
collapses to `{"UNKNOWN": 59}` for this reason.

### Finding 7 — Where 75, 82, 91 come from (issue ledger)

Source: `reports/comprehensive-audit/phase-a0/issue_ledger.json`.

**91** is the truth. The `issues` array contains exactly 91 entries
(24 P0 + 55 P1-tagged of which 28 are severity=P2 + 12 P3).

**82** = `23 P0 + 23 P1 + 24 P2 + 12 P3` — the **Gate 5 narrative** numbers
(`A0_05_CANONICAL_ISSUE_LEDGER.md` §3, §4 and §10 verdict). The arithmetic
itself does not even sum to 75 (23+23+24+12=82), so the Gate 5 narrative is
internally broken.

**75** = `coverage_check.total_unique_after_dedup` (issue_ledger.json
line 139). This is the "logical issue count after dedup" — but the ledger
identifies only **5 explicit duplicates** (A0-P1-010/012/013/029 + A0-P3-011),
which would give `91 − 5 = 86`, not 75.

**Three different count sets appear in three different places**:

| Source | P0 | P1 | P2 | P3 | Total |
|--------|---:|---:|---:|---:|------:|
| Gate 5 narrative (A0_05 §3-4) | 23 | 23 | 24 | 12 | 82 (text says 75) |
| Gate 8 roadmap (A0_08 §2 workstream tables, §6 plan) | 23 | 23 | 24 | 12 | 82 |
| Gate 9 Final Decision §5 headline | **24** | **27** | **28** | 12 | **91** |
| JSON issue_ledger.json severity_counts | **24** | **27** | **28** | 12 | **91** |
| JSON issue_ledger.json coverage_check.total_unique_after_dedup | — | — | — | — | 75 |

### Finding 8 — Where 23 and 24 P0 come from

**24** is the truth from the array. Severity sub-class breakdown:
- P0-S: 12 (001, 002, 008, 010, 011, 012, 016, 017, 018, 019, 020, 021)
- P0-C: 2 (007, 013)
- P0-D: 4 (003, 022, 023, 024)
- P0-T: 6 (004, 005, 006, 009, 014, 015)
- Sum: 24

**23** is what Gate 5 §3 and §10 verdict claim (`23_P0 (10 P0-S + 2 P0-C + 5 P0-D + 6 P0-T)`).

Note that `10 + 2 + 5 + 6 = 23` ✓ (Gate 5 sub-class arithmetic is consistent
internally), but the sub-class counts themselves disagree with the array
(array has 12 P0-S and 4 P0-D, narrative has 10 P0-S and 5 P0-D).

Gate 5 §3 distribution table therefore has **two errors**:
- P0-S: claims 10, actual 12
- P0-D: claims 5, actual 4

Gate 8 roadmap §1 also says "All 23 P0 issues" and A1-S workstream table says
"10 P0-S issues" — both propagate the same error.

Gate 9 §5 headline correctly says **24 P0**.

### Finding 9 — Why the validator judged 59 UNKNOWN as pass

`validate_phase_a0.py` line 295-313:

```python
def check_parity_matrix_dimensions(results: dict) -> None:
    ...
    data = load_json(path)
    dimensions = data.get("dimensions", [])
    status_counts: dict[str, int] = {}
    for dim in dimensions:
        status = dim.get("status", "UNKNOWN")  # ← BUG: field is `parity_status`
        status_counts[status] = status_counts.get(status, 0) + 1
    forbidden_composites = [...]
    composite_hits = [s for s in status_counts if s in forbidden_composites]
    results["parity_matrix_dimensions"] = {
        "total_dimensions": len(dimensions),
        "status_counts": status_counts,
        "forbidden_composites_found": composite_hits,
        "pass": len(dimensions) >= 40 and len(composite_hits) == 0,
    }
```

Two compounding bugs:

1. **Wrong field name** — every dimension falls back to `"UNKNOWN"` because
   `dim.get("status")` returns `None` (the JSON uses `parity_status`). All 59
   dimensions collapse into one bucket.
2. **Pass threshold is `>= 40` count-only** — even if every dimension were
   `UNKNOWN`, the validator returns PASS as long as the array has at least 40
   entries and no composite bucket name appears.

The validator therefore certifies `pass: true` while simultaneously recording
that it could not read a single status. `phase_a0_validation.json` line 343-349
contains this self-contradiction verbatim:
```
"total_dimensions": 59,
"status_counts": {"UNKNOWN": 59},
"forbidden_composites_found": [],
"pass": true
```

### Finding 10 — Why the validator treated all 5 candidate verdicts as hit

`validate_phase_a0.py` line 239-251:

```python
def check_final_decision_enumerated(results: dict) -> None:
    ...
    text = load_text(path)
    found = [v for v in ALLOWED_FINAL_DECISIONS if v in text]
    pass_decision = ALLOWED_FINAL_DECISIONS[0]
    results["final_decision"] = {
        "allowed_decisions_found": found,
        "is_pass_decision": pass_decision in found,
        "pass": len(found) >= 1,
    }
```

Gate 9 §7 explicitly **enumerates all 5 allowed verdicts as candidates** in
its documentation table. The substring scan therefore finds all 5 strings in
the markdown — not because all 5 were selected, but because all 5 were listed
as allowed options.

The validator then:
- Records `allowed_decisions_found: [<all 5 verdicts>]`
- Records `is_pass_decision: true` (because the PASS verdict string is
  somewhere in the document — in the candidate list)
- Records `pass: true` because `len(found) >= 1`

**This is the self-attestation loop**: the Gate 9 doc lists 5 allowed verdicts
as documentation; the validator interprets the documentation list as the
selection. The validator never verifies that exactly one verdict was
selected, and never parses the §9 "Final Decision" code block to confirm
which verdict was actually chosen.

### Finding 11 — Placeholder hashes in the v2 manifest

`reports/comprehensive-audit/phase-a0/evidence_manifest.v2.json` still contains:

| Line | Field | Value |
|-----:|-------|-------|
| 100 | `evidence_index.commands[0].sha256` | `"NOT_YET_CAPTURED"` (gate0/git_rev_parse_head.txt) |
| 101 | `evidence_index.commands[1].sha256` | `"NOT_YET_CAPTURED"` (gate0/git_status_short.txt) |
| 102 | `evidence_index.commands[2].sha256` | `"NOT_YET_CAPTURED"` (gate0/git_remote_v.txt) |
| 105 | `evidence_index.test-results[0].status` | `"EMPTY_DIR"` |
| 108-113 | `evidence_index.browser[*].status` | `"EMPTY_DIR"` × 6 (gate13a screenshots / console-logs / network-audit / sanitized-har / playwright-traces / storage-audit) |
| 128 | `evidence_index.playwright-traces[0].status` | `"EMPTY_DIR"` |
| 131 | `evidence_index.sanitized-har[0].status` | `"EMPTY_DIR"` |
| 143 | `evidence_index.network[0].status` | `"EMPTY_DIR"` |
| 146 | `evidence_index.storage[0].status` | `"EMPTY_DIR"` |
| 149 | `evidence_index.security[0]` | `"Phase A0 Gate 5 will inherit ..."` (future tense) |
| 159 | `evidence_index.architecture[0].status` | `"EMPTY_DIR"` + note `"Phase A0 Gate 7 will populate"` (future tense) |
| 169 | `evidence_grade_index.grades_to_add_in_phase_a0` | future-tense artifact list |

The validator's `check_no_placeholders_in_v2_manifest` scans for `(per-file)`,
`pending write`, `TODO`, `<TBD>`, `TBD` only — **it does not scan for
`NOT_YET_CAPTURED` or `EMPTY_DIR`**. The validator's
`placeholders_resolved.count = 24` is therefore accurate only for the narrow
set of token strings the regex matches; the user-visible claim "0 placeholders
remaining" is false.

### Finding 12 — Gate 13A actual evidence file count

The manifest records 7 Gate 13A evidence directories all as `EMPTY_DIR`
(`reports/phase7/gate13a/{screenshots,console-logs,network-audit,sanitized-har,playwright-traces,storage-audit,test-results}/`).

Direct filesystem check confirms:

```
reports/phase7/gate13a/screenshots/        → 0 files
reports/phase7/gate13a/console-logs/       → 0 files
reports/phase7/gate13a/network-audit/      → 0 files
reports/phase7/gate13a/sanitized-har/      → 0 files
reports/phase7/gate13a/playwright-traces/  → 0 files
reports/phase7/gate13a/storage-audit/      → 0 files
reports/phase7/gate13a/test-results/       → 0 files
```

The only files under `reports/phase7/gate13a/` are 3 markdown reports
(`PHASE7_GATE13A_BASELINE.md`, `PHASE7_GATE13A_FINAL_REPORT.md`,
`PHASE7_GATE13A_THREAT_MODEL.md`) plus one image at
`docs/corti_parity/phase7_gate13a/e2e_widget_interactive.png`.

**Zero original browser screenshots. Zero console logs. Zero HAR files. Zero
Playwright traces. Zero storage audits. Zero test result files.**

Issue ledger A0-P0-018 and A0-P0-019 claim `MITIGATED_IN_PHASE_7` with
`evidence_grade: E7` (SECURITY_NEGATIVE_VERIFIED). E7 requires an independent
negative verification — which cannot exist without any captured browser
evidence. The claim is therefore `IMPLEMENTATION_REPORTED`, not `E7`.

### Finding 13 — Source of Medical Coding L8 evidence

`product_maturity.json` line 27 sets `CN-01 Medical Coding (ICD-10-CN)` to
`current_maturity: "L8_QUALITY_BENCHMARKED"`. The rationale (line 28) is:

> "Phase 5 Track H ran 40-case Corti calibration + 201 iCoDer baseline. F1
> reported per iteration."

Cross-checks:

1. **Issue ledger A0-P0-013** (G10-001): severity `P0-C`, title
   "Only F1@1=0.15 on 5-case smoke; no 201-case baseline; CLAUDE.md 金标准评估
>    claim unbacked". Evidence grade E2.
2. **Issue ledger A0-P1-013** (duplicate of P0-013): confirms
   "no F1 baseline" is the canonical finding.
3. **CLAUDE.md §金标准评估** instructs running
   `python scripts/e2e_runtime_validation.py` for the 201-case gold standard —
   but no `tests/regression/test_f1_baseline.py` has been run against the
   frozen 201-case fixture as part of this audit (no evidence file in manifest
   under `tests/regression/`).
4. **Parity matrix** dimension A-08 / G-06 / F-01-08 — none of these reference
   a frozen held-out dataset or regression gate.

**The L8 claim is back-derived from Track H iteration logs, which are
prompt-tuning calibration runs (each iteration changes the prompt and
re-runs). They are NOT a held-out benchmark.** Per A0.1 §三 Gate 5 rules,
Medical Coding must be **SMOKE_ONLY** until:
- A frozen held-out dataset exists (not the calibration set)
- A defined metric (F1, agreement rate) is computed on that set
- Results are saved with a content hash
- A CI regression gate exists

None of these conditions is satisfied. **L8 is overclaimed.**

### Finding 14 — Current Roadmap vs Ledger discrepancy

Gate 8 roadmap `A0_08_REMEDIATION_ROADMAP_AND_PHASE_A1_ENTRY.md`:

| Roadmap section | Claim | Ledger truth |
|-----------------|-------|---------------|
| §1 Phase summary | "All 23 P0 issues resolved" | Array has 24 P0 |
| §1 Phase summary | "23 P1 issues resolved" | Array has 27 P1 |
| §1 Phase summary | "24 P2 issues resolved" | Array has 28 P2 |
| §2 A1-S workstream | "10 P0-S issues" | Array has 12 P0-S |
| §2 A1-C workstream | "2 P0-C issues" | Array has 2 P0-C ✓ |
| §2 A1-D workstream | "5 P0-D issues" | Array has 4 P0-D |
| §2 A1-T workstream | "6 P0-T issues" | Array has 6 P0-T ✓ |
| §2 A1-D workstream | Lists A0-P0-005 (Corti links) under A1-D | A0-P0-005 severity is `P0-T` (Product Truth), not P0-D |
| §6 Sequenced plan | "Month 13 PARTNER_PRODUCTION_READY achievable" | `PARTNER_PRODUCTION_READY` is a forbidden verdict per v2 manifest line 192 |
| §6 Sequenced plan | "Month 14 COMMERCIAL_GA" | `COMMERCIAL_GA` is the head of `commercial_ga_ready`, a forbidden verdict |

Additional priority problems called out by user feedback:

- **A1-T places Payment Processor + Public npm + Auto Top-up as P0-T**.
  These are commercial product features, not Security/PHI/Tenant blockers.
  A0-P0-009 (npm publish) and A0-P0-004 (Stripe/Alipay/WeChat) should NOT
  be in the same P0 tier as encryption-at-rest and 等保2.0.
- **Roadmap does not distinguish** between:
  - Security blockers (blocks any production)
  - Partner Technical Staging blockers (blocks external consumer)
  - Commercial blockers (blocks revenue)
- Roadmap's "PARTNER_PRODUCTION_READY achievable" / "COMMERCIAL_GA" claims
  are forbidden maturity verdicts per the v2 manifest itself.

### Finding 15 — Safely committable vs non-committable files

**MUST NOT be committed** under any circumstances:

| Path | Reason |
|------|--------|
| `backend/.env` | Contains `SECRET_KEY=change-me-in-production` and `DEBUG=true`. Issue A0-P0-010. Must be rotated + `.gitignore`'d before any commit. |
| `.audit-chrome-profile/` | Full Chrome user-data-dir. Contains cookies, session state, browsing history, crash dumps, GPU caches. Must be `.gitignore`'d. |
| `audit-gate3-*.png` (5 files) and `corti_console_*.png` / `corti_embedded_*.png` (16 files) at repo root | Stray working screenshots. Move to `evidence/` with hashes, or delete. |
| Any file matching `*.tgz` under `packages/` that contains real build output containing third-party code | Must be reviewed; a signed publishing flow is required (A0-P0-021). |

**Safely committable as audited product snapshot** (Commit A in Gate 9 plan):
- All 9 modified backend files (Phase 7 wiring; already public-IP cleaned)
- All 12 new backend files (Phase 7 Gate 1-9 + 13A; already public-IP cleaned)
- All 10 new backend test files
- All 4 modified frontend files
- All 12 modified packages/icoder-sdk files + `runs.ts` + dist artifacts
- All 5 modified packages/icoder-embedded files + demos
- 4 new alembic migrations
- New `examples/` (Corti-style partner reference app + 3 demos)
- New `phase7-external-consumer/`
- `packages/icoder-web/DEPRECATED.md`, `packages/web-components/DEPRECATED.md`, `web-components/DEPRECATED.md`
- `frontend/src/pages/EmbeddedAssistantPage.tsx`

**Safely committable as audit snapshot** (Commit B in Gate 9 plan):
- `reports/comprehensive-audit/` (Phase A0 + Phase A0.1 final)
- `reports/phase6/`, `reports/phase7/`
- `docs/audit/`, `docs/corti_parity/`
- `scripts/audit/`
- `packages/icoder-embedded/demos/` (if not already in Commit A)

**Ambiguous — must be reviewed before staging**:
- `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz`
- `packages/icoder-embedded/icoder-embedded-2.0.0.tgz`
  (These are real build outputs but the version name itself is a forbidden
  verdict-adjacent claim — `1.0.0-beta.2` as an unpublished version is fine,
  but only if the tarball is regenerated reproducibly at commit time and the
  SHA-256 is captured in the v2 manifest. Currently the manifest records
  sha256 for both, so this can be resolved in Gate 2.)

**No `git add -A`**: must stage by explicit path list.

### Finding 16 — Current temporary verdict

```
PHASE_A0_1_GATE_0_TEMPORARY_VERDICT:
  FAIL_PHASE_A0_OVERALL_PASS_INVALIDATED
  FAIL_PHASE_A0_PARITY_MATRIX_SEMANTIC_INVALID
  FAIL_PHASE_A0_VALIDATOR_SELF_ATTESTING_LOOP
  FAIL_PHASE_A0_FINAL_DECISION_SELECTION_AMBIGUOUS
  FAIL_PHASE_A0_PLACEHOLDER_RESOLUTION_INCOMPLETE
  FAIL_PHASE_A0_GATE_13A_SECURITY_CLOSURE_UNEVIDENCED
  FAIL_PHASE_A0_PRODUCT_MATURITY_L8_OVERCLAIMED
  FAIL_PHASE_A0_ROADMAP_PRIORITY_AND_VERDICTS_INVALID
  FAIL_PHASE_A0_LEDGER_COUNT_TRIALLY_INCONSISTENT
  FAIL_PHASE_A0_BASELINE_NON_REPRODUCIBLE_UNCOMMITTED
  PASS_PHASE_A0_FACTUAL_FOUNDATION_RECONSTRUCTION (the valuable corrections)
  BLOCKED_BY: 11 failure conditions above
  NOT_INHERITED: PASS_PHASE_A0_AUDIT_CLOSURE_AND_READY_FOR_PHASE_A1_...
```

Phase A0 produced valuable factual reconstruction (Execution Plane vs Domain
Runtime vs Platform Core; Agent Pack Catalog vs Expert Hierarchy; Workflow
Gates vs Pseudo-Experts; reinstated Secret/Tenant/PHI/Cost/Trace/Audit +
clinical quality concerns; retirement of composite parity percentages). Those
corrections are kept. The semantic, numerical and evidence-layer failures are
not.

Gate 0 closes here. Proceeding to Gate 1 (Audited Fileset and Baseline
Snapshot) — read-only enumeration, no commit, no tag.
