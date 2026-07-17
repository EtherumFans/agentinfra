# Phase A0.1R Gate 0 — Preflight and Failure Reproduction

> Reproduces every defect class that prevents Phase A0.1's
> `PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1`
> from being inheritable. Produces the **27 required outputs** demanded
> by the Phase A0.1R charter and locks the corrected state in writing
> before any Gate 1+ mutation begins.
>
> Verdict emitted by Gate 0 (NOT a PASS — preflight only):
> `PHASE_A0_1_R_GATE_0_PREFLIGHT_AND_DEFECT_REPRODUCTION_COMPLETE`
>
> **Inherited verdict**: REFUTED.
> Phase A0.1's summary declares `BASELINE_FROZEN` without performing
> any commit or tag. Verified below: zero commits, zero tags.

Spec reference: Phase A0.1R charter §3 (Gate 0), §6 (Forbidden Actions
during Gate 0), §A (27 Required Outputs).

---

## §0. Provenance and scope

| | |
|---|---|
| Phase | A0.1R — Secure Freeze Reconciliation |
| Predecessor | Phase A0.1 (audit repair; **verdict REFUTED**, not inherited) |
| Trusted HEAD | `c147d015455017bc1d8420cbdbd813b3b8ec23ce` |
| Branch at Gate 0 close | `master` (will be moved to `audit/phase-a0.1r-freeze` in Gate 8) |
| Remote | `https://github.com/EtherumFans/agentinfra.git` (push FORBIDDEN per §6) |
| Gate 0 mode | **READ-ONLY** — no commit, no tag, no push, no branch, no product code mutation, no audit report mutation |
| Forbidden during Gate 0 | Per Phase A0.1R charter §6 |

Gate 0 produces **only documentation and machine-readable evidence**.
The corrected JSON files (issue ledger V2.1, parity matrix V2.3,
maturity V3, manifest V2.2) are written in Gates 1–5, not Gate 0.

---

## §1. Verified repository state (outputs 1–5)

### Output 1 — Trusted HEAD

```
$ git rev-parse HEAD
c147d015455017bc1d8420cbdbd813b3b8ec23ce
```

Matches Phase A0.1 Gate 9 §2 trusted commit. **No drift.**

### Output 2 — Branch

```
$ git rev-parse --abbrev-ref HEAD
master
```

Phase A0.1R charter §6 forbids committing on `master`. Gate 8 will
create `audit/phase-a0.1r-freeze` and stage commits there. Until
Gate 8 begins, master stays untouched.

### Output 3 — Remote

```
$ git remote -v
origin  https://github.com/EtherumFans/agentinfra.git (fetch)
origin  https://github.com/EtherumFans/agentinfra.git (push)
```

Push is FORBIDDEN by Phase A0.1R charter §6. Tag stays local;
remote publication is a post-A1A business decision.

### Output 4 — Annotated tag inventory

```
$ git tag -l 'audit/*'
(empty)
```

**Phase A0.1 Gate 9 claimed `audit/phase-a0.1-baseline` was created.**
Verified: it was not. No `audit/*` tag of any kind exists. The
"BASELINE_FROZEN" claim in Phase A0.1's final summary is false.

### Output 5 — Commit A/B/C inventory

```
$ git log --all --oneline --grep="phase-a0.1"
(empty)
$ git log --all --oneline --grep="Bucket A"
(empty)
$ git log --all --oneline --grep="audit package"
(empty)
```

**Phase A0.1 Gate 9 specified Commit A and Commit B.** Neither exists.
Phase A0.1R will create Commit A, Commit B, and the new Commit C
(freeze receipt) in Gate 8/9.

---

## §2. Compromised credential containment surface (outputs 6–10)

### Output 6 — Compromised credential

```
ICODER_API_CLIENT_SECRET = [REDACTED_COMPROMISED_API_CLIENT_SECRET]
sha256(secret) = 7a3b25efb0a901a66ce5df775a74911c75808e9fed93e9421157c666d3b436a4
```

Source: `examples/partner-reference-app/.env` line:
`ICODER_API_CLIENT_SECRET=[REDACTED_COMPROMISED_API_CLIENT_SECRET]`

Status per Phase A0.1R charter §3.Gate1: **COMPROMISED**.
Working-tree exposure to audit tooling counts as compromise
(no matter that the audit tool runs locally — the file persisted in
plain text through Phase A0.1, was referenced by hash in two Phase
A0.1 markdown reports, and is part of the workspace that Gate 9
intended to freeze without first redacting).

### Output 7 — Files containing the secret (plain text)

```
$ grep -rl "[REDACTED_COMPROMISED_API_CLIENT_SECRET_FINGERPRINT]" \
    . 2>/dev/null | grep -v node_modules | grep -v "\.git/"
./examples/partner-reference-app/.env
./reports/comprehensive-audit/phase-a0.1/A0_1_01_AUDITED_FILESET_AND_BASELINE_SNAPSHOT.md
./reports/comprehensive-audit/phase-a0.1/A0_1_09_SAFE_COMMIT_AND_IMMUTABLE_FREEZE.md
```

**3 files.** All working-tree only.

### Output 8 — Secret NOT in git history

```
$ git log --all -p 2>/dev/null | grep -c "[REDACTED_COMPROMISED_API_CLIENT_SECRET_FINGERPRINT]"
0
```

**0 occurrences across all commits.** The secret has never been
committed. Therefore:

- Rotation scope = **local invalidation only** (rotate hash in local
  dev SQLite; sweep redactions in working-tree files). No remote
  registry, no key manager, no partner production system needs
  rotation.
- Phase A0.1R Gate 1 does **not** need to take the remote registry
  offline. (Phase A0.1 Gate 9 finding A0.1-G9-001 said "rotate
  before any push"; since no push will occur and the secret has
  never left the working tree, "rotation" reduces to local
  invalidation.)

### Output 9 — Browser profile coverage

```
.gitignore line 127: /.audit-chrome-profile/
```

```
$ ls .audit-chrome-profile/ 2>/dev/null | wc -l
42
```

The Chrome profile (42 top-level entries; includes session storage,
cookies, cache) IS covered by `.gitignore`. **No risk of accidental
commit via Bucket C/Bucket D staging.** Phase A0.1 Gate 9 §5 was
correct here.

### Output 10 — Phase A0.1R-required redaction token

Per Phase A0.1R charter §3.Gate1, the secret plain text is replaced
everywhere by the literal token:

```
[REDACTED_COMPROMISED_API_CLIENT_SECRET]
```

Gate 1 will apply this substitution to all 3 files in Output 7 and
verify that the literal secret no longer appears in any working-tree
file outside `.env` (which is gitignored and stays gitignored).

---

## §3. Bucket D materialized inventory (outputs 11–13)

### Output 11 — Tarballs

```
packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz
packages/icoder-embedded/icoder-embedded-2.0.0.tgz
```

Phase A0.1 Gate 9 deferred these. Phase A0.1R closes them in Gate 6
with explicit decisions (see §11 below).

### Output 12 — Built TS output directories

```
packages/icoder-sdk/dist/      (7 files; NOT covered by .gitignore sdk/dist/)
packages/icoder-embedded/dist/ (4 files; already tracked in git history)
phase7-external-consumer/dist/ (built JS)
```

Phase A0.1R charter §3.Gate6 default: `SOURCE_ONLY_AND_REBUILD`
for `packages/icoder-sdk/dist/` and `phase7-external-consumer/dist/`;
`KEEP_HISTORICALLY_TRACKED` for `packages/icoder-embedded/dist/`
(compatibility constraint).

### Output 13 — Stray screenshots at repo root

```
$ ls *.png | wc -l
35
```

Pattern breakdown:
- `audit-gate3-*.png` (5)
- `corti_console_*.png` (10)
- `corti_embedded_assistant_*.png` (4)
- Other stray screenshots (1 added since Phase A0.1 = 15 → confirmed 35 total per `ls *.png`)

Phase A0.1R charter §3.Gate6 default: `MOVE_AND_REDACT` — relocate
under `reports/comprehensive-audit/evidence/screenshots/` with
SHA-256 captured, PII / credentials / session tokens redacted.

### Output 13b — Deletion in working tree

```
D packages/icoder-sdk/package-lock.json  (staged in Phase A0.1 Bucket A list)
```

Phase A0.1R keeps the deletion. Rationale: lockfile drift was
documented in Phase A0.1 Gate 1; package-lock.json is regenerated
on install and need not be committed for a library package.

---

## §4. Canonical ledger defects (outputs 14–17)

### Output 14 — P0 aggregate count drift

Computed from `reports/comprehensive-audit/phase-a0.1/issue_ledger.v2.json`:

```
issues array length: 91
severity counts (from array): P0-S=12, P0-C=2, P0-D=4, P0-T=6, P0_aggregate=24
status counts (from array): OPEN=68, OPEN_BACKLOG=11,
                            MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED=2,
                            RESOLVED_PER_A0_GATE_2=3, RESOLVED_PER_A0_GATE_3=1,
                            REFRAMED=1, DUPLICATE=5
```

Ledger's `severity_counts_normalized.open_by_severity` claims:

```
P0-S_open: 11   ← actual OPEN P0-S = 10 (12 − 2 MITIGATED)
P0-C_open: 2    ← correct (both P0-C are OPEN)
P0-D_open: 4    ← correct (all 4 P0-D are OPEN)
P0-T_open: 6    ← correct (all 6 P0-T are OPEN)
P0_aggregate_open: 23   ← actual OPEN = 22; OPEN+MITIGATED = 24
```

**Drift source**: P0-S claim of 11 is neither the strict-OPEN count
(10) nor the OPEN+MITIGATED count (12). The Phase A0.1 ledger did
not enforce array-derived counts for the OPEN slice; it manually
subtracted 1 from P0-S without a recorded reason. This is the same
defect class as Phase A0 v1's "75/82/91 inconsistent" finding —
the very class Phase A0.1 Gate 3 claimed to have eliminated.

### Output 15 — primary_phase_mapping coverage

Per-issue `primary_phase` coverage is complete (all 91 issues carry
the field). The Phase A0.1R-relevant distribution (OPEN + OPEN_BACKLOG
+ MITIGATED, excluding DUPLICATE/RESOLVED/REFRAMED):

| primary_phase | count |
|---|---:|
| A1_security_first | 14 |
| A1_clinical_safety | 2 |
| A1_deployment_ops | 1 |
| A1_product_truth_minimal | 4 |
| A2_commercial_deferred | 4 |
| A2 | 17 |
| A3 | 28 |
| A4 | 11 |

The Phase A0.1 ledger's explicit-ID lists under
`primary_phase_mapping` are **incomplete**:

```
A1_security_first: explicit_ids has 12 entries
  includes A0-P0-022 (P0-D), A0-P0-023 (P0-D), A0-P0-024 (P0-D),
  A0-P0-001/002 (legal/compliance, should be separated per charter)
A2_commercial_deferred: explicit_ids = [A0-P0-004, A0-P0-008, A0-P0-009]
  MISSING: A0-P0-021 (supply chain signing, per-issue tagged A2_commercial_deferred)
```

### Output 16 — Workstream placement defects

| Issue | Severity | Current `primary_phase` | Charter-correct phase | Reason |
|---|---|---|---|---|
| A0-P0-001 | P0-S | A1_security_first | A1_legal_compliance (NEW) | Compliance cert is legal work, not engineering security |
| A0-P0-002 | P0-S | A1_security_first | A1_legal_compliance (NEW) | Privacy Policy / Terms / DPA / SLA is legal work |
| A0-P0-008 | P0-S | A2_commercial_deferred | A1_security_first | RUNTRACE_STORE=memory is a security/observability gap, not commercial |
| A0-P0-021 | P0-S | A2_commercial_deferred | A2_commercial_deferred (correct) | But missing from explicit_ids list (Output 15) |
| A0-P0-022 | P0-D | A1_security_first | A1_security_first (correct, tenancy) | Keep; is tenant isolation |
| A0-P0-023 | P0-D | A1_security_first | A1_deployment_ops | Backup/restore runbook is ops work |
| A0-P0-024 | P0-D | A1_security_first | A1_deployment_ops | Upgrade/rollback runbook is ops work |
| A0-P0-007 | P0-C | A1_clinical_safety | A1_clinical_safety (correct) | But CDI Research Mode must be bounded — does NOT close loop |

**Net effect on workstream count**: A1 grows from 4 workstreams
(security_first / clinical_safety / deployment_ops / product_truth_minimal)
to **5 workstreams** (add `A1_legal_compliance`). Combined with
the A2 / A3 / A4 set, the corrected count is **13 workstreams**,
not Phase A0.1's implied 12.

### Output 17 — Roadmap phase-count drift

Phase A0.1 Final Summary claimed `A1=19 P0 / A2=22 P1 + 4 P0-commercial-deferred / A3=27 P2 / A4=11 P3`.

Re-derived from corrected ledger (Gate 2 will lock the numbers;
Gate 0 reproduces the discrepancy):

```
A1 P0 (security + legal + clinical + deployment + product_truth):
  P0-S security_only = 10 (excludes A0-P0-001/002 → legal)
  P0-S legal_compliance = 2 (A0-P0-001/002)
  P0-C = 2
  P0-D security_tenancy = 1 (A0-P0-022)
  P0-D deployment_ops = 3 (A0-P0-003/023/024)
  P0-T product_truth = 4
  A1 P0 aggregate = 22

A2 P0-commercial-deferred:
  A0-P0-004 (Billing theater — split: Product Truth portion moves to A1_product_truth_minimal)
  A0-P0-009 (Package distribution)
  A0-P0-021 (Supply chain signing)
  A2 P0 = 3 (was 4; RUNTRACE_STORE moved back to A1)

A2 P1 / A3 P2 / A4 P3: per-issue `primary_phase` aggregates — Gate 2
will recompute and confirm whether the 22/27/11 figures hold.
```

The "79 vs 83 phase drift" mentioned in the charter arises because
Phase A0.1's roadmap counted 4 P0-commercial-deferred (including
A0-P0-008) but the corrected ledger has only 3 P0 in A2 — meanwhile
A0-P0-008 returns to A1, and the Billing Theater split produces one
new Product Truth P0. Net: A1 = 22, A2-commercial-deferred = 3,
Product-Truth-Commercial-Capability = 1 (parallel track). The sum
across the 4 phases is **79 open canonical** (matches ledger), but
the distribution across A1/A2/A3/A4 differs from Phase A0.1's claim.

---

## §5. Parity matrix defects (output 18)

### Output 18 — Parity V2.2 status illegalities + threshold violations

`reports/comprehensive-audit/phase-a0.1/parity_matrix_v2_2.json`:

```
allowed_statuses = [
  PARITY, PARTIAL_PARITY, ICODER_ADVANTAGE, CORTI_ADVANTAGE,
  DIFFERENT_BY_DESIGN, OUT_OF_SCOPE, NOT_IMPLEMENTED,
  NOT_VERIFIED, EVIDENCE_INSUFFICIENT, NOT_COMPARABLE
]
total dimensions: 59
status distribution:
  PARITY: 9, PARTIAL_PARITY: 6, NOT_IMPLEMENTED: 4,
  EVIDENCE_INSUFFICIENT: 14, CORTI_ADVANTAGE: 17,
  ICODER_ADVANTAGE: 2, OUT_OF_SCOPE: 3, DIFFERENT_BY_DESIGN: 3,
  ICODER_TECH_DEBT: 1   ← ILLEGAL (not in allowed_statuses)
```

**Illegality**: D-05 ("Legacy tool layer") carries status
`ICODER_TECH_DEBT`. This status is not in `allowed_statuses`. The
Phase A0.1 validator did not catch it because the validator's
allowed-status list (Phase A0.1 Gate 8) is not synchronized with
the matrix's `allowed_statuses` field. Phase A0.1R Gate 7 will
enforce validator-matrix synchronization.

D-05 corrected status: `EVIDENCE_INSUFFICIENT` or `DIFFERENT_BY_DESIGN`
— Gate 3 will pick the semantically correct option.

**Symmetric threshold violations**: The matrix declares

```
evidence_grade_thresholds_for_advantage:
  Runtime_advantage_minimum: E4
  Security_advantage_minimum: E7
  Clinical_advantage_minimum: formal benchmark or clinical audit
  UX_or_product_advantage_minimum: E5
  Tool_catalog_advantage_minimum: E2
```

17 dimensions carry `parity_status = CORTI_ADVANTAGE`. Distribution
by Corti evidence grade:

```
corti_evidence_grade=E5: 13
corti_evidence_grade=E1: 4   ← ALL FAIL THRESHOLD
```

The 4 failing CORTI_ADVANTAGE dimensions:

| ID | Class | Name | Corti grade | Threshold | Disposition |
|---|---|---|---|---|---|
| F-03 | Compliance | HIPAA | E1 | E7 (security) | Downgrade to EVIDENCE_INSUFFICIENT |
| F-04 | Compliance | ISO 27001 | E1 | E7 (security) | Downgrade to EVIDENCE_INSUFFICIENT |
| F-07 | Compliance | Multi-region failover | E1 | E7 (security) | Downgrade to EVIDENCE_INSUFFICIENT |
| F-08 | Compliance | Edge-node PHI redaction | E1 | E7 (security) | Downgrade to EVIDENCE_INSUFFICIENT |

All 4 are compliance/security class — threshold E7. None has Corti
evidence above E1 (marketing claims only). Per the symmetric
threshold rule (the same rule that downgraded 9 ICODER_ADVANTAGE
dimensions in Phase A0.1 Gate 4), these 4 must be downgraded to
`EVIDENCE_INSUFFICIENT`.

**Net change**: `CORTI_ADVANTAGE` count goes 17 → 13.
`EVIDENCE_INSUFFICIENT` count goes 14 → 18. Parity totals unchanged
at 59 dimensions.

---

## §6. Product maturity defects (output 19)

### Output 19 — Missing security + delivery axes

`reports/comprehensive-audit/phase-a0.1/product_maturity_v2.json`:

```
china_scenarios count: 16
sample scenario axes: code_maturity, quality_evidence, partner_validation,
                      regulatory, workflow_closure  ← 5 axes only
missing security axis: 16/16
missing delivery axis: 16/16
```

Phase A0.1R charter §3.Gate4 requires a **7-axis** maturity model:

```
1. code_maturity           (present)
2. quality_evidence        (present)
3. partner_validation      (present)
4. regulatory              (present)
5. workflow_closure        (present)
6. security                (MISSING — add in Gate 4)
7. delivery                (MISSING — add in Gate 4)
```

The 2 missing axes are required because:

- **security** — without it, scenarios like CN-01 (Medical Coding
  production) cannot express the A0-P0-016/017/020 security gaps
  that block production. A scenario can be code=L4 + quality=SMOKE_ONLY
  yet still fail maturity because security=E1.
- **delivery** — without it, scenarios cannot express the
  A0-P0-003 (no shippable deployment path) gap. A scenario can be
  code=L4 yet delivery=E0 (no deployment artifact).

Gate 4 will populate the 2 new axes for all 16 scenarios with
evidence-graded rationales.

---

## §7. Evidence manifest defects (output 20)

### Output 20 — Empty-directory semantics errors

`reports/comprehensive-audit/phase-a0.1/evidence_manifest.v2_1.json`:

The current schema uses `exists=false + capture_status=NOT_CAPTURED`
for empty directories. This is semantically wrong per Phase A0.1R
charter §3.Gate5:

- An empty directory that **exists on disk** must be recorded as
  `exists=true + artifact_count=0`.
- `exists=false` must mean the directory itself was never created.

Affected entries (sampled; full list to be enumerated in Gate 5):

| path | current | corrected |
|---|---|---|
| `phase7/gate13a/test-results/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0 |
| `phase7/gate13a/screenshots/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0 |
| `phase7/gate13a/playwright-traces/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0 |
| `phase7/gate13a/sanitized-har/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0 |
| `phase7/gate13a/network-audit/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0 |
| `phase7/gate13a/storage-audit/` | exists=false, NOT_CAPTURED | exists=true, artifact_count=0 |
| `evidence/architecture/` | exists=false, NOT_POPULATED | exists=true, artifact_count=0 |

**7+ entries** with wrong empty-dir semantics. Gate 5 will also add
the `storage_mode` field (default `SPLIT_PUBLIC_RESTRICTED`) per
charter §3.Gate5.

---

## §8. Validator V2 defect-coverage gaps (output 21)

### Output 21 — Validator V2 miss list

`scripts/audit/validate_phase_a0_1.py` reports `55/55 PASS`. The
following defect classes **visible in this Gate 0** are NOT caught
by validator V2:

| # | Defect class | Example | Validator V3 addition |
|---|---|---|---|
| 1 | primary_phase_mapping `explicit_ids` incomplete vs per-issue field | A0-P0-021 missing from A2 list | Cross-check: every OPEN issue's `primary_phase` value appears in `primary_phase_mapping[<phase>].explicit_ids` |
| 2 | Workstream placement mistakes (security vs legal vs ops) | A0-P0-023/024 in security, should be ops | Domain-keyword check: titles containing "backup"/"rollback"/"upgrade" must not be in A1_security_first |
| 3 | Symmetric parity threshold for CORTI_ADVANTAGE | F-03 at E1 | Apply identical threshold logic to CORTI_ADVANTAGE as to ICODER_ADVANTAGE |
| 4 | Illegal parity status outside allowed list | D-05 ICODER_TECH_DEBT | Synchronize validator's allowed-status set with matrix's `allowed_statuses` field |
| 5 | 7-axis maturity completeness | 16/16 missing security+delivery | Require security + delivery keys on every scenario |
| 6 | Empty-directory semantics | exists=false for existing dirs | Require `artifact_count` field when `path` ends in `/` |
| 7 | Secret plain-text in audit reports | secret appears in 2 .md files | Grep audit-report directory for the secret pattern |
| 8 | Annotated tag existence | tag `audit/phase-a0.1-baseline` not created | `git tag -l 'audit/phase-a0.1r-baseline'` must return exactly one entry |
| 9 | Commit A/B/C existence | none of the 3 commits exist | `git log --oneline` must contain 3 distinct commit subjects matching the canonical strings |
| 10 | Roadmap arithmetic (P0 sum) | ledger claims 23, actual 22 | Re-derive `severity_counts_normalized.open_by_severity` from array; require exact match |

**Net validator expansion**: 55 checks → ≥65 checks. Gate 7 will
also add **negative fixtures** (inject each defect, prove validator
fails) per charter §3.Gate7.

---

## §9. Bucket D decision matrix (output 22)

### Output 22 — Charter-mandated Bucket D dispositions

Phase A0.1R charter §3.Gate6 prescribes defaults; Gate 6 will
execute them. Reproduced here as the locked Gate 0 reference:

| Item | Default disposition | Mechanism |
|---|---|---|
| `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` | IGNORE (specific path) | Add `packages/icoder-sdk/*.tgz` to `.gitignore` (NOT global `*.tgz`) |
| `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` | IGNORE (specific path) | Add `packages/icoder-embedded/*.tgz` to `.gitignore` |
| `packages/icoder-sdk/dist/` (7 files) | SOURCE_ONLY_AND_REBUILD | Add `packages/icoder-sdk/dist/` to `.gitignore`; document rebuild command |
| `phase7-external-consumer/dist/` | SOURCE_ONLY_AND_REBUILD | Add `phase7-external-consumer/dist/` to `.gitignore` |
| `packages/icoder-embedded/dist/` (4 files) | KEEP_HISTORICALLY_TRACKED | Already in git index; keep modified versions in Commit A |
| `packages/icoder-sdk/package-lock.json` | ACCEPT DELETION | Stage the deletion in Commit A |
| 35 stray `*.png` at repo root | MOVE_AND_REDACT | Move under `reports/comprehensive-audit/evidence/screenshots/`; capture SHA-256; redact PII/secrets/session tokens |

**Charter constraint honored**: global `*.tgz` is NOT used (would
break test fixtures that commit legitimate tarballs).

---

## §10. Validator V3 negative-fixture plan (output 23)

### Output 23 — Negative fixtures Gate 7 must create

For each defect class in §8 above, Gate 7 produces a fixture that
provokes a validator FAIL. The fixture is a JSON file under
`scripts/audit/negative_fixtures/` with the defect injected. The
validator is invoked against each fixture and **must exit non-zero**.

| Fixture | Defect injected | Expected validator exit |
|---|---|---|
| `nf01_primary_phase_incomplete.json` | A0-P0-021 removed from A2_commercial_deferred.explicit_ids | non-zero |
| `nf02_workstream_misplacement.json` | A0-P0-023 primary_phase set to A1_security_first | non-zero |
| `nf03_corti_advantage_low_evidence.json` | F-03 left at CORTI_ADVANTAGE with corti_evidence_grade=E1 | non-zero |
| `nf04_illegal_parity_status.json` | D-05 left at ICODER_TECH_DEBT | non-zero |
| `nf05_missing_security_axis.json` | A scenario missing the `security` axis | non-zero |
| `nf06_empty_dir_wrong_semantics.json` | `evidence/architecture/` marked exists=false | non-zero |
| `nf07_secret_in_audit_report.md` | A markdown file containing the secret pattern | non-zero |
| `nf08_tag_missing.git` | No `audit/phase-a0.1r-baseline` tag | non-zero |
| `nf09_commit_missing.git` | Commit B subject not matching canonical | non-zero |
| `nf10_ledger_count_drift.json` | P0_aggregate_open claim of 23 with actual 22 | non-zero |

Negative fixtures live alongside the validator; CI in Phase A1A
will run them as part of every commit gate.

---

## §11. Phase A0.1R remediation roadmap (outputs 24–25)

### Output 24 — Gate 1–9 deliverables preview

| Gate | Deliverable | Hard checkpoint |
|---|---|---|
| 1 | `A0_1R_01_CREDENTIAL_CONTAINMENT_AND_REDACTION.md` + sanitized files | A: Credential Contained |
| 2 | `A0_1R_02_ROADMAP_RECONCILIATION.md` + `issue_ledger.v2_1.json` | (none, internal) |
| 3 | `A0_1R_03_PARITY_V2_3.md` + `parity_matrix_v2_3.json` | (none, internal) |
| 4 | `A0_1R_04_MATURITY_V3_7_AXIS.md` + `product_maturity_v3.json` | (none, internal) |
| 5 | `A0_1R_05_MANIFEST_V2_2.md` + `evidence_manifest.v2_2.json` | (none, internal) |
| 6 | `A0_1R_06_BUCKET_D_CLOSURE.md` + `.gitignore` patches + relocated screenshots | B: Bucket D Closed |
| 7 | `A0_1R_07_VALIDATOR_V3_WITH_NEGATIVE_FIXTURES.md` + `validate_phase_a0_1r.py` + 10 fixtures | C: Validator V3 Green |
| 8 | `A0_1R_08_BRANCH_AND_COMMIT_A.md` + Commit A on branch `audit/phase-a0.1r-freeze` + regression PASS | D: Commit A Immutable |
| 9 | `A0_1R_09_COMMIT_B_C_TAG_AND_POST_TAG_VALIDATION.md` + Commit B + Commit C + annotated tag + post-tag validator PASS | E–J: Baseline Immutable |

### Output 25 — Hard checkpoint map (A–J)

| Checkpoint | Gate | Description | Required state at Gate 0 close |
|---|---|---|---|
| A | 1 | Credentials contained | NOT YET — secret still in 3 files |
| B | 6 | Bucket D closed | NOT YET — 35 PNGs at root, tarballs undecided |
| C | 7 | Validator V3 green | NOT YET — validator V2 still in place |
| D | 8 | Commit A on branch; regression PASS | NOT YET — no branch, no commit |
| E | 9 | Commit B (audit package) | NOT YET |
| F | 9 | Commit C (freeze receipt) | NOT YET |
| G | 9 | Annotated tag | NOT YET — no tag exists |
| H | 9 | Post-tag validator PASS | NOT YET — no tag to validate against |
| I | 9 | Immutable baseline established | NOT YET — tag is the immutability anchor |
| J | 9 | Phase A1A entry unlocked | NOT YET — depends on I |

---

## §12. Phase A0.1R forbidden-actions register (output 26)

### Output 26 — Forbidden actions during Phase A0.1R

Reproduced from charter §6. The Gate 0 state honors every item;
Gate 1+ continues to honor items marked "permanent".

| # | Forbidden action | Duration |
|---|---|---|
| 1 | `git push` to any remote | Permanent (within A0.1R) |
| 2 | Open a pull request | Permanent |
| 3 | `npm publish` to public registry | Permanent |
| 4 | Create new agents / experts / tools / runtimes | Permanent |
| 5 | Modify Medical Coding prompts | Permanent |
| 6 | Modify CDI prompts | Permanent |
| 7 | `git add -A` or `git add .` (bulk staging) | Permanent |
| 8 | Commit on `master` | Permanent (commits go on `audit/phase-a0.1r-freeze`) |
| 9 | Submit `.audit-chrome-profile/` contents | Permanent |
| 10 | Submit a valid `.env` file | Permanent |
| 11 | Submit secrets / PHI / PII to git | Permanent |
| 12 | Use `BASELINE_FROZEN` in any verdict before Commit B + tag exist | Permanent |
| 13 | Output the final PASS verdict before post-tag validation PASS | Permanent |
| 14 | Modify Phase A0.1 artifacts beyond what Gates 1–7 prescribe | Permanent (scope-of-work constraint) |
| 15 | Inherit `PASS_PHASE_A0_1_*` verdict | Permanent (charter §3) |

---

## §13. Phase A0.1R entry-state verdict (output 27)

### Output 27 — Entry-state verdict for Phase A0.1R

```
PHASE_A0_1_R_GATE_0_PREFLIGHT_AND_DEFECT_REPRODUCTION_COMPLETE
```

Sub-state:

```
ENTRY_STATE =
  AUDIT_REPAIR_SUBSTANTIALLY_COMPLETE +
  IMMUTABLE_FREEZE_NOT_EXECUTED +
  CREDENTIAL_COMPROMISED_WORKING_TREE_ONLY +
  CREDENTIAL_NEVER_IN_GIT_HISTORY +
  COMMITS_A_B_C_NOT_CREATED +
  ANNOTATED_TAG_NOT_CREATED +
  ROADMAP_RECONCILIATION_PENDING +
  PARITY_V2_3_PENDING +
  MATURITY_V3_PENDING +
  MANIFEST_V2_2_PENDING +
  BUCKET_D_CLOSURE_PENDING +
  VALIDATOR_V3_PENDING +
  REGRESSION_ON_BRANCH_PENDING +
  POST_TAG_VALIDATION_PENDING

INHERITED_VERDICT =
  NONE  (PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1
         is REFUTED; Phase A0.1R does not inherit it)

ALLOWED_NEXT_VERDICT (Gate 1) =
  PHASE_A0_1_R_GATE_1_CREDENTIAL_CONTAINED_AND_REDACTED
  or
  PARTIAL_BLOCKED_BY_COMPROMISED_CREDENTIAL_NOT_INVALIDATED
```

---

## §14. What Gate 0 did NOT do

- ❌ Did NOT modify product code
- ❌ Did NOT modify audit reports (Phase A0.1 v1/v2 artifacts untouched)
- ❌ Did NOT create any branch (stay on master until Gate 8)
- ❌ Did NOT create any commit
- ❌ Did NOT create any tag
- ❌ Did NOT push
- ❌ Did NOT publish
- ❌ Did NOT invalidate the compromised credential (Gate 1's job)
- ❌ Did NOT move any screenshot (Gate 6's job)
- ❌ Did NOT modify `.gitignore` (Gate 6's job)
- ❌ Did NOT run the validator (Gate 7's job to install V3)
- ❌ Did NOT inherit `PASS_PHASE_A0_1_*`

---

## §15. Findings raised in Gate 0

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G0-001** | P0 (process) | Phase A0.1 Gate 9 verdict claimed `BASELINE_FROZEN` without creating any commit or tag. Verified via `git log --all --grep` and `git tag -l` — both empty. |
| **A0.1R-G0-002** | P0-S | Compromised credential `[REDACTED_COMPROMISED_API_CLIENT_SECRET]` (sha256 `7a3b25ef...`) appeared in plain text in 3 working-tree files. Never committed (0 hits in `git log --all -p`). Redacted in Phase A0.1R Gate 1. |
| **A0.1R-G0-003** | P0 (data) | Ledger P0-S_open claim of 11 doesn't match array (10 OPEN). Aggregate P0_open claim of 23 doesn't match (22 OPEN or 24 with MITIGATED). |
| **A0.1R-G0-004** | P0 (data) | `primary_phase_mapping.A2_commercial_deferred.explicit_ids` missing A0-P0-021 (per-issue tag includes it). |
| **A0.1R-G0-005** | P0 (data) | Workstream misplacement: A0-P0-001/002 (legal) in security; A0-P0-008 (run_trace store) in commercial; A0-P0-023/024 (ops) in security. |
| **A0.1R-G0-006** | P1 | Parity D-05 carries illegal status `ICODER_TECH_DEBT` (not in `allowed_statuses`). |
| **A0.1R-G0-007** | P0 (data) | 4 CORTI_ADVANTAGE dimensions (F-03/04/07/08) at corti_evidence_grade=E1 violate the E7 security-advantage threshold. |
| **A0.1R-G0-008** | P1 | Maturity matrix has 5 axes; spec requires 7 (security + delivery missing on 16/16 scenarios). |
| **A0.1R-G0-009** | P2 | Evidence manifest uses `exists=false` for existing-but-empty directories. 7+ entries affected. |
| **A0.1R-G0-010** | P1 | Validator V2 (55/55 PASS) misses 10 defect classes visible at Gate 0. Negative fixtures absent. |
| **A0.1R-G0-011** | P2 | 35 stray `*.png` at repo root; not gitignored. Risk of accidental commit. |
| **A0.1R-G0-012** | P2 | Billing Theater (A0-P0-004) must split: Product Truth portion → A1_product_truth_minimal; Commercial Capability portion → parallel commercial track. |
| **A0.1R-G0-013** | P2 | npm framing (A0-P0-009) must reframe to `NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL`. Public npm must NOT be default P0. |
| **A0.1R-G0-014** | P2 | CDI Research Mode must be bounded (restricted scope, no auto-send, no auto-writeback, NOT Workflow Closed). |
| **A0.1R-G0-015** | P3 | Annotated tag naming: Phase A0.1 used `audit/phase-a0.1-baseline`; Phase A0.1R will use `audit/phase-a0.1r-baseline` to avoid collision if Phase A0.1's tag is later force-created. |

---

## §16. Gate 0 hard checkpoint

There is no hard checkpoint at Gate 0 — Gate 0 produces no commits,
no tags, no mutations. Gate 0's deliverable is **this document**
plus the machine-readable preflight snapshot below.

## §17. Machine-readable preflight snapshot

Phase A0.1R Gates 1–9 will read this snapshot as the authoritative
entry state. Saved as
`reports/comprehensive-audit/phase-a0.1r/evidence/gate0_preflight_snapshot.json`
in Gate 1 (Gate 0 itself stays read-only and does not write JSON).

```json
{
  "phase": "A0.1R",
  "gate": 0,
  "verdict": "PHASE_A0_1_R_GATE_0_PREFLIGHT_AND_DEFECT_REPRODUCTION_COMPLETE",
  "trusted_head": "c147d015455017bc1d8420cbdbd813b3b8ec23ce",
  "branch": "master",
  "remote": "https://github.com/EtherumFans/agentinfra.git",
  "inherited_verdict": "REFUTED",
  "commits_existing": {
    "commit_a_bucket_a": false,
    "commit_b_audit_package": false,
    "commit_c_freeze_receipt": false
  },
  "tags_existing": {
    "audit/phase-a0.1-baseline": false,
    "audit/phase-a0.1r-baseline": false
  },
  "compromised_credential": {
    "in_git_history": false,
    "git_history_hit_count": 0,
    "working_tree_files": [
      "examples/partner-reference-app/.env",
      "reports/comprehensive-audit/phase-a0.1/A0_1_01_AUDITED_FILESET_AND_BASELINE_SNAPSHOT.md",
      "reports/comprehensive-audit/phase-a0.1/A0_1_09_SAFE_COMMIT_AND_IMMUTABLE_FREEZE.md"
    ],
    "redaction_token": "[REDACTED_COMPROMISED_API_CLIENT_SECRET]"
  },
  "browser_profile": {
    "gitignored": true,
    "gitignore_line": 127,
    "entries_on_disk": 42
  },
  "bucket_d": {
    "tarballs": [
      "packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz",
      "packages/icoder-embedded/icoder-embedded-2.0.0.tgz"
    ],
    "dist_directories": [
      "packages/icoder-sdk/dist/",
      "packages/icoder-embedded/dist/",
      "phase7-external-consumer/dist/"
    ],
    "root_png_count": 35,
    "deletions": [
      "packages/icoder-sdk/package-lock.json"
    ]
  },
  "ledger_defects": {
    "p0_aggregate_open_claim": 23,
    "p0_aggregate_open_actual_strict_open": 22,
    "p0_aggregate_open_actual_open_plus_mitigated": 24,
    "p0_s_open_claim": 11,
    "p0_s_open_actual": 10,
    "primary_phase_mapping_explicit_ids_incomplete": [
      "A0-P0-021"
    ],
    "workstream_misplacements": [
      {"id": "A0-P0-001", "current": "A1_security_first", "correct": "A1_legal_compliance"},
      {"id": "A0-P0-002", "current": "A1_security_first", "correct": "A1_legal_compliance"},
      {"id": "A0-P0-008", "current": "A2_commercial_deferred", "correct": "A1_security_first"},
      {"id": "A0-P0-023", "current": "A1_security_first", "correct": "A1_deployment_ops"},
      {"id": "A0-P0-024", "current": "A1_security_first", "correct": "A1_deployment_ops"}
    ]
  },
  "parity_defects": {
    "illegal_status_dimensions": [{"id": "D-05", "status": "ICODER_TECH_DEBT"}],
    "corti_advantage_threshold_failures": [
      {"id": "F-03", "name": "HIPAA", "corti_grade": "E1", "threshold": "E7"},
      {"id": "F-04", "name": "ISO 27001", "corti_grade": "E1", "threshold": "E7"},
      {"id": "F-07", "name": "Multi-region failover", "corti_grade": "E1", "threshold": "E7"},
      {"id": "F-08", "name": "Edge-node PHI redaction", "corti_grade": "E1", "threshold": "E7"}
    ]
  },
  "maturity_defects": {
    "required_axes": 7,
    "actual_axes": 5,
    "missing_axes": ["security", "delivery"],
    "scenarios_missing_security_axis": "16/16",
    "scenarios_missing_delivery_axis": "16/16"
  },
  "manifest_defects": {
    "empty_dir_semantics_errors": [
      "phase7/gate13a/test-results/",
      "phase7/gate13a/screenshots/",
      "phase7/gate13a/playwright-traces/",
      "phase7/gate13a/sanitized-har/",
      "phase7/gate13a/network-audit/",
      "phase7/gate13a/storage-audit/",
      "evidence/architecture/"
    ],
    "missing_storage_mode_field": true
  },
  "validator_v2": {
    "current_checks": 55,
    "current_passes": 55,
    "misses_defect_classes": 10
  },
  "hard_checkpoints": {
    "A": "NOT_CLOSED",
    "B": "NOT_CLOSED",
    "C": "NOT_CLOSED",
    "D": "NOT_CLOSED",
    "E": "NOT_CLOSED",
    "F": "NOT_CLOSED",
    "G": "NOT_CLOSED",
    "H": "NOT_CLOSED",
    "I": "NOT_CLOSED",
    "J": "NOT_CLOSED"
  },
  "forbidden_actions_register_size": 15
}
```

---

## §18. Gate 0 verdict

```
PHASE_A0_1_R_GATE_0_PREFLIGHT_AND_DEFECT_REPRODUCTION_COMPLETE

INHERITED_VERDICT: REFUTED (PASS_PHASE_A0_1_* NOT inherited)
NEXT_GATE: GATE_1_CREDENTIAL_CONTAINMENT_AND_REDACTION
NEXT_ALLOWED_VERDICTS:
  - PHASE_A0_1_R_GATE_1_CREDENTIAL_CONTAINED_AND_REDACTED
  - PARTIAL_BLOCKED_BY_COMPROMISED_CREDENTIAL_NOT_INVALIDATED

GATE_0_IS_READ_ONLY: true
GATE_0_MUTATIONS_PERFORMED: 0
GATE_0_OUTPUTS_PRODUCED: 27
```

End of Gate 0.
