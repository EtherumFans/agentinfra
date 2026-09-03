# Phase A1B-AE — Human-Operation Simulation Protocol (A1B-AE.0)

**Charter**: `A1B_AE_0_CHARTER_AND_BASELINE.md` (v1.0, 2026-07-22)
**Execution mode**: `HUMAN_OPERATION_SIMULATION_REQUIRED`

---

## §1. Why this protocol exists

Phase A1B-AE forbids the following shortcuts as primary evidence:

- grep / OpenAPI / HTML scrape / batch curl / schema generation /
  unit testing only / filename-based inference / Corti-marketing inference
- direct DB writes to fake user-operation results
- "API returns 200, therefore done" reasoning
- "test passes, therefore Agentic parity" reasoning

Every capability must traverse:

```
human observation
   → contract record
      → independent design
         → implementation
            → human-style run
               → negative test
                  → evidence archive
```

This protocol defines the operations permitted at each step.

## §2. Browser environment requirements

- Real headed Chrome / Chromium / Playwright **headed** mode.
- Standard desktop viewport (≥1280 × 800).
- Normal user locale; noWebDriver-only fingerprints.
- No JavaScript injection to modify page state.
- No auth bypass, captcha bypass, Cloudflare bypass, or robots bypass.
- On 401 / 403 / captcha / non-public content: **STOP** and mark
  `BLOCKED_BY_ACCESS_CONTROL`. Do not guess page contents.
- If no headed browser is available: mark
  `BLOCKED_BY_BROWSER_ENVIRONMENT`. **Never** replace with static
  source-code inspection.

## §3. Corti public documentation — human observation procedure

### §3.1 Entry points (clean-room baseline)

- `https://docs.corti.ai/`
- `https://docs.corti.ai/agentic/overview`
- `https://docs.corti.ai/agentic/architecture`
- `https://docs.corti.ai/agentic/experts`
- `https://docs.corti.ai/agentic/experts/available-experts`
- Per-expert reference pages (only those enumerated in the public
  Available Experts index)
- `https://docs.corti.ai/agentic/agents/agent-api-reference` (public)

### §3.2 Per-page step protocol

For each page, the operator (Claude Code) MUST produce, in
`reports/phase-a1b/evidence/corti_observation/<page_slug>/`, the following
artefacts:

| Artefact | Filename | Purpose |
|---|---|---|
| Step log | `step_log.json` | one row per action (see §3.3) |
| Before screenshot | `before_<step_id>.png` | viewport before action |
| After screenshot | `after_<step_id>.png` | viewport after action |
| Visible-text snapshot | `visible_text.txt` | text a human reader sees |
| URL manifest | `urls.json` | all URLs the page links to |
| Sanitized HAR | `network.sanitized.har` | sanitized network capture (PHI/secret-stripped) |
| Console log | `console.log` | browser console output |
| SHA-256 manifest | `sha256.json` | hashes of every artefact above |

### §3.3 Step-log row schema

```json
{
  "step_id": "<page_slug>-<NN>",
  "timestamp": "2026-07-22T<HH:MM:SS>Z",
  "page_title": "<title>",
  "page_url": "<url>",
  "action": "click|scroll|expand|copy|type|wait",
  "visible_target": "<human-visible label>",
  "locator_strategy": "role|label|text|xpath|css",
  "locator_value": "<value>",
  "expected_result": "<one-line expectation>",
  "actual_result": "<one-line observation>",
  "screenshot_before": "before_<step_id>.png",
  "screenshot_after":  "after_<step_id>.png",
  "status": "PASS|DIFF|UNKNOWN|BLOCKED_BY_ACCESS_CONTROL|BLOCKED_BY_BROWSER_ENVIRONMENT",
  "notes": "<optional deltas, missing items, surprises>"
}
```

### §3.4 Rules of engagement

1. One action at a time. Wait for page to settle before next action.
2. Prefer `role`, `label`, `text`, or visible-button locators.
3. Expand request / response schemas fully before capture.
4. Inspect error responses (4xx / 5xx), auth headers, pagination, and
   examples explicitly.
5. If a page is publicly marked Beta / Preview / Internal / Login-required,
   record that and proceed only with the publicly available content.
6. Do not paste Corti example prompts into production prompts. They may
   be used as *design inputs* to the clean-room re-authoring process
   described in Charter §7.
7. Sanitize all HAR files: strip Authorization headers, cookies, query
   tokens, and anything matching a PHI pattern before archiving.

## §4. iCoDer product — human observation procedure

### §4.1 Entry points (clean-room baseline)

- Frontend dev server: `http://localhost:5173` (Vite) — to be confirmed
  in Commit 11 evidence.
- Backend API: `http://localhost:8000` (FastAPI).
- Synthetic test credentials are provided via the test-seed fixture
  (created in A1B-AE.5); real user accounts are out of scope.

### §4.2 10 mandatory journeys

| # | Journey | Primary capability verified |
|---|---|---|
| 1 | Browse Expert Registry | Expert Registry public list + filters + license gate UX |
| 2 | Create Research Agent | Agent CRUD + Expert selection + Agent Card preview |
| 3 | Run Research Agent | Message → Task → Context + PubMed/Clinical Trials citation trace |
| 4 | Calculator | Deterministic Medical Calculator (BMI + invalid-unit error path) |
| 5 | Interviewing | Schema-driven questionnaire: start / interrupt / resume / complete / artifact |
| 6 | External Expert Disabled | DrugBank LICENSE_REQUIRED; no LLM fallback; no network call |
| 7 | Clone Preset | Clone Coding Assistant; rename; verify tenant ownership; preset untouched |
| 8 | Context Delete | Delete Context; 404 on re-read; content scrub; minimal audit retained |
| 9 | Cross-Tenant | Tenant A creates; Tenant B cannot read (404 no-leak); audit confirms |
| 10 | Logout cleanup | localStorage / sessionStorage / IndexedDB clear of PHI / Context / messages |

Each journey records the same artefact set as Corti observation
(§3.2) plus a JUnit evidence file under
`reports/phase-a1b/evidence/journey_<N>/`.

### §4.3 API fallback (only when no UI exists)

For capabilities without a UI (e.g. MCP Server CRUD, Expert Registry
admin endpoints), the operator MUST:

1. Execute one curl command at a time (no batch scripts).
2. Capture full request headers + body to `request.http`.
3. Capture full response headers + body + status to `response.http`.
4. Visually inspect the response JSON (recorded in `inspection.md`).
5. Mark the capability `API_WORKFLOW_VERIFIED` (not `HUMAN_WORKFLOW_VERIFIED`).

Direct DB queries are permitted *only* as secondary evidence to
confirm tenant ownership, Task state, Context deletion, audit record
presence, and secret-not-in-plaintext. They never substitute for the
API / UI operation.

## §5. HUMAN_WORKFLOW_VERIFIED — 11 conditions

A capability earns `HUMAN_WORKFLOW_VERIFIED` only when **all** of the
following are independently reproduced from evidence:

1. The capability is discoverable from a UI or public API entrypoint.
2. A normal user can configure it through visible steps.
3. It runs successfully.
4. The successful result is comprehensible to the user.
5. Error states are comprehensible to the user.
6. Browser and API results agree on the same operation.
7. Data persistence is correct (DB row matches user-visible state).
8. An audit record exists for the operation.
9. Cross-tenant negative test passes (Tenant B cannot read Tenant A).
10. No secret or synthetic PHI leak is detectable.
11. Screenshot, trace, HAR, and JUnit evidence all exist.

Failure of any condition downgrades the verdict to
`API_WORKFLOW_VERIFIED`, `PARTIAL`, or `BLOCKED_*` per the failure mode.

## §6. Forbidden shortcuts (binding)

- headless crawler as primary evidence
- curl loop scripts that batch-run without per-command inspection
- DB writes that fake user-operation results
- static source-code inspection as a substitute for headed-browser evidence
- "Marketing copy says feature X exists, therefore feature X works"
- lowering test timeouts to mask hanging fixtures
- skipping an entire test module to mask an environment issue
- mapping an unknown external Expert to a different region to "indirectly
  deny" it (unknown → DENY is the only allowed path)

## §7. Evidence archive layout

```
reports/phase-a1b/evidence/
  corti_observation/
    overview/
    architecture/
    experts/
    available_experts/
    <expert_slug>/
    agent_api_reference/
  journey_1_registry_browse/
  journey_2_research_agent_create/
  journey_3_research_agent_run/
  journey_4_calculator/
  journey_5_interviewing/
  journey_6_external_expert_disabled/
  journey_7_clone_preset/
  journey_8_context_delete/
  journey_9_cross_tenant/
  journey_10_logout_cleanup/
  api_only/                 # capabilities without UI
  sanitized_har/
  sha256_manifest.json      # root manifest
```

The root `sha256_manifest.json` aggregates every artefact's SHA-256 and
is the canonical evidence fingerprint for end-of-phase audit.

## §8. Per-capability evidence verdict matrix

| Capability (planned) | UI exists? | Required verdict | Notes |
|---|---|---|---|
| Expert Registry list + filter | yes (Journey 1) | `HUMAN_WORKFLOW_VERIFIED` | incl. DrugBank LICENSE_REQUIRED badge |
| Agent CRUD | yes (Journey 2) | `HUMAN_WORKFLOW_VERIFIED` | |
| Agent Card | yes (Journey 2) | `HUMAN_WORKFLOW_VERIFIED` | consistency across Hub / A2A / admin / runtime |
| Message → Task → Context | yes (Journey 3) | `HUMAN_WORKFLOW_VERIFIED` | |
| Memory Expert retrieval | yes (Journey 3 round 2) | `HUMAN_WORKFLOW_VERIFIED` | |
| Calculator Expert | yes (Journey 4) | `HUMAN_WORKFLOW_VERIFIED` | deterministic; no LLM |
| PubMed Expert | yes (Journey 3) | `HUMAN_WORKFLOW_VERIFIED` | synthetic query; citation trace |
| Clinical Trials Expert | yes (Journey 3) | `HUMAN_WORKFLOW_VERIFIED` | synthetic query |
| Interviewing Expert | yes (Journey 5) | `HUMAN_WORKFLOW_VERIFIED` | schema-driven |
| Coding wrapper Expert | yes (existing Coding page) | `HUMAN_WORKFLOW_VERIFIED` | |
| DrugBank Expert (LICENSE_REQUIRED) | yes (Journey 6) | `HUMAN_WORKFLOW_VERIFIED` | negative path |
| POSOS Expert (LICENSE_REQUIRED) | no UI | `API_WORKFLOW_VERIFIED` | negative path |
| Web Search Expert | no UI | `API_WORKFLOW_VERIFIED` | default DISABLED_BY_POLICY |
| MCP Server CRUD | no UI | `API_WORKFLOW_VERIFIED` | |
| Context Delete scrub | yes (Journey 8) | `HUMAN_WORKFLOW_VERIFIED` | |
| Cross-tenant isolation | yes (Journey 9) | `HUMAN_WORKFLOW_VERIFIED` | negative path |
| Logout browser-storage cleanup | yes (Journey 10) | `HUMAN_WORKFLOW_VERIFIED` | |
| Orchestrator Expert-selection trace | via trace viewer | `HUMAN_WORKFLOW_VERIFIED` | non-PHI audit |

A capability with no UI is `API_WORKFLOW_VERIFIED`. It may NEVER be
upgraded to `HUMAN_WORKFLOW_VERIFIED` without a UI journey.

---

End of protocol.
