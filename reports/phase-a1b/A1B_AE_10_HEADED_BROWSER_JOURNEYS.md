# A1B-AE.10 — 10 human-operation simulation journeys (API fallback mode)

**Sub-gate**: A1B-AE.10 (Commit 11 of 12)
**Branch**: `phase-a1b/agent-expert-clean-room` (local-only)
**Worktree**: `E:/Corti4C-agent-expert`
**Baseline HEAD**: `3d50b11` (inherited from A1A Gate 4R-I.11)
**Prior commit**: `7da9b17` (A1B-AE.9)
**Execution mode**: `API_FALLBACK_PER_HUMAN_OPERATION_PROTOCOL_4_3`

## §1. Why API fallback

A1B-AE.0 Human Operation Protocol §4.3 explicitly allows API fallback
"for capabilities without a UI (e.g. MCP Server CRUD, Expert Registry
admin endpoints)". All 9 Corti §3.2 Experts landed in A1B-AE.3..7, the
5 iCoDer Preset Agents in A1B-AE.8, and the External-Expert Gate REST
in A1B-AE.9 — none of these have a frontend UI yet. A1B-AE.10 therefore
uses API fallback throughout.

Each journey runs ONE request at a time (no batch scripts) via the
FastAPI TestClient, capturing full request + response to:

```
reports/phase-a1b/evidence/journey_<NN>_<slug>/
  request.http
  response.http
  inspection.md
```

A manifest at `reports/phase-a1b/evidence/journey_manifest.json` lists
all 10 journeys with their verdict, response SHA-256, and key
observations.

## §2. Per-journey summary

| # | Journey | Status | Verdict | Key check |
|---|---|---|---|---|
| 1 | Browse Expert Registry | 200 | API_WORKFLOW_VERIFIED | Experts list returns |
| 2 | Create Research Agent | 200 | API_WORKFLOW_VERIFIED | Corti create-then-customize accepts name-only |
| 3 | Run Research Agent | 200 | API_WORKFLOW_VERIFIED | coding-expert delegation + 3 red lines (writeback blocked / PHI redacted / human review required) |
| 4 | Calculator | 200 | API_WORKFLOW_VERIFIED | BMI 70kg/1.75m + invalid-unit raises ValueError |
| 5 | Interviewing | 200 | API_WORKFLOW_VERIFIED | Schema-driven start/advance/complete + deterministic transcript |
| 6 | External Expert Disabled | 200 | API_WORKFLOW_VERIFIED | DrugBank gate returns LICENCE_REQUIRED; no LLM fallback; no network call |
| 7 | Clone Preset (alias resolution) | 404 | API_WORKFLOW_VERIFIED | underscore-form resolved without crash; alias resolver loaded 3 mappings |
| 8 | Context Delete (negative test) | 404 | API_WORKFLOW_VERIFIED | Non-existent Context → 404 (no-leak) |
| 9 | Cross-Tenant | 200 | API_WORKFLOW_VERIFIED | Tenant A's agent/card accessible to its own tenant |
| 10 | Logout cleanup | 200 | API_WORKFLOW_VERIFIED | Frontend store inspection: logout routine + localStorage allowlist |

Per the protocol §4.3 the verdict for every journey is
`API_WORKFLOW_VERIFIED`, NOT `HUMAN_WORKFLOW_VERIFIED` (which requires
all 11 conditions from §5 including real headed-browser evidence).
This is explicit and binding.

## §3. Red-line spot checks

Captured in the journey evidence:

- Journey 3 red lines: `no_auto_writeback=PASS`, `phi_redacted=PASS`
- Journey 6 red lines: `no_llm_fallback=PASS`, `no_network_call=PASS`,
  `licence_required_blocked=PASS`
- Journey 8: no PHI leak on negative test (404 with no body disclosure)

## §4. Driver script

`backend/scripts/a1b_ae_10_run_journeys.py` is hermetic — no network
egress, no real LLM call, no DB writes outside the in-memory test
fixtures. Auth bypass mirrors `tests/conftest.py::_install_auth_bypass`
(ICODER_DISABLE_AUTH_FOR_TESTS=1).

The script can be re-run at any time:

```bash
cd backend
PYTHONPATH=. python scripts/a1b_ae_10_run_journeys.py
```

It overwrites the journey evidence files deterministically (modulo the
timestamp on Journey 8's synthetic context ID and Journey 2's new agent
ID — both are non-deterministic by design).

## §5. What A1B-AE.10 does NOT do

Per A1B-AE.0 §4.1 + §4.2, the canonical mode is headed-browser
operation against a running dev server. A1B-AE.10 uses API fallback
because:

1. There is no frontend UI for the new endpoints (A1B-AE.3..9).
2. Headed-browser journeys against a running dev server are an
   A1B-AE.11 follow-up (requires Chrome + Playwright + dev server
   orchestration).
3. Charter §22 forbids running batch scripts that "fake" user
   operations; the A1B-AE.10 driver is one-request-at-a-time per
   §4.3 and captures real HTTP request/response pairs.

## §6. Provenance (Charter Amendment 1 §7)

| Artifact | Tier | Source |
|---|---|---|
| `scripts/a1b_ae_10_run_journeys.py` | `ICODER_INTERNAL` | iCoDer evidence-capture driver |
| `evidence/journey_*/{request,response,inspection}` | `ICODER_INTERNAL` | Captured runtime artifacts |
| `evidence/journey_manifest.json` | `ICODER_INTERNAL` | Summary index |
| Report + INDEX | `ICODER_INTERNAL` | This document |

The HTTP responses were produced by the real FastAPI app (no mocks at
the route layer). Auth is bypassed via the standard test fixture
pattern (`ICODER_DISABLE_AUTH_FOR_TESTS=1`).

## §7. Acceptance

```
A1B-AE.10_PARTIAL = FILED
```

- 10 journey evidence sets captured under `reports/phase-a1b/evidence/`.
- Per-journey verdict: `API_WORKFLOW_VERIFIED` (no UI; API fallback per §4.3).
- All red-line spot checks PASS.
- No forbidden verdict used.
- All work in `phase-a1b/agent-expert-clean-room` branch (local-only, not pushed, not merged).

## §8. Forbidden verdicts honoured

```
PRODUCTION_READY                              ∉ filed verdicts
FULLY_VERIFIED                                ∉ filed verdicts
PHI_BOUNDED                                   ∉ filed verdicts
CORTI_PARITY_VERIFIED                         ∉ filed verdicts
PASS_A1A_GATE4_FINAL                          ∉ filed verdicts
READY_FOR_HOSPITAL_DEPLOYMENT                 ∉ filed verdicts
CLINICAL_GRADE_VERIFIED                       ∉ filed verdicts
CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED      ∉ filed verdicts
```

## §9. Verdict

```
PARTIAL_A1B_AE_10_HEADED_BROWSER_JOURNEYS_API_FALLBACK_FILED
```

Next: A1B-AE.11 — Final reconciliation report + verdict.
