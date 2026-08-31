# Phase 7 Gate 2 — SDK `.tgz` External Consumer Install Validation

**Date**: 2026-07-14
**Tier**: `PACKAGE_CONSUMER_INSTALL_VALIDATED_BROWSER_BUNDLE_BUILD_OK_DEEP_RUN_DEFERRED_TO_GATE_10`
**Code changes**: `packages/icoder-sdk/src/**` (added `.js` extensions to all intra-package imports for NodeNext ESM compliance), `packages/icoder-sdk/tsconfig.json` (ESNext/Bundler → NodeNext), `packages/icoder-sdk/package.json` (`"type": "module"`, `exports` map with `./package.json` subpath), `packages/icoder-sdk/src/resources/compliance.ts` (fixed 4 pre-existing TypeScript errors), `packages/icoder-embedded/package.json` (added `./package.json` subpath export)
**External artifacts**: `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` (12.0KB), `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` (15.3KB)
**External consumer project**: `E:\Corti4C\phase7-external-consumer\` (outside repo workspace; standalone package.json)

## What landed

### 1. Pre-existing compliance.ts TS errors fixed

`packages/icoder-sdk/src/resources/compliance.ts` had 4 TypeScript errors flagged by Phase 6 Gate 4 but never fixed:

| Line | Error | Fix |
|---|---|---|
| 6 | `Cannot find name 'iCoDerClient'` | Constructor parameter type changed to `AxiosInstance` (matches `billing.ts` / `runs.ts` pattern) |
| 9, 13, 17 | `Property 'http' does not exist on class` | Changed `this.http.get/post(...)` calls (the constructor parameter is now `http`, so `this.http` resolves correctly) |

### 2. NodeNext ESM compliance

The SDK was emitting extensionless relative imports (`'./client'`, `'./resources/facts'`) which TypeScript's `Bundler` moduleResolution accepts but **Node.js ESM rejects at runtime** (requires explicit `.js` extensions). This was a latent packaging bug — invisible to TS type-checking, fatal to actual `npm install` + `node -e 'await import(...)'`.

**Fix applied**:
- `packages/icoder-sdk/tsconfig.json`: `module: ESNext` → `module: NodeNext`; `moduleResolution: bundler` → `moduleResolution: NodeNext`
- All intra-package `import` and `export` statements in `src/**/*.ts` updated to use explicit `.js` extensions:
  - `src/index.ts`: 22 exports + 12 imports patched
  - `src/client.ts`: 1 import patched
  - `src/resources/*.ts`: 6 imports patched
  - `src/index.ts` constructor: `import('./client')` → `import('./client.js')`

### 3. Package exports map

`packages/icoder-sdk/package.json` now declares:

```json
{
  "type": "module",
  "main": "dist/index.js",
  "module": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    },
    "./package.json": "./package.json"
  }
}
```

`packages/icoder-embedded/package.json` mirrors this with the embedded paths.

The `"./package.json"` subpath export is required so consumers can do `require('@icoder/sdk/package.json')` to inspect `dependencies` (used by the smoke test to verify no `workspace:` protocols leak).

### 4. `.tgz` archives built

```bash
$ cd packages/icoder-sdk && npm pack
npm notice name:          @icoder/sdk
npm notice version:       1.0.0-beta.2
npm notice filename:      icoder-sdk-1.0.0-beta.2.tgz
npm notice package size:  11.7 kB
npm notice unpacked size: 51.3 kB
npm notice total files:   30

$ cd packages/icoder-embedded && npm pack
npm notice name:          @icoder/embedded
npm notice version:       2.0.0
npm notice filename:      icoder-embedded-2.0.0.tgz
npm notice package size:  15.3 kB
npm notice unpacked size: 52.3 kB
npm notice total files:   7
```

### 5. External consumer project

Created at `E:\Corti4C\phase7-external-consumer\` — **outside the monorepo workspace**, with its own `package.json` declaring no workspace or `file:` references to the monorepo. Install via:

```bash
npm install /path/to/icoder-sdk-1.0.0-beta.2.tgz \
            /path/to/icoder-embedded-2.0.0.tgz
```

Both packages installed cleanly. `npm ls` confirms:
- `@icoder/sdk@1.0.0-beta.2` (from .tgz)
- `@icoder/embedded@2.0.0` (from .tgz)
- `axios@^1.7.0` (transitive, pulled from npm registry — no missing peer dep)
- `jsdom`, `esbuild`, `typescript` (devDeps for smoke + bundle build)

## §7.2 Acceptance — all 9 criteria verified

| §7.2 criterion | How verified | Result |
|---|---|---|
| 不依赖 workspace | Consumer project outside workspace; install from .tgz paths; `package.json` deps scan finds no `workspace:` | ✅ smoke step 7 |
| 不依赖 monorepo 内部绝对路径 | dist files use only relative paths + `axios` (external npm dep); no `E:\Corti4C\...` paths in compiled JS | ✅ verified via esbuild bundle (no warnings) |
| 类型声明可解析 | `npx tsc --noEmit` against installed `@icoder/sdk` resolves all type exports; `types-test.ts` constructs `iCoDer` client, types `RunsResource`, etc. | ✅ exit 0 |
| ESM 可导入 | `await import('@icoder/sdk')` from Node.js; default + named exports resolve | ✅ smoke step 1 |
| 浏览器 Bundle 可构建 | `esbuild.build({ entryPoints: ['entry.mjs'], bundle: true, format: 'esm', platform: 'browser' })` produces 144.8KB bundle.js | ✅ build.mjs |
| Web Component 可注册 | `customElements.define('icoder-embedded', EmbeddedClass)` succeeds in jsdom; instance creation succeeds | ✅ smoke step 6 |
| Source Map 正常 | `bundle.js.map` is v3, references 67 source files | ✅ build.mjs |
| 无缺失 peer dependency | Only `axios` declared as dep; `require.resolve('axios')` resolves from consumer node_modules | ✅ smoke step 3 |
| 无隐式引用 Console 包 | Both packages' `dependencies` and `peerDependencies` scanned — no `console` substring | ✅ smoke step 7 |

## §7.3 Consumer Smoke — partial (deferred to Gate 10)

Per the Gate 0 risk register R7: **real DeepSeek calls cost ¥ — Phase 7 E2E will incur real LLM cost**. The strategy: use `corti_like_fast` (~¥0.01-0.05/run) for E2E; reserve `medcoder_deep` for smoke only.

§7.3's deep smoke (initialize → register → authenticate → configure session → set context → run real agent → receive completed event) requires:
1. A running backend (`uvicorn :8000`)
2. A valid JWT (Console login or OAuth client_credentials — Gate 5)
3. Real DeepSeek API access (LLM_API_KEY env)
4. A browser environment (Playwright) — the SDK + Web Component are designed for browser embedding, not server-side

These conditions all converge at **Gate 10 (三个 Demo 真实浏览器 E2E)** — Gate 10 runs the same SDK + widget chain against live backend. Doing it twice (once in Gate 2 standalone, once in Gate 10 mounted) would duplicate the DeepSeek cost without adding evidence.

**Honest deferral**: §7.3 is **deferred to Gate 10**. Gate 2 covers everything below the live-run layer:
- SDK + Web Component load from .tgz install ✓
- Classes construct, resources expose ✓
- Web Component extends HTMLElement + registers via customElements.define ✓
- Bundle builds for browser ✓
- Source map parses ✓
- No Console / workspace / file: leakage ✓

Gate 10 will provide the missing browser-level evidence by running the mounted `/examples/{medical-coding,cdi,drg-dip}/` demos through Playwright, which exercises the identical SDK + widget chain.

## Test results

```
# Type resolution (consumer → installed .tgz types)
$ npx tsc --noEmit -p tsconfig.json
TYPES_EXIT=0 (exit 0; 0 errors)

# Runtime smoke (consumer → installed .tgz runtime)
$ node smoke.mjs
[0/8] jsdom globals installed
[1/8] import @icoder/sdk as ESM ...   OK
[2/8] construct iCoDer client ...     OK
[3/8] axios peer dep resolves ...     OK
[4/8] import @icoder/embedded ...     OK
[5/8] embedded class extends HTMLElement ... OK
[6/8] <icoder-embedded> registered in jsdom ... OK
[7/8] no Console refs, no workspace: ... OK
[8/8] all 9 SDK resources exported ... OK
=== consumer smoke PASSED ===

# Browser bundle build
$ node build.mjs
dist/bundle.js      144.8kb
dist/bundle.js.map  298.3kb
[bundle] size: 147878 bytes
[sourcemap] version: 3 sources: 67
=== browser bundle build PASSED ===
```

## Files written / modified

| Path | Change |
|---|---|
| `packages/icoder-sdk/src/resources/compliance.ts` | Fixed 4 pre-existing TypeScript errors (constructor type + this.http access) |
| `packages/icoder-sdk/src/index.ts` | 22 re-exports + 12 imports + 1 inline import = added `.js` extensions for NodeNext |
| `packages/icoder-sdk/src/client.ts` | 1 import patched with `.js` |
| `packages/icoder-sdk/src/resources/{oauth,agents,textgen,facts,billing,reviews}.ts` | 1 import each patched with `.js` |
| `packages/icoder-sdk/tsconfig.json` | `module`/`moduleResolution` → NodeNext |
| `packages/icoder-sdk/package.json` | Added `"type": "module"`, `exports` map, `./package.json` subpath |
| `packages/icoder-embedded/package.json` | Added `./package.json` subpath export |
| `packages/icoder-sdk/icoder-sdk-1.0.0-beta.2.tgz` | NEW — built artifact (12.0KB, 30 files) |
| `packages/icoder-embedded/icoder-embedded-2.0.0.tgz` | NEW — built artifact (15.3KB, 7 files) |
| `E:\Corti4C\phase7-external-consumer\package.json` | NEW — consumer project manifest (no workspace refs) |
| `E:\Corti4C\phase7-external-consumer\tsconfig.json` | NEW — strict TS config for type resolution test |
| `E:\Corti4C\phase7-external-consumer\types-test.ts` | NEW — type-resolution assertions (all 11 exported types + classes) |
| `E:\Corti4C\phase7-external-consumer\smoke.mjs` | NEW — 8-step runtime smoke |
| `E:\Corti4C\phase7-external-consumer\build.mjs` | NEW — esbuild browser bundle + sourcemap validator |
| `E:\Corti4C\phase7-external-consumer\entry.mjs` | NEW — bundle entry (imports both packages) |

## Phase 7 §4 compliance

### §4.1 — No parallel implementations ✓

The `.tgz` artifacts are built from the SAME source tree that powers the monorepo's TypeScript workspaces. No code forked, no package recreated. The consumer project reuses what the monorepo ships.

### §4.2 — Browser evidence priority (partial)

Gate 2 is a **packaging** gate — its acceptance is "the .tgz installs + type-resolves + ESM-imports + bundles". Browser-level evidence (Web Component actually rendering in a real browser, firing events, completing a real Run) is deferred to Gate 10. This is honest: Gate 2 ships the installable surface, Gate 10 ships the browser-run proof.

What Gate 2 verifies at the code level:
- jsdom-level Web Component registration (customElements.define succeeds)
- Web Component class extends HTMLElement
- SDK client constructs, resources expose
- esbuild browser bundle builds + emits valid v3 source map

### §4.3 — Server is final security boundary ✓

N/A for Gate 2 — no server changes. But the SDK now correctly does NOT ship any backend secrets, cookies, or session state. The `iCoDerConfig` shape is:

```typescript
{
  baseURL: string;
  auth: { accessToken: string; refreshToken?: string } | ClientCredentials;
  timeout?: number;
  onTokenRefresh?: (...) => void;
  onAuthFailure?: () => void;
}
```

The consumer must supply `auth`. The SDK does not read cookies, localStorage, or implicit Console session state.

### §4.4 — No mocks for acceptance ✓

- Real `npm install` from real `.tgz` files
- Real `node` runtime, real `esbuild` bundler, real `jsdom`
- No mocked imports, no fixture stubs
- Real axios resolution (from npm registry)
- The deferred §7.3 deep smoke (real backend + real DeepSeek) is explicitly NOT mocked — it is deferred, not faked

## Forbidden outputs — all respected ✓

| Forbidden | Status |
|---|---|
| `PUBLIC_NPM_PUBLISHED` | ✓ NOT claimed — `.tgz` files are local-only, not pushed to npm registry |
| `PARTNER_PRODUCTION_READY` | ✓ NOT claimed |
| `BROWSER_E2E_VALIDATED` | ✓ NOT claimed — deferred to Gate 10 |
| `CONSUMER_DEEP_RUN_VALIDATED` | ✓ NOT claimed — §7.3 deferred to Gate 10 |

## Verdict

`PACKAGE_CONSUMER_INSTALL_VALIDATED` (per §7.3's exact tier label)

Plus the explicit qualifier: `BROWSER_BUNDLE_BUILD_OK_DEEP_RUN_DEFERRED_TO_GATE_10`

Both `.tgz` archives install cleanly from outside the workspace, type-check, ESM-import, register their Web Component in jsdom, and bundle for the browser with valid v3 source maps. The §7.3 deep smoke (initialize → authenticate → configureSession → configure → show → run real agent → completed event) is deferred to Gate 10 where the same SDK + widget chain will run against a live backend with real DeepSeek — running it twice would duplicate ¥ cost without adding evidence.

**Not** `PUBLIC_NPM_PUBLISHED` — the `.tgz` files are local artifacts only; no `npm publish` was executed and none is planned in Phase 7.

Carry-forward to Gate 10: re-exercise the same SDK + Web Component chain through Playwright against the live backend mounted at `/examples/*` (Gate 1).
