# A1B-AE-R.3 — Public Expert + SSRF

**Sub-gate**: R.3 (Public Expert + MCP)
**Date**: 2026-07-23
**Branch**: `phase-a1b/agent-expert-runtime-verification`
**Predecessor**: R.2 (`8eb7d60`)

## Verdict

```
PASS_A1B_AE_R_3_PUBLIC_EXPERT_AND_SSRF_FILED
```

FILED per charter §10 — phase terminal R.6 decides promotion to `_VERIFIED`.

## Scope

R.3 closes the A1B-AE.6/7 gap: PubMed + ClinicalTrials Experts were
Expert-Registry-only stubs that never made live calls. R.3 wires the
live EUtils + CT.gov v2 API integration behind the External-Expert
Gate (already shipped in A1B-AE.7) and adds an SSRF guard wrapping
every outbound MCP / Expert HTTP call.

| A1B-AE gap | R.3 fix |
|---|---|
| PubMed Expert returned `live_search_performed=False` unconditionally | `pubmed_expert.search_async()` performs real EUtils esearch + esummary when gate permits + VCR fixture present OR `allow_live_capture=True` |
| ClinicalTrials Expert same | `clinical_trials_expert.search_async()` performs real CT.gov v2 query under same conditions |
| No VCR-style fixture mechanism | Fixtures persisted at `reports/phase-a1b-runtime/evidence/api_captures/{expert}_{sha256}.json`; replay is the CI-stable path |
| `mcp_wrapper.py` opened sockets to any URL including loopback / RFC1918 / cloud-metadata | New `app.services.ssrf_guard.assert_url_safe()` blocks all RFC1918 / loopback / link-local / metadata hosts BEFORE any TCP connect; McpWrapper calls `_preflight()` on every entry point |
| MCP JSON-RPC routes | Already present at `/mcp/v1/tools/list` + `/mcp/v1/tools/call` (Phase 3-D1); R.3 verifies they work end-to-end |

## Files added / modified

**Added**:
- `backend/app/services/ssrf_guard.py` — host pre-flight checker (BLOCKED_NETWORKS covers 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, 100.64/10, 0/8, ::1, fc00::/7, fe80::/10) + cloud-metadata hostnames + DNS-rebinding defence
- `backend/tests/test_api/test_a1b_ae_r_3_public_expert_ssrf.py` — 31 tests covering gate-deny→0-egress, VCR fixture replay, SSRF blocking, McpWrapper SSRF, MCP JSON-RPC smoke

**Modified**:
- `backend/app/agents/experts/pubmed_expert.py` — added `search_async()` with gate-check + fixture replay + optional live capture (VCR); sync `search()` retained for backward compat with fixture replay path
- `backend/app/agents/experts/clinical_trials_expert.py` — same pattern for CT.gov v2 API
- `backend/app/services/mcp_wrapper.py` — every entry point (`discover_tools` / `call_tool` / `create_expert_config`) now calls `_preflight(url)` which raises `McpSSRFBlocked` on SSRF guard failure

## Design decisions

### Decision tree for live calls

```
query empty?
  └─ yes → empty result, live_search_performed=False
  └─ no
       ↓
External-Expert Gate evaluate()
  └─ deny (LICENCE_REQUIRED / EGRESS_DISABLED / REGION_BLOCKED / PROVIDER_OPT_IN_MISSING)
        └─ hermetic stub, live_search_performed=False, ZERO socket opens
  └─ permit
        ↓
VCR fixture exists for query?
  └─ yes → replay fixture, live_search_performed=True (fixture is primary evidence)
  └─ no
        ↓
allow_live_capture=True?
  └─ yes → real HTTP call, save response as new fixture, live_search_performed=True
  └─ no  → hermetic stub explaining how to seed fixture
```

The default is deny (egress_enabled defaults to False) — hermeticity is
preserved unless a caller explicitly opts in.

### VCR fixture format

```json
{
  "expert": "pubmed",
  "query": "sepsis-3 definition",
  "captured_at": "2026-07-23T...+00:00",
  "payload": {
    "articles": [{"pmid": "...", "title": "...", ...}],
    "total": 1
  }
}
```

Filename: `{expert}_{sha256(query)[:16]}.json` under
`reports/phase-a1b-runtime/evidence/api_captures/`. The SHA prefix
makes the fixture stable across runs while keeping the filename
human-guessable.

### SSRF guard design

- **Blocked networks**: all RFC1918 (10/8, 172.16/12, 192.168/16), loopback
  (127/8, ::1), link-local (169.254/16, fe80::/10), CGN (100.64/10),
  "this host" (0/8), ULA (fc00::/7), explicit cloud-metadata hostnames
  (169.254.169.254, metadata.google.internal, metadata.azure.com).
- **DNS rebinding defence**: when the URL host is a DNS name (not IP
  literal), `socket.getaddrinfo()` resolves it and checks every record.
  If any record lands in a blocked network, the URL is rejected.
- **Fail-closed on DNS failure**: an unresolved host returns
  `permitted=False`. Callers needing to allow unresolved hosts must
  opt in explicitly (no current caller does).
- **Scheme allowlist**: only `http` and `https` permitted.

The guard is pure-Python synchronous (no I/O except DNS) so it can run
in tight loops and inside test assertions without an event loop.

### McpWrapper SSRF integration

`McpWrapper._preflight(url)` calls `ssrf_guard.assert_url_safe()` and
raises the new `McpSSRFBlocked` exception on rejection. All 3 entry
points (`discover_tools`, `call_tool`, `create_expert_config`) call
`_preflight` BEFORE any `httpx.AsyncClient` operation. Charter §11
forbidden ops honoured (no `push`, no `merge --no-ff` to master, etc).

## Test evidence

```
tests/test_api/test_a1b_ae_r_3_public_expert_ssrf.py   31 passed
tests/test_api/test_a1b_ae_6_external_experts.py       17 passed (A1B-AE.6 regression)
```

### Mandatory negative tests (per plan)

| Scenario | Expected | Verified |
|---|---|---|
| PubMed gate deny → 0 egress | `_live_esearch` not invoked | ✓ |
| ClinicalTrials gate deny → 0 egress | `_live_ctgov` not invoked | ✓ |
| SSRF: `http://169.254.169.254/` | `permitted=False` | ✓ |
| SSRF: `http://10.0.0.5/` | `permitted=False` | ✓ |
| SSRF: `http://127.0.0.1/` | `permitted=False` | ✓ |
| SSRF: `http://[::1]/` | `permitted=False` | ✓ |
| McpWrapper.discover_tools on metadata URL | `McpSSRFBlocked` raised | ✓ |
| McpWrapper.call_tool on loopback URL | `McpSSRFBlocked` raised | ✓ |
| McpWrapper.create_expert_config on RFC1918 | `McpSSRFBlocked` raised | ✓ |
| drugbank without licence token | `LICENCE_REQUIRED` | ✓ |
| web-search without dual opt-in | `PROVIDER_OPT_IN_MISSING` | ✓ |
| web-search with provider + tenant opt-in | `permitted=True` | ✓ |

### Live capture not run in CI

The live EUtils + CT.gov calls are NEVER run in CI. They run only when a
human operator invokes `search_async(..., allow_live_capture=True)`
explicitly to seed a new fixture. The fixture-replay path is the
CI-stable path. The first such capture for any production query will
produce a new fixture file under
`reports/phase-a1b-runtime/evidence/api_captures/` and is considered a
separate artifact (with its own SHA-256 + timestamp).

## 5-tuple state (unchanged)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

## Forbidden verdicts (8) — honoured

None of `PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED` appears in this sub-gate, its report, or its commit message.

## Charter §11 forbidden ops — honoured

- No `git push` (branch remains local)
- No `merge --no-ff` to master
- No `amend`
- No `rebase`
- No `reset --hard`
- No `git add -A` / `-a` (explicit file list)
- No force-push

## R.3 status — complete

R.3 (Public Expert + SSRF) is now complete in 1 commit:
- PubMed + ClinicalTrials Experts have real live paths behind the gate
- VCR fixture mechanism preserves "real-call artefact" + "CI hermeticity"
- SSRF guard wraps every outbound HTTP egress point (PubMed / CT / MCP wrapper)
- MCP JSON-RPC routes (Phase 3-D1) re-verified

## Next

R.4 — Local Expert completion (Calculator catalogue expansion + Memory + Interviewing state machine).
