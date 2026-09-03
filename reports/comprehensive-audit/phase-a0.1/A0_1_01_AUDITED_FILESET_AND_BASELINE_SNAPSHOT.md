# Phase A0.1 Gate 1 — Audited Fileset and Baseline Snapshot

> Read-only snapshot. Does NOT modify product code. Does NOT commit.
> Does NOT create tag. Does NOT push.

Spec reference: Phase A0.1 §三 (Gate 1 — Audited Fileset and Baseline Snapshot).

---

## §1. Purpose

Produce a reproducible description of exactly what is on disk at HEAD
`c147d0154...` + dirty working tree, classified into four buckets:

1. **Audited Product** — what Phase A0 / A0.1 audit opines about
2. **Audit-Only** — the audit deliverables themselves
3. **Unsafe** — must never be committed (secrets, browser data, build outputs
   that require reproducibility)
4. **Ambiguous** — needs per-file decision before Gate 9 staging

This gate does NOT compute SHA-256 hashes; that is Gate 2's job. This gate
only enumerates paths and categories so Gate 2 has a known fileset to hash.

## §2. Baseline reference

```
Git HEAD    : c147d015455017bc1d8420cbdbd813b3b8ec23ce
HEAD subject: feat(track-h): Tier 2 Corti controlled probes
              — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells
Branch      : master
Remote      : origin → https://github.com/EtherumFans/agentinfra.git
HEAD time   : (per git log, not recomputed here)
Snapshot at : 2026-07-17 (working tree dirty)
Dirty entries: 97
```

`REPRODUCIBLE_AUDITED_PRODUCT_BASELINE` is **NOT** established — see §6.

## §3. .gitignore audit (protective coverage)

The following paths are confirmed ignored and therefore safe from accidental
`git add .` (but NOT safe from `git add -f`):

| Pattern | Matches | Verified |
|---------|---------|----------|
| `.env` | `backend/.env`, `examples/partner-reference-app/.env` | ✅ |
| `.env.*` | (any .env.something) | ✅ |
| `!.env.example` | exception so .env.example IS tracked | ✅ |
| `!.env.cloud.example` | exception so .env.cloud.example IS tracked | ✅ |
| `node_modules/` | `phase7-external-consumer/node_modules/` (2403 files) | ✅ |
| `.audit-chrome-profile/` | full Chrome profile (2030 files) | ✅ |
| `.corti-profile/` | (comment: Browser profile data) | ✅ |
| `frontend/dist/` | (build output) | ✅ |
| `web-components/dist/` | (build output) | ✅ |
| `sdk/dist/` | (legacy SDK dist path) | ✅ |

**Note**: `packages/icoder-sdk/dist/` is NOT covered by the existing
`sdk/dist/` pattern (different prefix). The directory IS untracked today and
would be added by a careless `git add packages/icoder-sdk/`. Must be
explicitly reviewed in Gate 9.

**`backend/.env` is NOT committed to git history** (verified via
`git ls-files backend/.env` → empty). The A0-P0-010 issue narrative
("Committed backend/.env") is inaccurate and must be reworded in Gate 3
to: "Backend ships no `.env.example`; working-tree `backend/.env` contains
placeholder `SECRET_KEY=change-me-in-production`; `config.py` auto-generates
a secret when env var unset, but no startup check refuses the
`change-me-in-production` sentinel."

## §4. Fileset classification — 97 working tree entries

### Bucket A — Audited Product (Commit A candidates)

These are product code, migrations, tests, and partner-facing artifacts that
Phase A0 / A0.1 audit opines about. All are safe to commit once reviewed.

#### A1. Modified backend code — 9 files

```
backend/app/api/agent_run.py
backend/app/api/embedded.py
backend/app/api/platform_api_clients.py
backend/app/api/usage.py
backend/app/main.py
backend/app/middleware/auth.py
backend/app/models/__init__.py
backend/app/models/oauth.py
backend/app/models/run_history.py
```

#### A2. Modified tests — 2 files

```
backend/tests/conftest.py
backend/tests/test_api/test_phase4f_agent_run.py
```

#### A3. New backend code (Phase 7) — 12 files

```
backend/alembic/versions/012_idempotency_records.py
backend/alembic/versions/013_run_history_status_and_cancel.py
backend/alembic/versions/014_api_client_attribution_and_origins.py
backend/alembic/versions/015_preview_sessions.py
backend/app/api/examples.py
backend/app/api/preview_sessions.py
backend/app/api/runs.py
backend/app/middleware/partner_cors.py
backend/app/models/idempotency_record.py
backend/app/models/preview_session.py
backend/app/services/idempotency_service.py
backend/app/services/preview_ticket.py
backend/app/services/run_lifecycle.py
backend/app/services/trace_token.py
```

Wait — that's 14 files (4 migrations + 10 source files). Corrected count: 14.

#### A4. New backend tests (Phase 7) — 10 files

```
backend/tests/test_api/test_phase7_gate1_examples_mount.py
backend/tests/test_api/test_phase7_gate3_agent_run_idempotency.py
backend/tests/test_api/test_phase7_gate4_run_cancel.py
backend/tests/test_api/test_phase7_gate5_api_clients.py
backend/tests/test_api/test_phase7_gate6_cors.py
backend/tests/test_api/test_phase7_gate7_trace_token.py
backend/tests/test_api/test_phase7_gate8_usage_api_client.py
backend/tests/test_api/test_phase7_gate9_sse_run_events.py
backend/tests/unit/app/api/test_phase7_gate13a_audit.py
backend/tests/unit/app/api/test_phase7_gate13a_preview_html.py
backend/tests/unit/app/api/test_phase7_gate13a_preview_sessions.py
backend/tests/unit/app/services/test_phase7_gate13a_preview_ticket.py
backend/tests/unit/app/services/test_phase7_gate3_idempotency.py
```

Wait — that's 13 files. Corrected count: 13.

#### A5. New frontend page — 1 file

```
frontend/src/pages/EmbeddedAssistantPage.tsx
```

#### A6. Modified frontend — 4 files

```
frontend/src/App.tsx
frontend/src/components/layout/Layout.tsx
frontend/src/i18n/locales.ts
frontend/tests/e2e/phase5_a4_embedded.spec.ts
```

#### A7. Modified packages/icoder-embedded — 5 files

```
packages/icoder-embedded/dist/icoder-assistant.d.ts
packages/icoder-embedded/dist/icoder-assistant.js
packages/icoder-embedded/package.json
packages/icoder-embedded/src/icoder-assistant.ts
packages/icoder-embedded/demos/  (new directory — 5 files)
```

#### A8. Modified packages/icoder-sdk — 13 files

```
packages/icoder-sdk/README.md
packages/icoder-sdk/package.json
packages/icoder-sdk/src/client.ts
packages/icoder-sdk/src/index.ts
packages/icoder-sdk/src/resources/agents.ts
packages/icoder-sdk/src/resources/billing.ts
packages/icoder-sdk/src/resources/compliance.ts
packages/icoder-sdk/src/resources/facts.ts
packages/icoder-sdk/src/resources/oauth.ts
packages/icoder-sdk/src/resources/reviews.ts
packages/icoder-sdk/src/resources/textgen.ts
packages/icoder-sdk/tsconfig.json
packages/icoder-sdk/src/resources/runs.ts   (new file)
packages/icoder-sdk/dist/                   (new directory, 7 files)
```

#### A9. Deleted — 1 file

```
packages/icoder-sdk/package-lock.json   (deleted)
```

#### A10. Partner app — 1 directory tree

```
examples/   (partner-reference-app/.env is gitignored; rest is OK)
examples/partner-reference-app/.env.example
examples/partner-reference-app/package-lock.json
examples/partner-reference-app/package.json
examples/partner-reference-app/README.md
examples/partner-reference-app/server.js
examples/partner-reference-app/views/index.ejs
examples/partner-reference-app/public/...
examples/phase5_track_b2/   (older content; review before staging)
examples/phase5_track_c/    (older content; review before staging)
```

**Note**: `examples/partner-reference-app/.env` contains a real-looking
`ICODER_API_CLIENT_SECRET=[REDACTED_COMPROMISED_API_CLIENT_SECRET]` (plain-text secret invalidated in Phase A0.1R Gate 1; see `reports/comprehensive-audit/phase-a0.1r/A0_1R_01_CREDENTIAL_CONTAINMENT_AND_REDACTION.md`).
Although gitignored, the secret must be **rotated before Commit A** because
the working tree has been observed by audit tooling and the secret is now in
audit memory. Treat as compromised.

#### A11. External consumer harness — 1 directory

```
phase7-external-consumer/
├── build.mjs
├── entry.mjs
├── package.json
├── package-lock.json
├── smoke.mjs
├── tsconfig.json
├── types-test.ts
├── dist/                      (built output — review)
└── node_modules/              (gitignored, 2403 files)
```

#### A12. Deprecated markers — 3 new + 1 modified

```
packages/icoder-web/DEPRECATED.md       (new)
packages/web-components/DEPRECATED.md   (new)
web-components/DEPRECATED.md            (new)
```

#### A13. Partner demos (packages/icoder-embedded/demos) — 5 files

```
packages/icoder-embedded/demos/cdi-demo.html
packages/icoder-embedded/demos/config.example.js
packages/icoder-embedded/demos/drg-dip-demo.html
packages/icoder-embedded/demos/medical-coding-demo.html
packages/icoder-embedded/demos/README.md
```

### Bucket B — Audit-Only (Commit B candidates)

These are audit deliverables. They reference Bucket A but are themselves
metadata. Safe to commit once the Final Decision is rewritten in Gate 9.

```
reports/comprehensive-audit/                    (all .md + evidence/*)
reports/phase6/                                 (all .md)
reports/phase7/                                 (all .md; gate13a/* evidence dirs empty)
docs/audit/                                     (new directory)
docs/corti_parity/phase7_gate13a/               (1 .png)
scripts/audit/                                  (validate_phase_a0.py + future scripts)
```

Plus this Phase A0.1 directory:

```
reports/comprehensive-audit/phase-a0.1/         (this gate's deliverables)
```

### Bucket C — Unsafe (must NEVER be committed)

```
backend/.env
  Contains SECRET_KEY=change-me-in-production + DEBUG=true.
  Gitignored ✓ (verified git check-ignore).
  Action: rotate secret, add startup-time check that refuses the sentinel.

examples/partner-reference-app/.env
  Contained ICODER_API_CLIENT_SECRET=[REDACTED_COMPROMISED_API_CLIENT_SECRET] (plain-text secret invalidated in Phase A0.1R Gate 1).
  Gitignored ✓ (verified git check-ignore).
  Action: rotate the API client secret before Commit A; keep .env on disk
          for local dev only.

.audit-chrome-profile/  (2030 files)
  Full Chrome user-data-dir. Cookies, session state, browsing history,
  crash dumps, GPU caches, extension state.
  Gitignored ✓ (verified git check-ignore).
  Action: leave gitignored; do NOT add.

audit-gate3-01-home.png                      (root)
audit-gate3-02-agent-hub.png                 (root)
audit-gate3-03-medical-coding.png            (root)
audit-gate3-04-cdi.png                       (root)
audit-gate3-05-ai-studio-overview-corti-links.png  (root)
corti_console_agent_code_js.png              (root)
corti_console_agent_detail_settings.png      (root)
corti_console_agents_list.png                (root)
corti_console_api_clients.png                (root)
corti_console_billing.png                    (root)
corti_console_embedded_assistant.png         (root)
corti_console_home.png                       (root)
corti_console_medical_coding_variants.png    (root)
corti_console_new_agent_medical_coding.png   (root)
corti_console_prebuilt_agents.png            (root)
corti_console_usage.png                      (root)
corti_embedded_assistant_code_html.png       (root)
corti_embedded_assistant_event_inspector.png (root)
corti_embedded_assistant_react_tab.png       (root)
corti_embedded_assistant_settings_tab.png    (root)
  Stray intermediate screenshots at repo root. Not gitignored, so a careless
  `git add *.png` would catch them.
  Action: move to reports/comprehensive-audit/evidence/ (with proper hashes
          captured in Gate 2) or delete; NOT to be committed from repo root.
```

### Bucket D — Ambiguous (Gate 9 review per-file)

```
packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz
packages/icoder-embedded/icoder-embedded-2.0.0.tgz
  Built npm tarballs. Real build outputs.
  Current v2 manifest has SHA-256 for both (lines 152-153).
  Concern: tarballs are opaque binaries; reproducibility of the build is
           not verified. If build inputs (src/ + tsconfig.json) change
           between commits, the SHA-256 will drift and the manifest breaks.
  Recommendation for Gate 9: REGENERATE both tarballs from committed source
           at commit time, recompute SHA-256, and capture in v2 manifest.
           If regeneration is non-reproducible, document the seed and
           toolchain versions.

packages/icoder-sdk/dist/   (7 files)
  Built TypeScript output (client.js, client.d.ts, index.js, etc.).
  NOT covered by `.gitignore` `sdk/dist/` pattern (that pattern is for the
  legacy `sdk/` directory, not `packages/icoder-sdk/dist/`).
  Recommendation: either commit (treat as released artifact) or extend
                  .gitignore to include `packages/*/dist/` and rebuild
                  at install time. Decide before Commit A.

phase7-external-consumer/dist/
  Built output. Same ambiguity as above.

packages/icoder-embedded/dist/  (4 files, modified)
  Already tracked in git history. Modified versions in working tree.
  Action: commit the modifications as part of Commit A; straightforward.
```

## §5. Fileset summary

| Bucket | Files (approx) | Commit target |
|--------|---------------:|---------------|
| A — Audited Product | ~70 product + test + migration + partner files | Commit A |
| B — Audit-Only | ~30+ markdown + JSON + scripts | Commit B |
| C — Unsafe | 21 PNG + 2 .env + 1 Chrome profile dir | NEVER |
| D — Ambiguous | 2 tarballs + 2 dist dirs | Per-file Gate 9 decision |

Total dirty entries: **97** working-tree slots (some are directories that
expand to many files).

## §6. Baseline reproducibility status

```
NO_COMMITTED_HEAD_DRIFT          ✅  (HEAD = c147d0154... unchanged)
REPRODUCIBLE_AUDITED_PRODUCT_BASELINE  ❌  NOT ESTABLISHED
  Reasons:
   1. Phase 6, Phase 7, Comprehensive Audit, Pre-A0, Phase A0, Phase A0.1
      deliverables are all UNCOMMITTED. The audit opines about a product
      state that has no commit anchor.
   2. Working tree contains Bucket A modifications and additions that the
      audit assumes are part of the product. Without a commit, two
      machines cloning HEAD `c147d0154...` will not reproduce these files.
   3. Bucket D tarballs and dist/ outputs are not reproducible from
      source without a documented build pipeline.
```

Gate 1 can therefore only establish:

```
PHASE_A0_1_GATE_1_VERDICT:
  FILESET_ENUMERATED (97 working-tree entries classified into 4 buckets)
  GITIGNORE_COVERAGE_VERIFIED (10 patterns; covers .env / node_modules / profile)
  BASELINE_REPRODUCIBILITY_NOT_ESTABLISHED
  BLOCKED_BY: uncommitted substrate + Bucket D reproducibility gap
```

The baseline will be established by Gate 9 (Safe Commit and Immutable Freeze),
which produces two commits + an annotated tag.

## §7. Findings raised in Gate 1

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G1-001** | P0-S | `examples/partner-reference-app/.env` working tree contains a real-looking `ICODER_API_CLIENT_SECRET`. Must rotate before any commit. |
| **A0.1-G1-002** | P1 | `backend/.env` ships no `.env.example`; `backend/.env` on disk has placeholder `SECRET_KEY=change-me-in-production`; `backend/app/config.py` auto-generates a secret but no startup check refuses the sentinel. A0-P0-010 narrative ("Committed backend/.env") is inaccurate and must be reworded. |
| **A0.1-G1-003** | P2 | `packages/icoder-sdk/dist/` and `phase7-external-consumer/dist/` are NOT covered by existing `.gitignore` patterns. Risk of accidental commit of opaque build outputs. |
| **A0.1-G1-004** | P2 | 21 stray `*.png` files at repo root (audit-gate3-* and corti_console_*) are not gitignored. Move to `reports/comprehensive-audit/evidence/` with hashes (Gate 2) or delete. |
| **A0.1-G1-005** | P2 | Two tarballs (`icoder-sdk-1.0.0-beta.2.tgz`, `icoder-embedded-2.0.0.tgz`) require reproducible build documentation before they can be included in Commit A. |
| **A0.1-G1-006** | P3 | Older `examples/phase5_track_b2/` and `examples/phase5_track_c/` directories need content review before Commit A staging. |

End of Gate 1. Proceeding to Gate 2 — Canonical Manifest Repair.
