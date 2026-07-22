# Charter Amendment 1 — Reverse-Engineering Tier Added

**Amendment ID**: `A1B-AE.0-AMENDMENT-1`
**Issued**: 2026-07-22 (mid-phase, after A1B-AE.2 commit `b23c69a`)
**Charter version**: v1.0 → **v1.1**
**Authorised by**: phase owner (user, SONG Luhua)
**Amendment type**: **additive** (no existing clause is weakened; new tier is added; previously filed evidence retains its provenance)
**Effective scope**: all remaining A1B-AE commits (A1B-AE.3..A1B-AE.11) and any re-observation of Corti.

---

## §A1.1 Why this Amendment exists

Charter v1.0 §7 established a single-tier `clean_room_authored: true` regime
under which only **publicly visible Corti documentation** could be used as
design source. This was sufficient to capture the Corti public Agentic
contracts (Agent, Expert, MCP, Task, Context, Memory, Agent Card) in
A1B-AE.1.

The phase owner has determined that, for the remaining commits (A1B-AE.3
Expert Registry through A1B-AE.11 final reconciliation), the phase needs
**deeper behavioural ground truth** than the public docs provide —
specifically:

- How the Corti Console (console.corti.app) actually presents Expert
  configuration to a developer user.
- What runtime request/response shapes Corti emits when an Expert is
  called through its Console (e.g. the `message:send` request body as
  filled by the Console's "Try it" UI).
- What MCP authentication flow variants actually look like end-to-end
  (none / inherit / bearer / oauth2.0) when an Expert is wired up.

Public docs describe these contracts at the **schema** level. Public docs
do NOT show the **behavioural** level (concrete filled examples, error
states, UI gating, region routing). For the iCoDer side to reach
functionally useful (not parity-claiming) replication, behavioural
observation is needed.

Charter v1.0 §7 forbade this. This Amendment adds it as a **second,
separate, equally-audited tier**. The original `CLEAN_ROOM_PUBLIC` tier
remains in force unchanged.

## §A1.2 New §7 (replaces v1.0 §7 in force; v1.0 §7 retained as §7.1 for history)

### §7 Observation scope and provenance tiers (v1.1)

Every prompt, schema, contract, design artefact, test fixture, or code
module produced under this Charter MUST declare one of two provenance
tiers in its file header or sidecar metadata:

#### §7.1 `CLEAN_ROOM_PUBLIC` tier (unchanged from v1.0)

**Permitted design sources**:
- publicly visible text on `docs.corti.ai` pages (no login);
- publicly visible request/response example bodies in the public API reference;
- the public A2A protocol specification at `https://a2a-protocol.org`;
- the public MCP specification;
- iCoDer original design.

**Forbidden**:
- Corti-internal source code, prompts, UI assets, trademarks;
- any `console.corti.app` content behind a login;
- customer traffic captures;
- binary reverse engineering of Corti artifacts.

**Declaration block** (unchanged from v1.0 §7):

```yaml
provenance: CLEAN_ROOM_PUBLIC
clean_room_authored: true
author: <name>
date: <YYYY-MM-DD>
design_source:
  - "Corti public docs (URL)"
  - "A2A public spec (v0.3)"
  - "MCP public spec"
  - "iCoDer original design"
contains_corti_private_material: false
```

#### §7.2 `REVERSE_ENGINEERED` tier (NEW in v1.1)

**Permitted design sources** (all four; any subset):
- observation of `console.corti.app` pages **under an authorised
  developer account** via headed browser (Playwright MCP, Chrome on CDP
  port 9222);
- observation of `console.corti.app` runtime network traffic as seen by
  the browser (DevTools / HAR export; **only the user's own synthetic
  test data**, never another customer's data);
- behavioural reverse engineering — filling forms, clicking buttons,
  capturing the resulting HTTP requests and responses;
- black-box inference of state machines, enums, and error envelopes
  from observed runtime behaviour.

**Forbidden even under this tier**:
- copying Corti source code (server-side or client-side bundle **source**);
- extracting Corti-private LLM prompts by any means (jailbreak, prompt
  extraction, side-channel);
- re-publishing Corti trademarks, logos, marketing copy;
- capturing or persisting another Corti customer's data;
- credential sharing, session hijacking, or bypassing Corti's
  authentication or rate-limiting controls;
- any action that would violate Corti's Terms of Service as published.

**Declaration block** (mandatory):

```yaml
provenance: REVERSE_ENGINEERED
author: <name>
date: <YYYY-MM-DD>
observation_session_id: <YYYY-MM-DD-HHMM-UTC-tabN-stepN>
observation_url: <console.corti.app URL observed>
observation_account_type: <developer | trial | paid>  # as applicable
design_source:
  - "Corti Console behaviour (URL observed <date>)"
  - "Corti Console network trace (HAR sanitized; <date>)"
  - "iCoDer original adaptation"
contains_corti_private_material: false
contains_corti_source_code: false
contains_corti_trademark: false
data_classification:
  - synthetic_only
  - developer_account_owned
reverse_engineering_method:
  - black_box_observation
  - network_trace_analysis
  - form_fill_and_capture
```

#### §7.3 Mixed-tier artefacts

If a single artefact draws on BOTH tiers (e.g. a schema whose shape
comes from public docs but whose filled example comes from Console
observation), the artefact MUST declare:

```yaml
provenance: MIXED
provenance_breakdown:
  schema_shape: CLEAN_ROOM_PUBLIC
  filled_example: REVERSE_ENGINEERED
clean_room_authored: true  # schema-level; see provenance_breakdown
```

#### §7.4 Audit enforcement

Every commit filed under v1.1 MUST include in its commit body:

```
provenance_summary:
  CLEAN_ROOM_PUBLIC_artefacts: <count>
  REVERSE_ENGINEERED_artefacts: <count>
  MIXED_artefacts: <count>
  forbidden_behaviour_invoked: none | <list>
  contains_corti_private_material: false
  contains_corti_source_code: false
  contains_corti_trademark: false
```

The final A1B-AE.11 reconciliation report MUST include the cumulative
provenance summary across A1B-AE.0..A1B-AE.11.

#### §7.5 Previously filed evidence

All evidence filed before this Amendment (A1B-AE.0 charter at `37e4848`,
A1B-AE.1 Corti public-contracts at `558cfce`, A1B-AE.2 taxonomy at
`b23c69a`) is **unchanged** and retains its `CLEAN_ROOM_PUBLIC`
classification. The Amendment does NOT retroactively re-classify.

The `clean_room_authored: true` flag on those commits remains valid
because they drew only on public docs (A1B-AE.1 §1.1 attestment).

Any commit that uses the new REVERSE_ENGINEERED tier MUST declare it
prominently in the commit message subject line, e.g.:

```
audit/phase-a1b: A1B-AE.3 — Expert Registry (REVERSE_ENGINEERED; Console observed)
```

## §A1.3 Forbidden verdicts (unchanged)

All 8 verdicts forbidden in Charter v1.0 §11 remain forbidden in v1.1:

- `PRODUCTION_READY`
- `FULLY_VERIFIED`
- `PHI_BOUNDED`
- `CORTI_PARITY_VERIFIED`
- `PASS_A1A_GATE4_FINAL`
- `READY_FOR_HOSPITAL_DEPLOYMENT`
- `CLINICAL_GRADE_VERIFIED`
- `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED`

The authorisation of reverse engineering does NOT lift these
prohibitions. Reverse engineering produces **functional** capability
replication, not **legal** parity. The distinction matters:

- Functional replication = "iCoDer can do X that Corti also does".
- Legal parity = "iCoDer is equivalent to Corti in a legally binding
  audit sense".

This Charter authorises the former; the latter would require a
separate, post-A1B phase with customer-billable compliance work
(SOC 2 / HIPAA / China 等保 / etc.).

## §A1.4 Permitted final verdict (unchanged)

The only permitted final verdict for A1B-AE remains:

```
PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED
```

The word `PARTIAL` covers both tiers: some capabilities are reconciled
clean-room (A1B-AE.1, .2, parts of .3-.8), some are reconciled via
reverse engineering (other parts of .3-.8). The reconciliation is
partial either way.

## §A1.5 Acceptance conditions update (additions only)

To Charter v1.0 §10 acceptance conditions, ADD:

- §10.13 Every artefact committed after this Amendment declares its
  provenance tier (`CLEAN_ROOM_PUBLIC`, `REVERSE_ENGINEERED`, or
  `MIXED`) in its header.
- §10.14 Every commit message body after this Amendment includes a
  `provenance_summary` block per §7.4.
- §10.15 No artefact committed after this Amendment contains Corti
  source code, Corti-private prompts (extracted via jailbreak or
  side-channel), Corti trademarks, or another Corti customer's data.
- §10.16 The A1B-AE.11 final report includes a cumulative provenance
  table and an audit-trail of every Console observation session
  (session ID → observation URL → artefacts produced).

## §A1.6 Carry-forward to in-flight A1B-AE.3

A1B-AE.3 (Expert Registry model + alembic + API) is currently in
progress with 1 preliminary Corti Console evidence file already
captured (the `/agentic/experts` deep re-capture at
`reports/phase-a1b/evidence/a1b_ae_3_corti_observation/08_agentic_experts_deep/observation.json`).
That evidence is classified `CLEAN_ROOM_PUBLIC` (it was captured from
the public docs page, not from Console).

Under v1.1, A1B-AE.3 MAY additionally observe:
- `console.corti.app/project/.../agents` (Expert registry list view);
- `console.corti.app/project/.../agents/create` (Expert creation form);
- the `/message:send` request the Console emits when an Expert is
  called.

These observations MUST be filed under
`reports/phase-a1b/evidence/a1b_ae_3_corti_console_observation/` with
sidecar provenance metadata per §7.2.

## §A1.7 Effective immediately

This Amendment takes effect on commit. The next commit (A1B-AE.3)
MUST cite this Amendment in its commit message body and apply v1.1
provenance declarations to all new artefacts.

---

End of Charter Amendment 1.
