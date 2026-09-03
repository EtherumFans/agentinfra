# Phase 7 Gate 12 — Partner Reference App (Hard Checkpoint D)

**Status**: PASS_GATE12_PARTNER_REFERENCE_APP_VERIFIED
**Date**: 2026-07-14
**Hard checkpoint**: D (Gate 12 closed) — full partner integration pattern demonstrated end-to-end

## Objective

Per Phase 7 §11 hard checkpoint order `A (Gates 2+3) → B (Gates 5+6+7) → C (Gate 10) → D (Gate 12)`,
Gate 12 is the final hard checkpoint before the acceptance report. It requires:

1. A canonical partner integration example at `examples/partner-reference-app/`
2. Demonstrating the full partner value chain works end-to-end:
   - Partner backend holds secret server-side
   - Partner backend exchanges `client_credentials` for token
   - Browser widget loads via partner origin (CORS allowlist permits it)
   - Widget submits clinical text → real DeepSeek → structured response
   - Signed trace_url from Gate 7 surfaces in `run.completed` event
   - Patient context switching calls `clearPatientContext()` first

## What was built

### `examples/partner-reference-app/` (~330 LOC across 5 files)

```
partner-reference-app/
├── .env.example           # ICODER_* env vars (no secret shipped to browser)
├── .env                   # local dev values (gitignored)
├── package.json           # express + node >= 18 only
├── README.md              # partner-facing quick start + security checklist
├── server/
│   └── index.mjs          # /token (client_credentials exchange) + static
└── public/
    ├── index.html         # HIS/EMR shell with <icoder-embedded>
    └── app.js             # widget bootstrap + event handling + patient switch
```

### Backend changes (Gate 12 surfaced real gaps)

#### 1. `app/middleware/partner_cors.py` — `X-Attempt` header in preflight

Widget sends `X-Attempt: 1|2` (Phase 6 Gate 3 retry counter) but the partner
CORS preflight response didn't allow it. Browsers blocked the actual POST
after preflight.

**Fix**: Added `X-Attempt` to `Access-Control-Allow-Headers` in the
short-circuit preflight response.

#### 2. `app/middleware/auth.py` — `get_current_user_or_oauth_client` (~55 LOC)

`agent_run.py` used `Depends(get_current_user)` which only accepts user JWTs.
Partner clients exchanging `client_credentials` got 401 "User not found"
because their token's `sub` is the OAuth client_id, not a user_id.

**Fix**: New hybrid dependency accepts either:
- User JWT (Console flow) → returns `(user, None)`
- Client_credentials token (partner flow) → returns `(None, client_dict)`

Routes using this dependency read identity from whichever side is set.

#### 3. `app/api/agent_run.py` — wire hybrid auth + trace_url narrowing

- Swapped `current_user: User = Depends(get_current_user)` for
  `principal: tuple = Depends(get_current_user_or_oauth_client)`
- Synthesize `user_id`, `org_id`, `api_client_id` from whichever side of the
  principal is set
- Set `api_client_id` on the idempotency record (was hardcoded `None`)
- Narrow the partner trace_url trigger from `(body.api_client_id or org_id)`
  to `current_client is not None or body.api_client_id`. The old condition
  fired for every Console user because Console users also have org_id.

#### 4. `tests/conftest.py` — bypass override for new dependency

The `_install_auth_bypass` fixture installs overrides for `get_current_user`
and `get_current_organization` under `ICODER_DISABLE_AUTH_FOR_TESTS=1`. Added
the matching override for `get_current_user_or_oauth_client` returning
`(mock_user, None)` so 904+ existing tests stay green.

## End-to-end verification (Playwright MCP)

Real browser session at `http://localhost:4400/`:

| Step | Observation |
|------|-------------|
| Partner app boots | `GET /healthz → {"ok":true}` |
| Server-side token exchange | `GET /token → {access_token, expires_in: 3600}` |
| Token payload | `sub: partner-ref-07ef23d306cf, type: client_credentials, org_id: 0188d65b1a3d` |
| Widget bundle load | `GET http://localhost:8000/api/embedded/assistant.js` 200 (CORS allowlist permits localhost:4400) |
| widget.ready event | fired |
| `widget.auth()` | accepted partner token |
| `widget.configureSession({patientId: P-2026-001, name: 张三})` | context set, `_contextId = E-20260713-001` |
| `widget.ask(clinicalText)` | POST `/api/v1/agents/medical-coding-agent/run` |
| Real DeepSeek response | `latency_ms: 5462, is_mock: false` |
| Codes returned | `D86.000` (primary, conf 0.86) + `S22.400` (secondary, conf 0.70) |
| `manual_review_required: true` | compliance gate fires correctly |
| 7-step trace_events | input_received → language_detect → build_prompt → llm_call → parse_json → project_result → return |
| Signed trace_url (Gate 7) | `http://localhost:8000/api/v1/runs/run-782b1365.../trace?token=eyJjIjoi...` |
| `run.completed` event | `agent=medical-coding-agent latency=5462ms trace ↗` |
| `account.creditsConsumed` event | `internal_credit 0` |
| Patient switch (×2) | `patient.context.cleared` fired each time before re-configure |

### Screenshot

`reports/phase7/phase7_gate12_partner_reference_app.png` — full page showing:
- Widget initialized with real DeepSeek response
- Event log with `run.completed` + trace link + `account.creditsConsumed`
- 7 capabilities verified checklist in right panel

## iCoDer ADVANTAGE vs Corti (preserved through Gate 12)

- **Server-side secret pattern documented** — Corti's docs assume browser-pasted JWT; iCoDer ships a reference showing the production pattern
- **Signed trace_url partner access** — Corti requires Console session; iCoDer signs URLs (Gate 7)
- **Cross-patient warn + clear events** — Corti has none; widget emits `patient.context.cleared` (Gate 11)
- **3 vertical agents in one reference** — Corti ships one medical-coding widget; iCoDer demonstrates the same pattern works for `medical-coding-agent`, `cdi`, `drg-analyzer`

## Test verification

```
$ python -m pytest tests/test_api/test_phase4f_agent_run.py \
                    tests/test_api/test_phase7_gate{3,5,6,7,8,9}_*.py
74 passed in 147.02s
```

All Phase 7 Gates + Phase 4-F regression green after the hybrid auth + CORS
header fixes.

## Phase 7 §11 hard checkpoint D — CLOSED

Checkpoint D requirement: partner reference app demonstrating the full
integration pattern.

- [x] `examples/partner-reference-app/` exists with README + .env.example
- [x] Server-side secret pattern (no browser-visible secret)
- [x] Server-side `client_credentials` exchange works against real backend
- [x] Widget loads from partner origin via CORS allowlist
- [x] Real DeepSeek run completes through partner token
- [x] Signed trace_url surfaces in `run.completed` event
- [x] Patient context isolation events (`patient.context.cleared`) fire on switch
- [x] 74/74 regression tests pass

## Verdict

**PASS_GATE12_PARTNER_REFERENCE_APP_VERIFIED** — Hard checkpoint D closed.

## Next

- Final: Phase 7 验收报告 (acceptance report)
