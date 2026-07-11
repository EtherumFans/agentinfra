# Phase 5 A4 — Web Component 2.0 (Corti-compatible method-based API)

**Date:** 2026-07-10
**Gap closed:** GAP-11-01 (Phase 4-H §11 — 3rd-party integration audit)
**Status:** PASS

## What changed

`@icoder/embedded` rewritten from 1.0 (attribute-based config) to 2.0 (Corti-compatible method-based API). The widget now matches Corti's `<corti-embedded>` surface 1:1, while keeping iCoDer ADVANTAGE methods (`setPatientContext`, `ask`) per memory `feedback_corti_alignment.md`.

## 7 gaps closed (Phase 4-H §11)

| # | Gap | Fix |
|---|---|---|
| 1 | Attribute-based config (1.0) | `auth()`, `configureSession()`, `configure()`, `show()` methods |
| 2 | Split events (`coding.completed` + `error`) | Unified `embedded-event` envelope `{name, payload}` |
| 3 | No `configureSession({defaultTemplateKey})` analog | Added |
| 4 | Patient context as separate method | Folded into `configureSession()` (kept `setPatientContext` as ADVANTAGE) |
| 5 | Auto-visible on connect | Hidden until `show()` (matches Corti) |
| 6 | No `configure({features, locale})` | Added |
| 7 | Event payload shape mismatch | `{name, payload}` envelope |

## API surface (2.0)

### Corti-compatible methods
- `auth({access_token, refresh_token?, token_type?, mode?})`
- `configureSession({defaultTemplateKey, defaultLanguage?, patientId?, name?, encounterId?})`
- `configure({features?, locale?})`
- `show()`

### iCoDer ADVANTAGE methods (kept)
- `setPatientContext({patientId?, name?, encounterId?})`
- `ask(question): Promise<RunResponse>`

### Events (unified `embedded-event`)
- `ready` — widget finished initializing
- `run.completed` — `{run_id, agent_id, latency_ms, output, cost}` (iCoDer-specific)
- `account.creditsConsumed` — `{amount, currency, run_id}`
- `error.triggered` — `{message}`
- `message.received` — `{role, content}`

## Files

| Path | Purpose |
|---|---|
| `packages/icoder-embedded/src/icoder-assistant.ts` | Full rewrite (576 lines) |
| `packages/icoder-embedded/src/index.ts` | New — re-exports |
| `packages/icoder-embedded/tsconfig.json` | New |
| `packages/icoder-embedded/package.json` | Version 2.0.0 + metadata |
| `packages/icoder-embedded/README.md` | Quick start + API ref + changelog |
| `packages/icoder-embedded/MIGRATION-2.0.md` | 1.0 → 2.0 diff for integrators |
| `packages/icoder-embedded/examples/index.html` | Interactive demo |
| `frontend/tests/e2e/phase5_a4_embedded.spec.ts` | 7/7 Playwright regression tests |
| `frontend/playwright.phase5-a4.config.ts` | Standalone config (no app auth) |

## Bugs found + fixed during A4

1. **ES module path resolution** — example HTML used `./dist/...` but example is in `examples/` subdir; corrected to `../dist/...`
2. **CustomElementRegistry constructor reuse** — Chrome spec forbids using the same constructor for two tag names (`icoder-embedded` + `icoder-assistant`); created anonymous subclass for the deprecated alias
3. **Custom element constructor attribute-set** — setting `this.style.display = 'none'` in `constructor()` violates spec ("The result must not have attributes"); moved to `connectedCallback()`

## Verification

### Build
```
$ cd packages/icoder-embedded && npx tsc
(no output, exit 0)
$ ls dist/
icoder-assistant.d.ts  icoder-assistant.js  index.d.ts  index.js
```

### Tests
```
$ cd frontend && npx playwright test --config=playwright.phase5-a4.config.ts
Running 7 tests using 1 worker
  7 passed (3.2s)
```

Tests cover:
1. `<icoder-embedded>` registers + methods exist on prototype
2. `auth()/configureSession()/configure()/show()` chain emits `ready`
3. Widget hidden by default, visible after `show()`
4. `configureSession({patientId, name, encounterId})` renders patient bar
5. Legacy `<icoder-assistant>` tag still registers (deprecated alias)
6. 1.0 attribute-based config still works + emits console.warn deprecations
7. TypeScript `.d.ts` files ship in `dist/`

### Browser walkthrough

Loaded `http://localhost:8765/examples/index.html`:
- ✅ Both tags (`<icoder-embedded>` + `<icoder-assistant>`) register
- ✅ Clicking "Initialize Widget" runs the full chain (auth → configureSession → configure → ready → show)
- ✅ Patient bar visible with name="张三" id="#P-2026-001"
- ✅ Template badge shows "icoder/medical-coding-agent"
- ✅ Clicking "Test 1.0 Attribute Compat" installs legacy tag with deprecation warnings

Screenshot: `screenshots/phase5_a4_method_chain_initialized.png`

## Endpoint fix (bonus)

2.0 also fixes a latent 1.0 bug — the widget called `POST /api/runtime/agents/{agentRef}/run`, which was removed in Phase 2.1-A (returns 410 Gone). 2.0 uses the unified `POST /api/v1/agents/{agentId}/run` endpoint (Phase 4-F2).

## Deprecation window

- 1.0 attributes (`access-token`, `agent-ref`) still work in 2.0.x with console.warn
- 1.0 tag (`<icoder-assistant>`) still works in 2.0.x as alias
- 1.0 events (`coding.completed`, `error`) NOT emitted in 2.0 — must switch to `embedded-event`
- All 1.0 paths removed in 2.1

## Next: A5 (publish)

The package is publish-ready. `npm publish --access public` deferred to user (see `PHASE5_A5_NPM_PUBLISH_GUIDE.md`).
