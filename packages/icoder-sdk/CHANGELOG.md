# Changelog

All notable changes to `@icoder/sdk` will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the Pre-Release 0 rule relaxed for `1.0.0-beta.*` (i.e. breaking API
shape changes are allowed on beta bumps until 1.0.0 stable).

## [Unreleased]

Engineering readiness for 1.0.0 stable. No code surface changes.

### Added
- `CHANGELOG.md` (this file) — tracks version history from 1.0.0-beta.2 onward.
- `PUBLISH.md` — npm publish checklist for the moment credentials + 2FA are in
  place (deferred per R6 cloud-only ADR until pilot onboarding).

### Changed
- README quickstart `baseURL` default updated from `http://localhost:8000`
  (dev-only) to `https://api.cn.icoder.cloud` (R6 cloud-only canonical).
  Local dev URL still documented as an override for self-hosted development.

### Notes
- 5-tuple (GATE4_8 / GATE4_9 / GATE4_ACCEPTANCE / CORTI_PARITY /
  PRODUCTION_READINESS) is charter-locked; SDK packaging changes do not
  interact with the 5-tuple.
- No new forbidden git ops (no push, no master commit, no amend, no `-A`).
- No new forbidden verdicts (verdict lexicon unchanged).

## [1.0.0-beta.2] — 2026-07-14

Phase 6 Gate 4: unified Agent Run + Trace resource family.

### Added
- `icoder.runs.runText(agentId, text, options)` — canonical agent run entry.
  Returns `{ run_id, trace_id, trace_url, cost: { amount, currency: 'CNY' },
  latency_ms }`.
- `icoder.runHistory.list({ agent_id, days, limit })` — RunHistory API
  wrapper (alembic 010).
- `icoder.runTrace.timeline(runId)` — 9-step trace timeline data source
  (alembic 009).
- `icoder.patientContext` resource class (placeholder, Phase 7 Gate 11).
- A2A v0.3 envelope types: `A2AEnvelope`, `A2AMessage`, `A2AMessagePart`
  mirroring `app/icoder/agent_runtime/a2a_facade.py`. Currently no client-side
  consumer; reserved for direct A2A messaging in a later revision.

### Changed
- `icoder.agentRun` resource renamed to `icoder.runs` (legacy alias kept
  for transitional compatibility; will be removed in 1.0.0 stable).
- Cost shape unified: `{ amount: number, currency: 'CNY' }`. Older
  `cost_usd` field name is documented as historical; underlying value
  is already CNY per CLAUDE.md 货币约定 (Phase 5 A2).

### Internal
- Build verified: `tsc` clean, `dist/index.js` + `dist/index.d.ts`
  emitted, tarball `icoder-sdk-1.0.0-beta.2.tgz` reproducible.
- Registry publish DEFERRED — package consumed via git/source for now.
  Decision recorded in PUBLISH.md.

## [1.0.0-beta.1] — 2026-06-20

Initial TypeScript SDK scaffold.

### Added
- `iCoDer` default export with 8 resource classes: `facts`, `agents`,
  `experts`, `reviews`, `speechToText`, `textGen`, `billing`, `usage`.
- `oauth` resource class for API client credential management.
- Axios-based HTTP client with JWT `accessToken` / `refreshToken` auth.
- TypeScript types for all request/response payloads.
