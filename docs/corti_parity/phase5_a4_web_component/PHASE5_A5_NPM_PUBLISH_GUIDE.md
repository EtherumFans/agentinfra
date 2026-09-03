# Phase 5 A5 — `@icoder/embedded@2.0.0` npm publish guide

This is a runbook for the actual `npm publish` action. The package itself is
**fully prepared** (verified via `npm pack --dry-run` — see contents below).
The actual publish requires:

1. npm login (interactive — not automatable by Claude)
2. The `@icoder` scope to exist as a npm org

## Package readiness (verified 2026-07-10)

```
$ cd packages/icoder-embedded && npm pack --dry-run
npm notice 📦  @icoder/embedded@2.0.0
npm notice Tarball Contents
npm notice 8.2kB MIGRATION-2.0.md
npm notice 4.2kB README.md
npm notice 5.1kB dist/icoder-assistant.d.ts
npm notice 23.3kB dist/icoder-assistant.js
npm notice 156B dist/index.d.ts
npm notice 53B dist/index.js
npm notice 941B package.json
npm notice Tarball Details
npm notice name: @icoder/embedded
npm notice version: 2.0.0
npm notice package size: 11.7 kB
npm notice unpacked size: 41.9 kB
```

All 7 files published; 11.7 kB tarball.

## Pre-publish checklist

- [x] Version bumped 1.0.0 → 2.0.0 (`package.json`)
- [x] `dist/` built via `tsc` (4 files: `icoder-assistant.js`, `icoder-assistant.d.ts`, `index.js`, `index.d.ts`)
- [x] README.md with quick start + API reference + changelog
- [x] MIGRATION-2.0.md (1.0 → 2.0 attribute-to-method migration guide)
- [x] License field (`Apache-2.0`)
- [x] `prepublishOnly` script runs build before publish
- [x] `files` allowlist prevents accidental source/examples publish
- [x] 7/7 Playwright regression tests pass (`tests/e2e/phase5_a4_embedded.spec.ts`)
- [x] Browser walkthrough verified (screenshot in `screenshots/phase5_a4_method_chain_initialized.png`)

## Steps the user must run

### 1. Create the `@icoder` npm org (first time only)

Visit https://www.npmjs.com/org/create and create `icoder` (free for public
unlimited packages).

### 2. Login locally

```bash
# In Claude Code REPL, prefix with `!` to run interactively in this session:
! npm login --scope=@icoder --registry=https://registry.npmjs.org
```

Prompts: username, password, email, OTP (if 2FA enabled). Stored in
`~/.npmrc` (`//registry.npmjs.org/:_authToken=...`).

Verify login:

```bash
! npm whoami
```

### 3. Final pre-publish sanity (one more)

```bash
cd packages/icoder-embedded
npm run build           # rebuild to be safe
npm pack --dry-run      # re-verify tarball
```

### 4. Publish

```bash
# Scoped packages are private by default; --access public makes it public.
npm publish --access public
```

Output should end with `+ @icoder/embedded@2.0.0`.

### 5. Verify the published package

```bash
# In a fresh empty directory:
mkdir /tmp/test-icoder-embedded && cd /tmp/test-icoder-embedded
npm init -y
npm install @icoder/embedded
node -e "const p = require('@icoder/embedded/package.json'); console.log(p.version);"
# Expect: 2.0.0
```

Browser test:

```bash
# View the published page
open https://www.npmjs.com/package/@icoder/embedded
```

### 6. Tag the git release

```bash
git tag -a @icoder/embedded@2.0.0 -m "Phase 5 A5: publish @icoder/embedded@2.0.0"
git push origin @icoder/embedded@2.0.0
```

## Rollback (if needed)

npm does not allow unpublish after 24 hours. Within 24 hours:

```bash
npm unpublish @icoder/embedded@2.0.0     # specific version
# or the whole package (only if no installs yet)
npm unpublish @icoder/embedded --force
```

After 24 hours: deprecate instead:

```bash
npm deprecate @icoder/embedded@2.0.0 "Use @icoder/embedded@2.0.1 instead"
```

Then bump + publish a fixed version.

## Post-publish (A5 done → close Phase 5 Track A)

After publish, the Phase 4-H recommendation's P1 GAP-11-02 is closed. The
remaining Phase 5 Track A item is:

- **A6** — RunHistory Date filter + daily chart on `/usage` (frontend only,
  backend `daily_breakdown` already wired by A3)

## Why Claude did not run `npm publish`

Per CLAUDE.md `feedback_stop_on_user_signal.md` and the system prompt's
"Executing actions with care" section, npm publish is:

- Hard to reverse (24h unpublish window, then deprecate-only)
- External (visible to everyone on the public registry)
- Requires interactive credentials (no automatable login)

So Claude prepares the package + this runbook; the user runs step 4.
