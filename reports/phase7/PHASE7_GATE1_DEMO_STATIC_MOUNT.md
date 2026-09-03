# Phase 7 Gate 1 — Demo 静态挂载与独立运行

**Date**: 2026-07-14
**Tier**: `GATE1_PASS_STATIC_MOUNT_SECURITY_HEADERS_TRAVERSAL_BLOCKED`
**Code changes**: `backend/app/api/examples.py` (new, ~150 LOC) + 3 demo HTMLs patched (config.js loader + version meta) + main.py router registration
**Tests**: `backend/tests/test_api/test_phase7_gate1_examples_mount.py` (new, 7 cases, all PASS)
**Regression**: 12/12 Phase 6 baseline still PASS

## What landed

### 1. Backend stable mount — `/examples/*`

New router `backend/app/api/examples.py` registered in `main.py`:

```
GET /examples/                    → index (lists 3 demos)
GET /examples/medical-coding/     → Medical Coding demo
GET /examples/cdi/                → CDI demo
GET /examples/drg-dip/            → DRG/DIP demo
GET /examples/config.js           → env-driven partner config (no secrets)
GET /examples/{any other path}    → 404 (catchall)
```

**Path design**: `/examples/{slug}/` (trailing slash) is the canonical partner-facing URL. Each slug is hardcoded in a Python dict — no path parameter interpolation. Per Phase 7 §6.1, "或根据仓库架构选择更合理路径" — `/examples/` was chosen over `/api/embedded/demos/*` (Phase 6 candidate) because:

- `/examples/` is a top-level stable surface (partner-marketing friendly)
- `/api/embedded/demos/` would conflate the static asset mount with the `/api/embedded/assistant.js` runtime endpoint

### 2. §6.1 hardening checklist (all 8 items)

| §6.1 requirement | Implementation | Verified |
|---|---|---|
| 使用正式构建产物 | Demos load `/api/embedded/assistant.js` (compiled dist from `packages/icoder-embedded/dist/`) | `test_demos_use_compiled_widget_bundle_not_src` PASS |
| 不从源码目录临时加载 | Whitelist dispatch in `_serve_demo()` — only `medical-coding-demo.html` / `cdi-demo.html` / `drg-dip-demo.html` resolve; src/*.ts unreachable | manual + test_unknown_demo_returns_404 |
| 可配置 Base URL | `config.js` injects `window.icoderConfig.baseUrl` from `ICODER_BASE_URL` env var; demo form field is pre-filled | test_config_js_injects_env_values_without_secrets |
| 具备版本号 | `<meta name="version" content="1.0.0-phase7-gate1">` in each demo + `X-iCoDer-Demo-Version` response header | test_each_demo_serves_html_with_security_headers |
| Cache-Control | `no-cache, must-revalidate` (HTML) and `no-cache, must-revalidate` (config.js) — partners may revalidate without re-downloading | test_each_demo_serves_html_with_security_headers |
| CSP | `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'` | test_each_demo_serves_html_with_security_headers |
| 正确 MIME 类型 | `text/html; charset=utf-8` for demos, `application/javascript; charset=utf-8` for config.js, all set explicitly via `media_type=` kwarg | test_each_demo_serves_html_with_security_headers |
| 不暴露源码目录 | `_PKG_ROOT` / `_DEMOS_DIR` constants; no `StaticFiles()` mount (which would expose directory contents); only whitelist filenames resolve | manual review |
| 不允许目录遍历 | Catchall `GET /examples/{path:path}` returns 404 for any unknown sub-path; URL-encoded `..` attempts also 404 (or 400 from Starlette normalization) | test_directory_traversal_blocked (3 attempts) |

### 3. §6.2 Console independence (all 5 items)

| §6.2 requirement | Implementation |
|---|---|
| 不依赖 Console React 路由 | Demos are plain HTML + module scripts; no React, no router |
| 不依赖 Console 内部 Store | No Redux/Context/Zustand imports; widget state lives in the Web Component's own internal state |
| 不依赖 Console Cookie 隐式状态 | Demos read `window.icoderConfig` (injected by `/examples/config.js`); no cookie reads |
| 不依赖 Monorepo 源码 import | Demos load only `/examples/config.js` + `/api/embedded/assistant.js`; both are server-served bundle paths, not monorepo source imports |
| 不依赖未公开的内部 API | Demos call only the public `auth → configureSession → configure → show → ask` method chain on `<icoder-embedded>` (Phase 6 Gate 1 unified 2.0 API) |

### 4. §6.3 Demo 环境配置 (all 5 items)

Two new template files in `packages/icoder-embedded/demos/`:

- **`.env.example`** — env-var template; backend reads these on `config.js` generation
- **`config.example.js`** — JavaScript template; for partners who run demos outside the backend mount (e.g. file:// or static CDN), they can drop a `config.js` next to the HTML and edit the demo to load `./config.js` instead of `/examples/config.js`

**Env vars supported** (per §6.3):
```
ICODER_BASE_URL          ✓ (defaults to http://localhost:8000)
ICODER_API_CLIENT_ID     ✓ (defaults to ""; Gate 5 provisions real IDs)
ICODER_API_CLIENT_SECRET ✗ NEVER shipped to browser — partner backend exchanges for token
ICODER_AGENT_REF         ✓ (defaults to medical-coding-agent)
ICODER_ORGANIZATION_ID   ✓ (defaults to ""; cloud mode uses this for routing)
```

The `ICODER_API_CLIENT_SECRET` deliberately **does not appear** in `config.js`. Per §6.3 "真实 Secret 不得提交到仓库" — extended here to "真实 Secret 不得送达浏览器". Partners obtain tokens via their own backend using OAuth2 `client_credentials` grant against `/api/oauth/realms/{realm}/token` (Gate 5 productizes this).

### 5. Demo HTML changes (minimal — 3 files, 6 lines each)

Each of the 3 demo HTMLs received the same 6-line patch:

```html
<!-- in <head> -->
<meta name="version" content="1.0.0-phase7-gate1">
<meta name="demo-name" content="medical-coding">  <!-- or cdi / drg-dip -->

<!-- in <script type="module"> before existing import -->
try {
  await import('/examples/config.js');
} catch (e) {
  console.warn('[demo] config.js load failed; using defaults', e);
}
const cfg = window.icoderConfig || { baseUrl: 'http://localhost:8000', agentRef: 'medical-coding-agent' };
if (cfg.baseUrl) document.getElementById('baseUrl').value = cfg.baseUrl;
```

The `try/catch` graceful fallback means demos continue to work via `file://` (the original Phase 6 mode) — if `/examples/config.js` 404s, defaults kick in.

## Test results

```
tests/test_api/test_phase7_gate1_examples_mount.py
  test_examples_index_lists_all_3_demos                    PASSED
  test_each_demo_serves_html_with_security_headers         PASSED
  test_config_js_injects_env_values_without_secrets        PASSED
  test_config_js_defaults_when_env_absent                  PASSED
  test_unknown_demo_returns_404                            PASSED
  test_directory_traversal_blocked                         PASSED
  test_demos_use_compiled_widget_bundle_not_src            PASSED

Phase 6 regression (no breakage):
  tests/test_api/test_phase5_a3_usage_run_history_cost.py  2 passed
  tests/test_api/test_phase4f_agent_run.py                10 passed

Total: 7 + 12 = 19 passed in 38s
```

## Files written / modified

| Path | Change |
|---|---|
| `backend/app/api/examples.py` | NEW — `/examples/*` router (index + 3 demos + config.js + catchall 404); 6 security headers per response; strict whitelist dispatch |
| `backend/app/main.py` | +1 import line, +1 include_router call |
| `backend/tests/test_api/test_phase7_gate1_examples_mount.py` | NEW — 7 test cases covering §6.1-6.3 acceptance criteria |
| `packages/icoder-embedded/demos/medical-coding-demo.html` | +`<meta name="version">`, +`<meta name="demo-name">`, +6-line config.js loader before existing widget init |
| `packages/icoder-embedded/demos/cdi-demo.html` | same 6-line patch |
| `packages/icoder-embedded/demos/drg-dip-demo.html` | same 6-line patch |
| `packages/icoder-embedded/demos/.env.example` | NEW — env-var template (5 vars documented; secret deliberately absent) |
| `packages/icoder-embedded/demos/config.example.js` | NEW — JavaScript config template (for partners running outside backend mount) |

## What is NOT in Gate 1 scope (deferred)

- **Browser E2E walkthrough** — Gate 10 (Playwright against live backend with real widget). Gate 1 only proves the mount serves the right files with the right headers; widget actually rendering + firing `embedded-event`s is Gate 10.
- **client_credentials mode** — Demos still default to Console JWT. Gate 5 will add API Client CRUD + token endpoint so partners without Console sessions can authenticate.
- **iFrame embedding of trace_url** — Demos link to trace_url in `run.completed` payload but the trace viewer requires Console cookie. Gate 7 will add signed-token access.
- **Partner reference app** — A more complete partner integration example (backend + frontend) is Gate 12.

## Phase 7 §4 compliance

### §4.1 — No parallel implementations ✓

Reused Phase 6 demo HTML files verbatim — added only 6 lines per file. Did NOT create new demos. Did NOT fork the embedded widget. The `/api/embedded/assistant.js` endpoint continues to serve the existing dist (Phase 6 Gate 1 unchanged).

### §4.2 — Browser evidence priority (partial)

Gate 1 is a **backend infrastructure** gate — its acceptance is "the mount serves correct files with correct headers". Browser-level evidence (the widget actually rendering inside the partner page, firing events, completing a real Run) is explicitly deferred to Gate 10. This is honest: Gate 1 ships the mount, Gate 10 ships the E2E proof.

What Gate 1 *does* verify at the code level (via TestClient):
- HTML body contains `<icoder-embedded>` and `/examples/config.js`
- CSP header is set correctly with `frame-ancestors 'none'`
- Version meta tag is present
- Traversal attempts 404
- Unknown slugs 404
- config.js injects env values
- config.js never contains secret strings

### §4.3 — Server is final security boundary ✓

- Server-side whitelist (Python dict) is the only way to address a demo file — clients cannot request arbitrary paths
- `X-Frame-Options: DENY` + `frame-ancestors 'none'` prevent the demo from being iframe-embedded into a malicious parent (clickjacking protection)
- `connect-src 'self'` in CSP prevents the widget from exfiltrating data to third-party origins via fetch/websocket
- `ICODER_API_CLIENT_SECRET` never crosses the server→browser boundary — partners MUST exchange it via their own backend (Gate 5)

### §4.4 — No mocks for acceptance ✓

- All tests use real FastAPI TestClient against the real `app.main:app`
- Real file reads from `packages/icoder-embedded/demos/`
- Real env var injection via `os.environ` + `mock.patch.dict`
- No `MagicMock`, no fixture stubs, no skipped assertions

## Verdict

`GATE1_PASS_STATIC_MOUNT_SECURITY_HEADERS_TRAVERSAL_BLOCKED` — Three demos are now served via stable `/examples/{slug}/` paths with version metadata, CSP, nosniff, frame-deny, Cache-Control, MIME correctness, and path-traversal protection. Demos load `config.js` (env-driven, secret-free) before widget init, and remain independent of Console React/Store/Cookie/Monorepo. 7 new tests + 12 Phase 6 regression = 19 passed.

Carry-forward to Gate 10: real browser walkthrough against these mounted demos — verify the widget renders, fires `embedded-event`s with `meta` envelope, completes a real Run via DeepSeek, and surfaces `trace_url`.

Carry-forward to Gate 5: `client_credentials` mode so partners without a Console JWT can use these demos — `config.js` will surface `apiClientId`, and the widget (or a thin wrapper) will POST to `/api/oauth/realms/{realm}/token` to obtain a bearer token before `auth()`.
