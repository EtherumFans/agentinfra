# Phase A1A Gate 4R-I.4 — Engineering Debt Liquidation

**Date**: 2026-07-21
**Branch**: `phase-a1a/emergency-containment` at `84eba78` (post Gate 4R-I.3)
**Predecessor**: Gate 4R-I.3 (`84eba78` post-merge regression)
**Successor**: Gate 4R-I.8 (security/compliance release re-audit)

Charter §6 requires triaging the 6 categories deferred in 4R-I.3 §3
and liquidating known mechanical issues (wrong-DB tests, source-tree
writes, schema drift, stale product-name assertions, broken paths).
This sub-gate catalogues findings and applies the mechanical fixes
that are in scope.

## §1. Deferred test category triage (from 4R-I.3 §3)

| # | Category | 4R-I.3 status | 4R-I.4 status | Evidence |
|---|---|---|---|---|
| 5 | Frontend TypeScript | NOT RUN | **PASS** (`tsc --noEmit` exit 0) | Frontend tsc clean |
| 6 | Frontend build | NOT RUN | **PASS** (`vite build` exit 0 in 44.60s; 13 chunks) | `frontend/dist/` rebuilt |
| 7 | Frontend unit tests | NOT RUN | **PASS 77/77** after 1 stale-assertion fix (see §3.1) | `vitest --run` |
| 8 | Playwright browser tests | NOT RUN | DEFERRED (Phase 7 Gate 11/12/13 evidence still valid pre-merge) | — |
| 10 | PostgreSQL migration | NOT RUN | DEFERRED (no local PG instance; requires CI environment) | — |
| 12 | Lint / static check | NOT RUN | **PASS** (tsc clean; eslint not run — not in default flow) | — |
| 13 | SDK / package build | NOT RUN | **PASS** (`@icoder/sdk@1.0.0-beta.2` builds cleanly via `tsc`) | `packages/icoder-sdk/dist/` |
| 14 | Examples smoke tests | NOT RUN | **PARTIAL** (`node --check` syntax PASS; runtime requires live backend) | `examples/partner-reference-app/server/index.mjs` syntax-clean |

**Net**: 5 of 8 triaged categories now have evidence; 3 deferred (Playwright,
PostgreSQL, full examples runtime) with cited blockers.

## §2. Mechanical debt scan results

### 2.1 corti-reverse-engineered fixture gap (charter §7)

4R-I.6 §5.4 claimed "8 missing .md files in
`tests/fixtures/corti-reverse-engineered/`". That path **does not
exist** in the repository. The actual path is
`docs/corti-reverse-engineered/` and contains 19 .md files.

Scan result: **all 19 referenced .md files exist**. Zero gap.

The 4R-I.6 report's count of "27 test errors" referred to environment-
specific Windows asyncio hangs, NOT missing fixtures. Those are pre-
existing and were correctly catalogued in 4R-I.3 §5.

### 2.2 Schema drift (ORM vs migrations)

42 ORM tables vs migrations. All 42 are created by `op.create_table`
in some migration. **Zero drift**. 5 migration tables (legacy Phase
1.2 `contexts` family) have been dropped from ORM but still appear in
migration history — this is the expected pattern (migrations preserve
history; ORM tracks current state).

### 2.3 Source-tree writes

Scanned all test files for `open(...,'w')`, `write_text`, `write_bytes`.
All writes target `tmp_path`, `tmp`, or `asset` fixtures (pytest-
managed temp dirs). **Zero source-tree writes**.

### 2.4 Wrong-DB tests

Scanned `icoder.db` references in tests. All are either:
- Comments documenting what is NOT touched
- Fallback strings (`or "sqlite+aiosqlite:///./data/icoder.db"`) —
  these don't actually point at the dev DB in test runs because
  `settings.DATABASE_URL` is overridden in conftest before tests start

**Zero wrong-DB defects.**

### 2.5 Stale product-name / route assertions

Found 1 stale assertion: `agentNavigationSmoke.test.tsx` enforced a
Phase 3-B2 Loop 0 directive ("EmbeddedAssistantPage physically
deleted") that was superseded by Phase 7 Gate 13 (2026-07-14) which
restored `/ai-studio/embedded-assistant` for Corti parity.

**Fixed** (see §3.1).

### 2.6 Broken paths

Scanned for `Path("./..."`) or `Path("../...")` patterns in tests.
**Zero broken paths**. The test DB CWD dependency
(`sqlite+aiosqlite:///./data/test.db` resolved from CWD) is
documented in conftest and works when pytest is run from `backend/`.

## §3. Fixes applied in this sub-gate

### 3.1 Stale test assertion fix

`frontend/src/pages/__tests__/agentNavigationSmoke.test.tsx`:

- Removed `EmbeddedAssistantPage` from the "deleted pages" list
- Updated the route-removal test to only assert `TextGeneration`
  routes are removed (which is still true); `EmbeddedAssistant`
  route is now legitimately present at `/ai-studio/embedded-assistant`
- Net: 77/77 frontend tests PASS (was 75/77)

### 3.2 OpenAPI refresh

`docs/openapi/openapi.json` was stale — frozen at 162 paths, but
the live FastAPI app exposes 194 paths (35 added, 3 removed).

Regenerated from `app.main:app` at HEAD. Now matches live state:
- 194 paths
- 237 routes
- Phase 7 Gate 5/7/8/12/13 additions reflected (`/api/clients/*`,
  `/api/embedded/preview-sessions/*`, `/api/usage/by-agent`, etc.)

### 3.3 SDK dist rebuild (no source change)

`packages/icoder-sdk/` built cleanly via `tsc`. The `dist/` is
populated. No source changes — just confirmed buildability.

## §4. Items deliberately NOT fixed

These are mechanical debt items that were considered but not touched
in this sub-gate because they are out of scope or require product
judgement:

| Item | Reason deferred |
|---|---|
| `.gitignore` whitelist for `*.log` under integration/evidence/ | Not blocking; JUnit XML captures structured data |
| Legacy root-level `audit_*.xml` files | Charter §5.3 "do not move historical evidence"; left for separate cleanup |
| Phase A0.1 / Phase A0 comprehensive-audit reports | Historical artefacts; index-first principle applies (Gate 4R-I.2) |
| Playwright browser suite re-run | Phase 7 Gate 11/12/13 evidence still valid pre-merge; re-run is Gate 4R-I.9 scope |
| PostgreSQL migration verification | Requires external PG instance; deferred to CI |
| Module-level singleton hermeticity beyond Rate Limiter | Triaged in 4R.3 as GATE4R_REG_008 (P2, 2 nodes) |

## §5. Charter §6 acceptance

| Criterion | Status |
|---|---|
| Triaged the 6 categories deferred in §3 | MET ✓ (§1 of this report) |
| Liquidated known mechanical issues | MET ✓ (schema drift 0, source-tree writes 0, wrong-DB 0, stale assertions fixed, broken paths 0) |
| Built the corti-reverse-engineered fixture gap catalogue | MET ✓ (§2.1 — 0 missing fixtures; the "8 missing" claim in 4R-I.6 was incorrect) |

## §6. Forbidden list for this sub-gate

| Forbidden action | Status |
|---|---|
| Modify clinical prompts | NOT DONE ✓ |
| Weaken JWT/encryption/redaction/egress/retention | NOT DONE ✓ |
| Add features beyond mechanical debt | NOT DONE ✓ |
| Touch master / origin/master | NOT DONE ✓ |
| Push / PR | NOT DONE ✓ |
| Delete historical reports | NOT DONE ✓ |

## §7. Provisional verdict

```
PASS_A1A_GATE4R_I_4_ENGINEERING_DEBT_LIQUIDATION_FILED
```

Tier: FILED (not VERIFIED). Mechanical debt catalogued; tractable
items fixed; remainder deferred with cited blockers.

## §8. Next

Gate 4R-I.8 — security/compliance release re-audit:

- Re-verify Gate 4 PHI boundary claims against current HEAD
- Audit all ~60 PHI fields per charter §12.1
- Verify KMS, tenant-level keys, egress policy runtime behavior
- Output P0/P1 security blockers list
