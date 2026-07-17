# Phase A0.1 Gate 9 — Safe Commit and Immutable Freeze

> Produces the immutable git baseline required for Phase A1 entry.
> Two surgical commits (no `git add -A`) + one annotated tag. NO push.
> NO npm publish. NO PR. Local freeze only.

Spec reference: Phase A0.1 §三 Gate 9, §六 (forbidden actions).

---

## §1. What this gate produces

| Artifact | Purpose |
|----------|---------|
| Commit A `audit/phase-a0.1: audited product snapshot (Bucket A)` | Anchors the product substrate the audit opines about |
| Commit B `audit/phase-a0.1: audit package (Bucket B) + immutable baseline freeze` | The audit deliverables themselves |
| Annotated tag `audit/phase-a0.1-baseline` | Points at Commit B HEAD; carries the final verdict in its message |
| Executable script `scripts/audit/stage_phase_a0_1_commit.sh` | Reproducible staging; supports `--dry-run` |

After Gate 9, the repository satisfies
`REPRODUCIBLE_AUDITED_PRODUCT_BASELINE = ESTABLISHED` (the property
Gate 1 could not establish alone).

## §2. Pre-condition checks (all must pass before staging)

The script verifies all four before touching the index:

1. **HEAD == trusted commit.** `git rev-parse HEAD` must equal
   `c147d015455017bc1d8420cbdbd813b3b8ec23ce`. If HEAD drifts, abort.
2. **Branch == master.** Refuses to run on a feature branch.
3. **Semantic validator PASS.** `python scripts/audit/validate_phase_a0_1.py`
   must exit 0. Re-runs every time; catches regressions introduced
   between Gate 8 and Gate 9.
4. **No forbidden actions taken.** Read-only check: no push, no npm,
   no PR. (The script itself does not push; the check is structural.)

## §3. Bucket A — Audited Product (~70 files)

Staged via explicit `git add <file>` per file. **No `git add -A`.**
**No `git add reports/comprehensive-audit/`** in Commit A.

Categories (per Gate 1 §4):

| Category | Count | Notes |
|----------|------:|-------|
| Modified backend code | 9 | agent_run / embedded / platform_api_clients / usage / main / auth middleware / 3 models |
| Modified backend tests | 2 | conftest + test_phase4f |
| New alembic migrations | 4 | 012 idempotency / 013 run_history status+cancel / 014 api_client attribution / 015 preview_sessions |
| New backend services + middleware + models + api | 10 | examples / preview_sessions / runs / partner_cors / idempotency_record / preview_session / idempotency_service / preview_ticket / run_lifecycle / trace_token |
| New backend tests (Phase 7) | 13 | Gates 1, 3, 4, 5, 6, 7, 8, 9, 13A (5 files) |
| Frontend | 5 | EmbeddedAssistantPage + App + Layout + locales + e2e test |
| packages/icoder-embedded | 9 | dist (2) + package.json + src + demos (5) |
| packages/icoder-sdk | 12 | README + package.json + 8 resources + client + index + tsconfig + 1 new (runs.ts) |
| packages/icoder-sdk deletion | 1 | package-lock.json removed |
| examples/partner-reference-app | 6 | .env.example + 5 source files |
| phase7-external-consumer | 7 | harness without dist/ or node_modules/ |
| DEPRECATED.md markers | 3 | icoder-web + web-components (packages/) + web-components (root) |

**Bucket A excludes:**

- `examples/partner-reference-app/.env` (Bucket C — gitignored, contains real-looking secret; **rotate before any push**)
- `backend/.env` (Bucket C — gitignored, placeholder secret)
- `packages/icoder-sdk/dist/` (Bucket D — reproducibility TBD)
- `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` (Bucket D)
- `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` (Bucket D)
- `phase7-external-consumer/dist/` (Bucket D)

## §4. Bucket B — Audit Package

| Path | Contents |
|------|----------|
| `reports/comprehensive-audit/phase-a0.1/` | All 9 gate markdown reports + 5 JSON deliverables + gate0_findings.json |
| `reports/comprehensive-audit/evidence/git/phase_a0_commands/` | 3 git command output files with real SHA-256 |
| `scripts/audit/validate_phase_a0_1.py` | Canonical machine-verifier |
| `scripts/audit/build_parity_v2_2.py` | Build script for parity V2.2 (reproducibility) |
| `scripts/audit/build_maturity_v2.py` | Build script for maturity V2 |
| `scripts/audit/stage_phase_a0_1_commit.sh` | This gate's executable |

**Bucket B does NOT modify** `reports/comprehensive-audit/phase-a0/`
or any prior-phase audit directory. Those are preserved as audit trail.

## §5. Bucket C — Unsafe (NEVER staged)

| Path | Reason |
|------|--------|
| `backend/.env` | Contains `SECRET_KEY=change-me-in-production`. Gitignored. Action: ship `.env.example` (in Bucket A) + add startup sentinel (A1 work). |
| `examples/partner-reference-app/.env` | Contained `ICODER_API_CLIENT_SECRET=[REDACTED_COMPROMISED_API_CLIENT_SECRET]` (plain-text secret invalidated in Phase A0.1R Gate 1). Gitignored. Working-tree exposure to audit tooling counted as compromise; secret rotated + client deactivated. |
| `.audit-chrome-profile/` | Full Chrome user-data-dir (2030 files). Gitignored. |
| `audit-gate3-*.png`, `corti_console_*.png`, `corti_embedded_assistant_*.png` (21 files at repo root) | Stray screenshots. Not gitignored. Action: move to `reports/comprehensive-audit/evidence/` (with hashes) or delete. **Do not commit from repo root.** |

The staging script does not add any of these. The `.gitignore`
covers `.env*` and `.audit-chrome-profile/`; the PNG files are an
ongoing hygiene issue (A0.1-G1-004) — they sit at repo root and
would be caught by a careless `git add *.png`. Phase A1 must decide.

## §6. Bucket D — Ambiguous (DEFERRED to per-file decision)

These need a reproducibility decision before joining Commit A.
Gate 9 explicitly defers them; the staging script does not add them.

| Path | Concern | Recommended resolution |
|------|---------|------------------------|
| `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` | Opaque binary tarball; build reproducibility unverified | Either commit + document build seed/toolchain, OR extend `.gitignore` to exclude `*.tgz` |
| `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` | Same | Same |
| `packages/icoder-sdk/dist/` (7 files) | Built TS output; NOT covered by existing `.gitignore` `sdk/dist/` pattern (legacy path) | Either commit (treat as released artifact) OR extend `.gitignore` to `packages/*/dist/` |
| `phase7-external-consumer/dist/` | Built output | Same as above |

The deferral is documented in
`reports/comprehensive-audit/phase-a0.1/A0_1_09_BUCKET_D_DEFERRED.md`
(see §10 below for the abbreviated form). Phase A1 P0 must close
each deferred item with an explicit commit / ignore / regenerate
decision.

## §7. Annotated tag — `audit/phase-a0.1-baseline`

Created on Commit B HEAD. Message carries the verdict:

```
Phase A0.1 - Audit Repair and Immutable Baseline Freeze

Establishes the REPRODUCIBLE_AUDITED_PRODUCT_BASELINE required for
Phase A1 entry.

Verdict: PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1

Validator: PASS_PHASE_A0_1_SEMANTIC_VALIDATOR_V2 (55/55 checks).
Issue ledger: 86 canonical / 79 open (machine-derived).
Parity matrix: 59 dimensions (machine-derived).
Product maturity: 16 scenarios × 5 axes; 0 at L7+; 0 with formal benchmark.
Roadmap: A1=19 P0 / A2=22 P1 + 4 P0-commercial-deferred / A3=27 P2 / A4=11 P3.

Phase A0 v1 PASS_PHASE_A0_* verdict REFUTED (7 findings in Gate 0).
Phase A0 v1 artifacts PRESERVED (not modified) as audit trail.

NO push. NO npm publish. NO PR. Local freeze only.
```

Annotated (`-a`) not lightweight — the message is part of the tag
object hash, so any tampering invalidates the tag.

## §8. Forbidden actions (per Phase A0.1 §六)

| Action | Status |
|--------|--------|
| Push to remote | ❌ FORBIDDEN |
| Publish to npm | ❌ FORBIDDEN |
| Create PR | ❌ FORBIDDEN |
| Modify product code | ❌ FORBIDDEN (read-only audit repair) |
| `git add -A` | ❌ FORBIDDEN |
| `git add reports/comprehensive-audit/` (bulk) | ❌ FORBIDDEN |
| Tag lightweight (no `-a`) | ❌ FORBIDDEN |
| Inherit Phase A0 PASS verdict | ❌ FORBIDDEN |

The staging script respects every constraint. After Gate 9 closes,
the local repo is in the immutable baseline state; remote-side
actions are a separate business decision.

## §9. Hard Checkpoint — Safe Commit (provisional)

| Sub-check | Status |
|-----------|--------|
| SC-1: validator PASS as pre-condition | ✅ dry-run executed; 55/55 checks |
| SC-2: HEAD == trusted commit | ✅ c147d0154... verified |
| SC-3: branch == master | ✅ |
| SC-4: staging script exists with `--dry-run` | ✅ scripts/audit/stage_phase_a0_1_commit.sh |
| SC-5: Bucket C explicitly excluded | ✅ .env files + Chrome profile + stray PNGs |
| SC-6: Bucket D deferred with rationale | ✅ §6 above + A0_1_09_BUCKET_D_DEFERRED.md |
| SC-7: annotated tag (not lightweight) | ✅ `git tag -a` |
| SC-8: no push, no npm, no PR | ✅ script does not perform these; §六 honored |

**Hard Checkpoint SC: ✅ PASS (8/8 sub-checks) provisional — final ratification when the script is actually executed and the tag is created.**

## §10. Bucket D deferred decision matrix (abbreviated)

| Path | Decision options | Default if A1 does not decide |
|------|------------------|-------------------------------|
| `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` | (a) commit + document build seed; (b) extend `.gitignore` to exclude `*.tgz` | (b) — extend `.gitignore` |
| `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` | Same | (b) |
| `packages/icoder-sdk/dist/` | (a) commit; (b) extend `.gitignore` to `packages/*/dist/` and rebuild at install | (b) — cleaner |
| `phase7-external-consumer/dist/` | Same | (b) |
| Stray `*.png` at repo root (21 files) | (a) move to `reports/comprehensive-audit/evidence/` with hashes; (b) delete | (a) — preserve audit value |

A1 entry criterion: each row gets a decision recorded in this
table before A1 P0 work begins.

## §11. Findings raised in Gate 9

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G9-001** | P0-S | `examples/partner-reference-app/.env` working tree contained `ICODER_API_CLIENT_SECRET=[REDACTED_COMPROMISED_API_CLIENT_SECRET]` (plain-text redacted in Phase A0.1R Gate 1; client deactivated + hash rotated in `backend/data/icoder.db`). Working-tree exposure to audit tooling counted as compromise; **secret invalidated before Phase A0.1R Commit A**. Stays gitignored; not part of any commit. |
| **A0.1-G9-002** | P1 | Bucket D (2 tarballs + 2 dist/ directories) cannot be staged without a reproducibility decision. Deferred to A1 entry; default resolution is `.gitignore` extension. |
| **A0.1-G9-003** | P2 | 21 stray `*.png` files at repo root are not gitignored. Risk of accidental commit via `git add *.png`. Phase A1 must either move them under `reports/comprehensive-audit/evidence/` with SHA-256 captured, or delete them. |
| **A0.1-G9-004** | P3 | The staging script's Bucket A file list is hand-maintained. If new product files land in the working tree before Gate 9 executes, they will not be auto-included. Phase A1 should consider a structured manifest (`phase-a0.1-bucket-a.manifest`) that the script reads. |

## §12. Gate 9 verdict

```
PHASE_A0_1_GATE_9_SAFE_COMMIT_AND_IMMUTABLE_FREEZE_READY
2_COMMITS_PLANNED (A product snapshot + B audit package)
1_ANNOTATED_TAG_PLANNED (audit/phase-a0.1-baseline)
0_GIT_ADD_A_USED
0_FORBIDDEN_ACTIONS
4_PRE_CONDITION_CHECKS_VERIFIED (HEAD + branch + validator + read-only)
BUCKET_C_NEVER_STAGED (8 .env + chrome-profile + 21 png)
BUCKET_D_DEFERRED (2 tarballs + 2 dist dirs + 1 png cleanup)
HARD_CHECKPOINT_SC_PROVISIONAL_PASS (8/8)
REPRODUCIBLE_AUDITED_PRODUCT_BASELINE_READY_TO_ESTABLISH
```

### Final Phase A0.1 verdict (pending Gate 9 execution)

```
PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1
```

(One of the 5 allowed verdicts per Phase A0.1 §五.)

### Phase A1 may start after:

1. `bash scripts/audit/stage_phase_a0_1_commit.sh` executed locally.
2. `git tag -l 'audit/phase-a0.1*'` shows the annotated tag.
3. `git log --oneline -3` shows Commit A and Commit B on master HEAD.
4. A1-S, A1-C, A1-D workstream owners assigned (business side).
5. Bucket D default resolutions applied or explicit decisions recorded.

**NO push required for A1 start.** A1 development is local; remote
publication is a separate business decision after A1 closes.

End of Gate 9. End of Phase A0.1.
