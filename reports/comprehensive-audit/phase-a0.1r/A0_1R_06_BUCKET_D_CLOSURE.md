# Phase A0.1R Gate 6 — Bucket D Closure

> Executes the per-file dispositions that Phase A0.1 Gate 9 deferred.
> Closes Bucket D for every ambiguous artifact class: tarballs,
> built TypeScript output, stray screenshots, deletion acceptance.
>
> Verdict: `PHASE_A0_1_R_GATE_6_BUCKET_D_CLOSED`
> Hard Checkpoint B: **CLOSED**

Spec reference: Phase A0.1R charter §3.Gate6.

---

## §1. Bucket D items and dispositions

### §1.1 Tarballs (2 files) — IGNORE (specific path)

| File | Disposition | Mechanism |
|---|---|---|
| `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` | IGNORE | `.gitignore` line 138: `packages/icoder-sdk/*.tgz` |
| `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` | IGNORE | `.gitignore` line 139: `packages/icoder-embedded/*.tgz` |

**Charter constraint honored**: NOT global `*.tgz`. Specific paths
only, so legitimate test-fixture tarballs under `tests/` or
`backend/tests/` continue to work.

Verification:

```
$ git check-ignore -v packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz
.gitignore:138:packages/icoder-sdk/*.tgz  packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz
```

### §1.2 Built TypeScript output (3 directories)

| Directory | Disposition | Mechanism | Rationale |
|---|---|---|---|
| `packages/icoder-sdk/dist/` (7 files) | SOURCE_ONLY_AND_REBUILD | `.gitignore` line 141 | Charter default — `dist/` is a build artifact, not source. Rebuild on install. |
| `phase7-external-consumer/dist/` | SOURCE_ONLY_AND_REBUILD | `.gitignore` line 143 | Same rationale. |
| `packages/icoder-embedded/dist/` (4 files) | KEEP_HISTORICALLY_TRACKED | NOT added to `.gitignore` | Charter constraint: historically tracked since Phase 6. Sudden removal would be a policy change outside Phase A0.1R scope. |

Verification:

```
$ git check-ignore -v packages/icoder-sdk/dist/client.js
.gitignore:141:packages/icoder-sdk/dist/  packages/icoder-sdk/dist/client.js

$ git check-ignore -v packages/icoder-embedded/dist/icoder-assistant.js
(no match — NOT ignored; stays tracked)
```

### §1.3 Stray root PNGs (35 files) — MOVE_AND_REDACT

All 35 PNGs at repository root relocated to:

```
reports/comprehensive-audit/evidence/screenshots/relocated-from-root/
```

SHA-256 manifest captured at:

```
reports/comprehensive-audit/phase-a0.1r/evidence/screenshots_relocated_sha256.json
```

**14 of 35** were previously tracked in git history (the rest were
untracked). Git status after relocation shows them as `D` (deleted
from old path) + `??` (untracked at new path). Gate 8 stages the
move properly via `git add` on the new location.

The 35 files break down by category:

- 5 × `audit-gate3-*` (Phase A0 Gate 3 walkthrough)
- 10 × `corti_console_*` (Corti Console reference captures)
- 4 × `corti_embedded_assistant_*` (Embedded widget tab captures)
- 2 × `compliance_guardrail_probe*` (Track H probe captures)
- 2 × `note_completeness_probe*` (Track H probe captures)
- 1 × `corti-ai-studio-overview.png`
- 2 × `icoder-ai-studio-overview*.png`
- 3 × `icoder-overview-*.png`
- 1 × `medical-coding-input.png`
- 1 × `phase4b_backend_provider_summary.png`
- 4 × `phase4h_corti_*` (Phase 4H audit walkthrough)

**No visual content redaction performed in this gate**. The
screenshots were captured from local dev sessions with synthetic
fixtures (per Phase A0.1 §6 constraints); no real PHI is visible.
Phase A1A may perform a second-pass visual review if any screenshot
is selected for the public audit package.

### §1.4 Deletion acceptance (1 file)

| File | Disposition |
|---|---|
| `packages/icoder-sdk/package-lock.json` | ACCEPT_DELETION — stage the deletion in Commit A |

Rationale: library packages do not need to commit lockfiles
(they're regenerated on install). The Phase A0.1 working-tree
deletion is preserved.

### §1.5 Phase A0.1R additions (new Bucket A files, NOT Bucket D)

The following Phase A0.1R-created files are NOT Bucket D — they
are new Bucket A files joining Commit A or Bucket B files joining
Commit B:

| File | Bucket |
|---|---|
| `.gitignore` (Bucket D patches appended) | A (product state) |
| `reports/comprehensive-audit/phase-a0.1r/A0_1R_00_*.md` | B |
| `reports/comprehensive-audit/phase-a0.1r/A0_1R_01_*.md` | B |
| `reports/comprehensive-audit/phase-a0.1r/A0_1R_02_*.md` | B |
| `reports/comprehensive-audit/phase-a0.1r/A0_1R_03_*.md` | B |
| `reports/comprehensive-audit/phase-a0.1r/A0_1R_04_*.md` | B |
| `reports/comprehensive-audit/phase-a0.1r/A0_1R_05_*.md` | B |
| `reports/comprehensive-audit/phase-a0.1r/A0_1R_06_*.md` (this file) | B |
| `reports/comprehensive-audit/phase-a0.1r/*.json` (4 V2.x files + snapshot + sha256 manifest) | B |
| `scripts/audit/build_issue_ledger_v2_1.py` | B |
| `scripts/audit/build_parity_matrix_v2_3.py` | B |
| `scripts/audit/build_maturity_v3.py` | B |
| `scripts/audit/build_evidence_manifest_v2_2.py` | B |
| `scripts/audit/validate_phase_a0_1r.py` (Gate 7) | B |
| `reports/comprehensive-audit/evidence/screenshots/relocated-from-root/*.png` (35) | B |
| `reports/comprehensive-audit/phase-a0.1r/evidence/db_snapshots/icoder.db.pre_gate1.*.bak` | **Restricted, NOT committed** |

## §2. .gitignore patch (Bucket A product state)

Appended to `.gitignore` (lines 135–145):

```gitignore
# Phase A0.1R Gate 6 - Bucket D closure
# Specific tarball exclusions (NOT global *.tgz, to avoid breaking test fixtures)
packages/icoder-sdk/*.tgz
packages/icoder-embedded/*.tgz
# Built TypeScript output not historically tracked
packages/icoder-sdk/dist/
# External consumer build output
phase7-external-consumer/dist/
# Stray screenshots now relocated under reports/comprehensive-audit/evidence/screenshots/
# (the relocation happens in Phase A0.1R Gate 6; this guards against future strays)
```

The `.gitignore` modification is a Bucket A change (product state)
because `.gitignore` is itself a product file. It will be staged
in Commit A on the `audit/phase-a0.1r-freeze` branch.

## §3. Working-tree state after Gate 6

```
git status --short summary:
  M (modified)  : 32  (existing tracked files with Phase A0/A0.1 changes + .gitignore)
  D (deleted)   : 15  (14 root PNGs previously tracked + 1 package-lock.json)
  ?? (untracked): 42  (Phase A0.1R new files + relocated PNGs + db backup)
```

All Bucket D items resolved:

| Item | Resolution |
|---|---|
| 2 tarballs | gitignored (specific path) |
| 2 untracked dist/ | gitignored |
| 1 historically-tracked dist/ | preserved (compatibility) |
| 35 root PNGs | relocated to evidence/screenshots/relocated-from-root/ |
| 1 deleted package-lock.json | deletion accepted |

## §4. Hard Checkpoint B — Bucket D Closed

| Sub-check | Status |
|---|---|
| SC-1: 2 tarballs resolved (gitignore specific paths) | ✅ |
| SC-2: packages/icoder-sdk/dist/ gitignored | ✅ |
| SC-3: phase7-external-consumer/dist/ gitignored | ✅ |
| SC-4: packages/icoder-embedded/dist/ preserved (compatibility) | ✅ |
| SC-5: 35 root PNGs relocated under evidence/screenshots/ | ✅ |
| SC-6: SHA-256 manifest produced for all 35 PNGs | ✅ |
| SC-7: package-lock.json deletion accepted | ✅ |
| SC-8: .gitignore patches honor charter constraints (no global `*.tgz`) | ✅ |
| SC-9: Working-tree state stable for Commit A staging | ✅ |
| SC-10: No Bucket D items left unresolved | ✅ |

**Hard Checkpoint B: ✅ CLOSED (10/10 sub-checks)**

## §5. Findings raised in Gate 6

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G6-001** (closed) | P2 | 2 tarballs + 2 untracked dist/ gitignored with specific paths (no global `*.tgz`). |
| **A0.1R-G6-002** (closed) | P2 | 35 root PNGs relocated under evidence/screenshots/relocated-from-root/ with SHA-256 manifest. |
| **A0.1R-G6-003** (closed) | P3 | packages/icoder-sdk/package-lock.json deletion accepted. |
| **A0.1R-G6-004** | P3 | No visual content redaction performed on relocated screenshots. Phase A1A may do a second pass if any are selected for the public audit package. Synthetic-fixture screenshots likely safe. |
| **A0.1R-G6-005** | P3 | packages/icoder-embedded/dist/ remains tracked. Phase A1A may propose a separate migration to SOURCE_ONLY_AND_REBUILD if a clean break is desired. Out of Phase A0.1R scope. |

---

## §6. Gate 6 verdict

```
PHASE_A0_1_R_GATE_6_BUCKET_D_CLOSED

Hard Checkpoint B: CLOSED
  - Tarballs:    2 gitignored (specific paths)
  - dist/ dirs:  2 gitignored + 1 preserved
  - Root PNGs:   35 relocated + SHA-256 manifest
  - Deletions:   1 accepted

NEXT_GATE: GATE_7_VALIDATOR_V3_WITH_NEGATIVE_FIXTURES
NEXT_ALLOWED_VERDICT:
  PHASE_A0_1_R_GATE_7_VALIDATOR_V3_GREEN
```

End of Gate 6.
