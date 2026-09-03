# DEPRECATED — use `@icoder/embedded` instead

**Phase 6 Gate 1 (2026-07-13)**: this package is **deprecated**. The raw JS
files here (`icoder-assistant.js`, `icoder-dictation.js`) are an early prototype
that predates both the 1.0 attribute-based implementation in
`packages/icoder-web/` and the 2.0 Corti-compatible method-based implementation
in `packages/icoder-embedded/`.

## Why deprecated

This package has no build step, no TypeScript types, and predates the Corti
parity audit (Phase 4-H §11). It uses the legacy `api-key` attribute pattern
and calls legacy endpoints that have since been removed (returns 410 Gone).

The canonical implementation is `@icoder/embedded` v2.0.0+ at
`packages/icoder-embedded/`, which:
- Is 1:1 aligned with Corti's `<corti-embedded>` API surface
- Ships TypeScript types via `dist/index.d.ts`
- Has 7/7 Playwright regression coverage
- Calls the live unified endpoint `POST /api/v1/agents/{id}/run` (Phase 4-F2)

## What's here that 2.0 doesn't have

- `icoder-dictation.js` — a dictation widget. **Not in `packages/icoder-embedded/`**.
  Same STT situation as `packages/icoder-web/` — see that package's DEPRECATED.md
  for STT migration guidance.

## Migration

Discard this package; use `@icoder/embedded` from `packages/icoder-embedded/`.
See that package's `MIGRATION-2.0.md`.

## Removal timeline

Will be removed in Phase 7. No bug fixes or features will land here.
