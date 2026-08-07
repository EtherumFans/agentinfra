# Publish checklist — `@icoder/sdk`

This document tracks the engineering steps to publish `@icoder/sdk` to the
public npm registry. **Actual publication is OUT OF SCOPE for the current
engineering session** and is deferred until:

1. R6 cloud-only deployment ADR conditions are met (see
   `docs/governance/DEPLOYMENT_PATH_ADR.md`).
2. npm organization `@icoder` is registered and the publishing identity has
   2FA enabled.
3. Charter §22 forbidden git/verdict ops constraints are honoured — npm
   publish itself is not in the forbidden list, but the version bump must
   not pretend any of the 5-tuple has improved.

## Why deferred

- Current charter verdict is `PARTIAL_*_FILED` for product readiness; the
  SDK is consumed via git/source for engineering verification (matches
  Phase 6 Gate 4 token `REGISTRY_PUBLISH_DEFERRED`).
- Cloud-only canonical base URL is `https://api.cn.icoder.cloud` (R6 ADR).
  Publishing before DNS + TLS + regional gateway is live would advertise a
  non-functional default to first-time developers.
- Pilot design partners consume via `npm pack` + `npm install <tarball>` so
  that breaking API shape changes can land without yanking.

## Pre-publish engineering checklist (do NOT execute until all boxes tick)

- [ ] Cloud-only base URL `https://api.cn.icoder.cloud` resolves and
      serves a 200 on `GET /api/rest/v1/health` from a non-localhost
      network.
- [ ] `CHANGELOG.md` Unreleased section moved under a real version header
      with ISO date (YYYY-MM-DD).
- [ ] `README.md` quickstart URL matches production; no `localhost`
      default in the canonical quickstart.
- [ ] `npm run build` succeeds locally with zero TypeScript diagnostics.
- [ ] `dist/` regenerated from a clean checkout (`rm -rf dist && npm run
      build`) and matches `dist/` committed in git.
- [ ] Tarball dry-run review: `npm pack` produces a tarball whose file
      list contains only `dist/**`, `README.md`, `CHANGELOG.md`, `LICENSE`,
      and `package.json`.
- [ ] `package.json` `version` bumped to `1.0.0` (drop `-beta.N` suffix).
- [ ] Charter compliance review: no new forbidden verdicts in CHANGELOG,
      no 5-tuple mutation claims.
- [ ] Commit on `master` candidate branch with explicit file list (never
      `git add -A`); tag `sdk-v1.0.0` after CI green.

## npm-side setup (one-time, by org owner)

```bash
# Login with the npm account that owns the @icoder org
npm login

# Confirm org membership
npm org ls icoder

# Two-factor auth MUST be enabled at the account level
# (Profile → Account Settings → Two Factor Authentication → auth-and-writes)
```

## Publish sequence (execute ONLY after pre-publish checklist is fully green)

```bash
# 1. Verify clean tree (no uncommitted edits, no -A staging)
git status --porcelain

# 2. Build from clean checkout
rm -rf dist && npm run build

# 3. Dry-run tarball inspection
npm pack
tar -tzf icoder-sdk-1.0.0.tgz  # confirm only dist + README + CHANGELOG + LICENSE + package.json

# 4. Publish public
npm publish --access public

# 5. Verify availability
npm view @icoder/sdk@1.0.0
```

## Post-publish

- Update `docs/developer-docs/sdk.md` (or Docusaurus equivalent) to
  reference the published version.
- Tag the release commit: `git tag -a sdk-v1.0.0 -m 'SDK 1.0.0'`.
- Append a `## [1.0.0] — YYYY-MM-DD` section to `CHANGELOG.md`.
- Notify design partners that the `npm pack` consumption path is
  superseded (continue to allow it for transitional period).

## Rollback (in case of post-publish incident)

- Do NOT unpublish if more than 72 hours have passed (npm immutable
  window). Use `npm deprecate` instead:
  ```bash
  npm deprecate @icoder/sdk@1.0.0 "Use 1.0.1 instead. See CHANGELOG."
  ```
- For severe security or data-integrity defects: yank within 72 hours via
  `npm unpublish @icoder/sdk@1.0.0`. Record the yank in CHANGELOG and
  open a charter review note (5-tuple interactions must be documented).

## Charter constraints honoured by this document

- Verdict lexicon: no `PRODUCTION_READY` / `READY_FOR_MVP_SHIP` tokens
  implied by publishing. The act of `npm publish` is orthogonal to the
  charter 5-tuple and the 8 forbidden verdicts.
- Git ops: no `--amend`, no `-A`, no push to `master` until pre-publish
  checklist is fully green and tag commit is reviewed.
- Currency: all references in CHANGELOG / README use CNY (¥) per the
  Phase 5 A2 monetary convention.
