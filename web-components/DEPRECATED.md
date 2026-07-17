# DEPRECATED — use `@icoder/embedded` instead

**Phase 6 Gate 1 (2026-07-13)**: this directory is **deprecated**. It contains
an early Lit-based prototype of `<icoder-assistant>` + `<icoder-speech-to-text>`
that predates the Corti parity audit (Phase 4-H §11) and the canonical 2.0
implementation in `packages/icoder-embedded/`.

## Why deprecated

- Uses Lit (Corti's `<corti-embedded>` is framework-free vanilla Web Component
  — the canonical `packages/icoder-embedded/` matches Corti's choice)
- Uses legacy `api-key` attribute pattern (1.0 attribute-based)
- Calls endpoints that have been removed in Phase 2.1-A (returns 410 Gone)
- No Corti parity, no Playwright coverage

## What's here that 2.0 doesn't have

- `icoder-speech-to-text.ts` — STT widget. **Not in `packages/icoder-embedded/`**.
  Same STT situation as `packages/icoder-web/` — see that package's DEPRECATED.md.

## Migration

Discard this directory; use `@icoder/embedded` from `packages/icoder-embedded/`.
See that package's `MIGRATION-2.0.md`.

## Removal timeline

Will be removed in Phase 7. No bug fixes or features will land here.
