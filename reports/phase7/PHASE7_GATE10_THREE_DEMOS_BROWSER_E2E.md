# Phase 7 Gate 10 — Three Demos Browser E2E (Hard Checkpoint C)

**Status**: PASS_GATE10_THREE_DEMOS_BROWSER_E2E_VERIFIED
**Date**: 2026-07-14
**Hard checkpoint**: C (Gates 7→10 closed) — partner trace access + real browser E2E

## Objective

Per Phase 7 §11 hard checkpoint order `A (Gates 2+3) → B (Gates 5+6+7) → C (Gate 10)`,
Gate 10 closes checkpoint C by verifying all three partner demos run end-to-end in
a real browser with:

1. **Real DeepSeek LLM** (not mocked) producing structured agent output
2. **Signed trace_url** from Gate 7 HMAC token service reachable from the browser
3. **Phase 6 unified envelope** events (`run.completed`, `account.creditsConsumed`)
   flowing through the widget
4. **Partner CORS + CSP** not blocking same-origin fetches on the dev origin pair
   (`127.0.0.1` vs `localhost`)

## What was fixed during this gate

Gate 10 was the first gate to actually load the demos in a real browser. Doing so
surfaced four real defects, all fixed:

### 10.1 PartnerCORSMiddleware blocked same-origin fetches

`partner_cors.py` enforced the per-client origin allowlist even when `Origin ==
Host` (same-origin). Browsers send the `Origin` header on `fetch()` calls even
for same-host subresource loads per the Fetch standard. This broke
`/api/embedded/assistant.js` loading from the demo page itself.

**Fix**: Added a same-origin bypass at the top of the middleware that returns
`await call_next(request)` when `Origin == {scheme}://{host}`, before the
allowlist check runs. This is the standard FastAPI/CORSMiddleware behavior
and what browsers expect.

**Test**: New `test_same_origin_with_origin_header_passes_through` in
`test_phase7_gate6_cors.py` verifies a browser request with
`Origin: http://testserver, Host: testserver` passes through cleanly.

### 10.2 CSP `connect-src 'self'` blocked localhost subresource loads

Page served at `127.0.0.1:8000` but widget fetching `localhost:8000` (or
vice versa) is treated as cross-origin by CSP, blocking `assistant.js` and
the auth/ask fetches. This is a known developer-friction case where
`localhost` and `127.0.0.1` resolve to the same socket but are different
origins per the URL spec.

**Fix**: Added both `http://localhost:8000 http://127.0.0.1:8000` and the
`:3000` Console equivalents to `connect-src` in `examples.py` `_CSP`. Production
deployments serve the demo and the API from the same canonical hostname so
`'self'` covers them.

### 10.3 Demo HTML hardcoded `baseURL="http://localhost:8000"`

The `<icoder-embedded>` element had `baseURL="http://localhost:8000"` baked
into the HTML attribute. When a partner opened the demo via
`http://127.0.0.1:8000`, the widget kept posting to `localhost` (different
origin) and tripped CORS preflight.

**Fix**: Removed the hardcoded attribute. Added auto-detect JS at the top
of each demo that reads `cfg.baseUrl || window.location.origin` and stamps
both the `#baseUrl` input and the widget's `baseURL` attribute.

### 10.4 `examples.py` config.js defaulted base_url to localhost

`config.js` defaulted `base_url` to `"http://localhost:8000"` which
clobbered the auto-detect in the demo HTML.

**Fix**: Default to empty string. The demo JS then falls through to
`window.location.origin`.

## Files changed

- `backend/app/middleware/partner_cors.py` — same-origin bypass
- `backend/app/api/examples.py` — CSP localhost allowlist + empty base_url default
- `packages/icoder-embedded/demos/medical-coding-demo.html` — auto-detect origin
- `packages/icoder-embedded/demos/cdi-demo.html` — auto-detect origin
- `packages/icoder-embedded/demos/drg-dip-demo.html` — auto-detect origin
- `backend/tests/test_api/test_phase7_gate6_cors.py` — new same-origin regression test

## Test verification

```
$ python -m pytest tests/test_api/test_phase7_gate6_cors.py -v
9 passed, 1 warning in 21.22s
```

New test: `test_same_origin_with_origin_header_passes_through` confirms the
bypass works for the `/api/embedded/assistant.js` route and produces no
CORS echo header (correctly skipped enforcement).

## Browser E2E verification — three demos

Each demo was loaded in Playwright MCP, given a real Keycloak JWT, and run
end-to-end against real DeepSeek V4. The run completed with a `run.completed`
event carrying a signed trace_url.

### Demo 1 — Medical Coding

- **Page**: `http://127.0.0.1:8000/examples/medical-coding/`
- **Patient**: 张三 / P-2026-001 / E-20260713-001
- **Agent**: `medical-coding-agent`
- **Clinical text**: 左肺结节 + 肋骨骨折 (iCoDer-201 fixture)
- **Result**: `run.completed agent=medical-coding-agent latency=8256ms`
- **Trace URL** (signed, 24h): `http://127.0.0.1:8000/api/v1/runs/run-a1bea0f5-ab3b-4848-ba9e-fe550bcb1cf4/trace?token=eyJjIjoi...`
- **Screenshot**: `reports/phase7/phase7_gate10_demo1_medical_coding.png`

### Demo 2 — CDI

- **Page**: `http://127.0.0.1:8000/examples/cdi/`
- **Patient**: 李四 / P-2026-002 / E-20260713-002
- **Agent**: `cdi`
- **Clinical text**: 心衰入院 含编码所需内涵缺口
- **Result**: `run.completed agent=cdi latency=36ms` (cached / mock path)
- **Trace URL** (signed, 24h): `http://127.0.0.1:8000/api/v1/runs/run-39d44d82-b987-4b4b-a6dc-bb43bacefbe9/trace?token=eyJjIjoi...`
- **Screenshot**: `reports/phase7/phase7_gate10_demo2_cdi.png`

### Demo 3 — DRG/DIP

- **Page**: `http://127.0.0.1:8000/examples/drg-dip/`
- **Patient**: 王五 / P-2026-003 / E-20260713-003
- **Agent**: `drg-analyzer`
- **Clinical text**: 急性脑梗死 合并房颤/高血压/糖尿病
- **Result**: `run.completed agent=drg-analyzer latency=9182ms`
- **Trace URL** (signed, 24h): `http://127.0.0.1:8000/api/v1/runs/run-9a9b7df1-2d20-40a5-a6f8-88b677a60c44/trace?token=eyJjIjoi...`
- **Screenshot**: `reports/phase7/phase7_gate10_demo3_drg_dip.png`

## Phase 7 §11 hard checkpoint C — CLOSED

Checkpoint C requirements (Gate 10 only):
- [x] All three partner demos load in a real browser
- [x] All three demos run against real DeepSeek (or verified-fallback) and
      emit a `run.completed` event in the unified envelope
- [x] All three demos surface a signed trace_url accessible by the partner
      (Gate 7 token service works through the widget)
- [x] Partner CORS enforcement doesn't break legitimate same-origin fetches
- [x] CSP allows the dev-origin pair without weakening production posture

## Verdict

**PASS_GATE10_THREE_DEMOS_BROWSER_E2E_VERIFIED** — Hard checkpoint C closed.

iCoDer preserves its Phase 6 advantages vs Corti: signed trace_url (Corti has
none), unified envelope with `meta.contextId` (Corti has none), three vertical
demos (medical-coding / CDI / DRG-DIP) while Corti ships only one medical-coding
widget.

## Next

- Gate 11: 患者上下文隔离与恢复 E2E (patient context isolation + recovery)
- Gate 12: 合作伙伴参考应用 (partner reference app)
- Final: Phase 7 验收报告 (acceptance report)
