# Phase A0.1 Gate 9 — Bucket D Deferred Decision Matrix

> Bucket D from Gate 1 = "Ambiguous, needs per-file decision before
> Gate 9 staging". Gate 9 explicitly defers these. This file is the
> decision matrix A1 P0 must close.

Spec reference: Phase A0.1 Gate 9 §6.

---

## §1. Why Bucket D exists

Four kinds of artifacts sit in the working tree that are neither
clearly safe-to-commit (Bucket A) nor clearly never-commit (Bucket C):

1. **Opaque binary tarballs** — `*.tgz` build outputs whose SHA-256
   depends on build inputs and toolchain versions that are not
   documented. If the inputs drift between commits, the SHA-256
   drifts and the manifest breaks.
2. **Built TypeScript output** — `dist/` directories. Some are
   covered by existing `.gitignore` patterns; some are not because
   the pattern was written for a legacy path that no longer exists.
3. **Stray PNG files at repo root** — not gitignored, but never
   meant to be committed.

Bucket D's defining property: each item is a real artifact on disk
(reproducibility is the question, not existence), and the right
answer depends on a per-file product decision.

## §2. Decision matrix

### D-1: `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz`

| | |
|---|---|
| **Size** | ~30 KB |
| **What it is** | npm tarball produced by `npm pack` from `packages/icoder-sdk/` |
| **Current state** | Untracked (not in git index) |
| **Reproducibility concern** | Build seed + toolchain versions not documented; SHA-256 drifts if `package-lock.json` changes |
| **Option A** | Commit. Document build seed (`npm pack --dry-run` output) + Node version + npm version. Add SHA-256 to evidence manifest. |
| **Option B** | Extend `.gitignore` to include `*.tgz`. Regenerate at install time. **Recommended default** if A1 does not actively decide. |
| **Cross-reference** | A0.1-G1-005, A0-P0-009 (npm unpublished — the registry doesn't have this tarball anyway) |
| **Decision deadline** | A1 entry (before A1 P0 work begins) |

### D-2: `packages/icoder-embedded/icoder-embedded-2.0.0.tgz`

| | |
|---|---|
| **Size** | ~40 KB |
| **What it is** | npm tarball produced by `npm pack` from `packages/icoder-embedded/` |
| **Current state** | Untracked |
| **Reproducibility concern** | Same as D-1 |
| **Option A** | Commit + document build seed/toolchain |
| **Option B** | Extend `.gitignore` to include `*.tgz`. **Recommended default.** |
| **Cross-reference** | A0.1-G1-005, A0-P0-009 |
| **Decision deadline** | A1 entry |

### D-3: `packages/icoder-sdk/dist/` (7 files)

| | |
|---|---|
| **Files** | client.js, client.d.ts, index.js, index.d.ts, resources/*.js, resources/*.d.ts |
| **What it is** | TypeScript compiler output |
| **Current state** | Untracked. **NOT covered by `.gitignore`** `sdk/dist/` pattern — that pattern is for the legacy `sdk/` directory, not `packages/icoder-sdk/dist/`. |
| **Reproducibility concern** | Should rebuild identically from `src/` given same TS version; not verified. |
| **Option A** | Commit (treat as released artifact like `packages/icoder-embedded/dist/` which is already tracked). |
| **Option B** | Extend `.gitignore` to include `packages/*/dist/`. Rebuild at install time via `postinstall` hook. **Recommended default.** |
| **Cross-reference** | A0.1-G1-003 |
| **Decision deadline** | A1 entry |

### D-4: `phase7-external-consumer/dist/`

| | |
|---|---|
| **Files** | Built JS from `build.mjs` |
| **What it is** | Build output of the external consumer harness |
| **Current state** | Untracked |
| **Reproducibility concern** | Should rebuild from `entry.mjs` + `types-test.ts` |
| **Option A** | Commit |
| **Option B** | Extend `.gitignore` to include `phase7-external-consumer/dist/`. Rebuild via `npm run build` in CI. **Recommended default.** |
| **Cross-reference** | A0.1-G1-003 |
| **Decision deadline** | A1 entry |

### D-5: Stray `*.png` files at repo root (21 files)

| | |
|---|---|
| **Files** | `audit-gate3-01-home.png` ... `audit-gate3-05-*.png` (5) + `corti_console_*.png` (10) + `corti_embedded_assistant_*.png` (4) + others (2) |
| **What they are** | Stray intermediate screenshots from manual audit walks |
| **Current state** | Untracked. **NOT gitignored.** Risk of accidental commit via `git add *.png`. |
| **Reproducibility concern** | N/A — these are evidence, not build outputs. |
| **Option A** | Move to `reports/comprehensive-audit/evidence/screenshots/` with SHA-256 captured in evidence manifest. Preserve audit value. |
| **Option B** | Delete. **Not recommended** — these are the only browser-walk evidence for some claims. |
| **Recommended** | Option A. Move before any push to remote. |
| **Cross-reference** | A0.1-G1-004 |
| **Decision deadline** | Before any push to remote (NOT required for A1 start locally, but required before remote publication) |

### D-6: `packages/icoder-embedded/dist/` (modified, 4 files)

| | |
|---|---|
| **Files** | icoder-assistant.js + icoder-assistant.d.ts + 2 more |
| **Current state** | **Already tracked** in git history; modified in working tree |
| **Reproducibility concern** | Same as D-3 but history already exists |
| **Option A** | Commit the modifications as part of Commit A. **Straightforward — already tracked.** |
| **Recommended** | Option A. |
| **Cross-reference** | Gate 1 §4 A7 |
| **Decision deadline** | Already in Bucket A staging list. Not really "deferred" — included in Commit A. |

## §3. Default resolution script (if A1 does not actively decide)

If A1 P0 starts without closing D-1 through D-5, the default
resolutions apply automatically:

```bash
# D-1, D-2: ignore tarballs
echo "*.tgz" >> .gitignore

# D-3, D-4: ignore built dist/ under packages/ and phase7-external-consumer/
echo "packages/*/dist/" >> .gitignore
echo "phase7-external-consumer/dist/" >> .gitignore

# D-5: move stray PNGs to evidence directory
mkdir -p reports/comprehensive-audit/evidence/screenshots/
git mv audit-gate3-*.png reports/comprehensive-audit/evidence/screenshots/ 2>/dev/null || mv audit-gate3-*.png reports/comprehensive-audit/evidence/screenshots/
# (repeat for corti_console_*.png, corti_embedded_assistant_*.png)
```

These defaults preserve audit value (PNGs are kept, just relocated)
and eliminate reproducibility risk (tarballs and dist/ are rebuilds,
not committed artifacts).

## §4. A1 P0 entry check

Phase A1 P0 workstream cannot start until each row in §2 has an
explicit decision recorded (either matching the default or a
documented alternative). The Gate 8 validator will be extended in
Phase A1 to enforce this.
