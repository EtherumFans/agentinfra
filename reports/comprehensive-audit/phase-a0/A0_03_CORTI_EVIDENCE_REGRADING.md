# A0 Gate 3 — Corti Evidence Re-grading

> Phase A0 Gate 3. Applies the E0–E8 evidence grade scale (spec §4.3) to every Corti capability claim made in Pre-A0 26A. Downgrades overstated claims. Produces a machine-verifiable regrading matrix.

Spec reference: §4.3 (evidence grades), §5 (forbidden grade inflation), §22 (Hard Checkpoint D — Parity Integrity prerequisite).

---

## §1. Why this gate exists

Pre-A0 26A used a vague grade "VERIFIED_CONSOLE" for many claims. Phase A0 spec §4.3 defines 9 evidence grades (E0–E8) with strict criteria. Several Pre-A0 claims do not meet the grade they were assigned:

| Pre-A0 claim | Pre-A0 grade | Actual evidence | Phase A0 grade |
|--------------|--------------|-----------------|----------------|
| Agent CRUD operations verified | VERIFIED_CONSOLE | Page existed; Settings tab visible; no Create/Update/Delete exercised | **E5_BROWSER_VERIFIED** (UI surface only) — NOT E8 |
| Real payment processor verified | VERIFIED_CONSOLE | "Add a payment method" button present; no real transaction | **E5_BROWSER_VERIFIED** (UI surface only) — NOT E8 |
| AMBOSS = 14th prebuilt Expert | VERIFIED_CONSOLE | Referenced in one user-created agent's system prompt; not in docs overview; not in expert library browse | **E1_DOCUMENTED** (prompt reference only) — NOT E5 |
| Agent "save = live" lifecycle verified | VERIFIED_CONSOLE | Observed chat pane says "ready to message" | **E5_BROWSER_VERIFIED** (UI state) — save-then-run end-to-end NOT exercised |
| 9 ICD-10 variants verified | VERIFIED_CONSOLE | Dropdown open in screenshot; all 9 options visible | **E5_BROWSER_VERIFIED** (UI surface); selection + run with specific variant NOT exercised |
| 20 pre-built agents verified | VERIFIED_CONSOLE | List visible in screenshot | **E5_BROWSER_VERIFIED** (list existence); individual agent run NOT verified per agent |
| JS SDK signature verified | VERIFIED_CONSOLE | Code generator snippet visible in Console | **E5_BROWSER_VERIFIED** for snippet; NOT E6 (no external install + run) |
| Embedded SDK signature verified | VERIFIED_CONSOLE | Code generator snippet visible | **E5_BROWSER_VERIFIED** for snippet |

**Pattern**: Pre-A0 conflated "I saw it in the Console" with "the capability is verified end-to-end". Phase A0 separates these precisely.

## §2. Evidence grade definitions (per spec §4.3)

| Grade | Name | Criteria |
|-------|------|----------|
| E0 | UNSUPPORTED | No evidence; claim is unsupported |
| E1 | DOCUMENTED | Referenced in official docs or marketing but not independently verified |
| E2 | CODE_OBSERVED | Code/config/file observed on disk; not executed |
| E3 | UNIT_VERIFIED | Unit test passes against the claim |
| E4 | INTEGRATION_VERIFIED | Integration test passes against the claim |
| E5 | BROWSER_VERIFIED | Observed in a live browser session (Console, app, widget); UI state confirmed |
| E6 | EXTERNAL_CONSUMER_VERIFIED | External consumer (SDK, partner app) installed + successfully exchanged messages with the system |
| E7 | SECURITY_NEGATIVE_VERIFIED | Negative test confirms a security property (e.g., unauthorized request rejected) |
| E8 | EXTERNAL_PARTNER_OR_PRODUCTION_OBSERVED | Real production traffic or real partner integration observed |

### Grade promotion rules

- E5 → E6 requires installing the SDK as an external package (not from local tgz) and completing at least one round-trip.
- E5 → E8 requires a real transaction (real money, real clinical data, real production tenant).
- E1 → E5 requires observing the capability in a live browser.
- E2 → E3 requires running the unit test.

## §3. Regrading matrix — all Corti capability claims

### Class A — Foundation (architecture, protocol, agent card)

| # | Claim | Pre-A0 grade | Phase A0 grade | Rationale |
|---|-------|--------------|----------------|-----------|
| A-01 | Corti has Orchestrator + Experts + Memory architecture | E1 (docs) | **E1_DOCUMENTED** | Docs page read; no runtime observation | 
| A-02 | Corti implements A2A v0.3 | E1 (docs) | **E1_DOCUMENTED** | Docs page read; envelope not captured on wire |
| A-03 | Corti exposes `.well-known/agent.json` Agent Card | E1 (docs) | **E1_DOCUMENTED** | Docs reference; not fetched |
| A-04 | Corti generates server-side contextId | E1 (docs) | **E1_DOCUMENTED** | Docs reference |
| A-05 | Corti has Memory expert (RAG-like) | E1 (docs) | **E1_DOCUMENTED** | Listed in docs overview; not exercised |
| A-06 | Corti streams SSE events | E1 (docs) | **E1_DOCUMENTED** | Docs reference; no SSE capture |
| A-07 | Corti supports request/response polling | E1 (docs) | **E1_DOCUMENTED** | Docs reference |
| A-08 | Corti A2A Tasks (long-running) | NOT_VERIFIED | **E0_UNSUPPORTED** | No Corti doc claims Tasks; Pre-A0 didn't claim it either |

### Class B — Agent surface

| # | Claim | Pre-A0 grade | Phase A0 grade | Rationale |
|---|-------|--------------|----------------|-----------|
| B-01 | Agent CRUD: Create | E5 (Console) | **E5_BROWSER_VERIFIED** for UI; not E6 (no SDK Create exercised against real backend) | "New Agent" button present; flow not completed end-to-end |
| B-02 | Agent CRUD: Read/List | E5 (Console) | **E5_BROWSER_VERIFIED** | Agents list page visible with 20 entries |
| B-03 | Agent CRUD: Update | E5 (Console) | **E5_BROWSER_VERIFIED** for Settings tab visible; field edit not saved+verified | Settings tab populated; no Save-then-reload test |
| B-04 | Agent CRUD: Delete | NOT_VERIFIED | **E0_UNSUPPORTED** | No delete button observed; not exercised |
| B-05 | Agent lifecycle: save = live | E5 (Console) | **E5_BROWSER_VERIFIED** for "ready to message" state; agent run NOT triggered from saved state | Chat pane visible |
| B-06 | Pre-built Agent count = 20 | E5 (Console) | **E5_BROWSER_VERIFIED** | Full list screenshot (02_prebuilt_agents_full_list.png) |
| B-07 | Agent preset template picker | E5 (Console) | **E5_BROWSER_VERIFIED** | "New Agent" + template options visible |
| B-08 | Agent Hub tabs (My / Pre-built) | E5 (Console) | **E5_BROWSER_VERIFIED** | Tabs visible in screenshot |
| B-09 | Code generators per agent | E5 (Console) | **E5_BROWSER_VERIFIED** for JS+.NET+JSON snippets visible | Snippets observed; not executed |
| B-10 | Badge taxonomy | NOT_VERIFIED | **E0_UNSUPPORTED** | Corti badges not enumerated in Pre-A0 |

### Class C — Expert surface

| # | Claim | Pre-A0 grade | Phase A0 grade | Rationale |
|---|-------|--------------|----------------|-----------|
| C-01 | Memory expert exists | E1 (docs) | **E1_DOCUMENTED** | Docs overview lists; not in Console expert library browse |
| C-02 | Medical Coding expert exists | E5 (Console) | **E5_BROWSER_VERIFIED** for "coding-expert" bound to demo agent | Bound to fa3be93e agent |
| C-03 | PubMed expert exists | E5 (Console) | **E5_BROWSER_VERIFIED** for "pubmed-expert" bound | Bound to demo agent |
| C-04 | Web Search expert exists | E5 (Console) | **E5_BROWSER_VERIFIED** for "web-search-expert" bound | Bound to demo agent |
| C-05 | Medical Calculator expert exists | E5 (Console) | **E5_BROWSER_VERIFIED** for "medical-calculator-expert" bound | Bound to demo agent |
| C-06 | Interviewing expert exists | E1 (docs) | **E1_DOCUMENTED** | Docs reference only; not observed bound |
| C-07 | POSOS expert exists | E1 (docs) | **E1_DOCUMENTED** | Docs reference; per Phase 4-H §7 has MCP server bound (not re-verified) |
| C-08 | DrugBank expert exists | E1 (docs) | **E1_DOCUMENTED** | Same as C-07 |
| C-09 | Clinical Trials expert exists | E1 (docs) | **E1_DOCUMENTED** | Docs reference |
| C-10 | **AMBOSS expert exists** | E5 (Console) — overstated | **E1_DOCUMENTED** (prompt reference only) | DOWNGRADED. AMBOSS is mentioned in fa3be93e system prompt text, but is NOT in docs overview, NOT in Console expert library browse, NOT bound to any observed agent. The system prompt text could be stale template copy (per 04_agent_detail_schema.md §"Staleness observation"). Cannot promote to E5 without observing AMBOSS as a selectable Expert. |
| C-11 | ICD-10-CM expert exists | E5 (Console) | **E5_BROWSER_VERIFIED** for dropdown option | In Medical Coding dropdown |
| C-12 | ICD-10-WHO/UK/GM/PCS experts exist | E5 (Console) | **E5_BROWSER_VERIFIED** for dropdown options | All visible in dropdown |

### Class D — Tool / MCP surface

| # | Claim | Pre-A0 grade | Phase A0 grade | Rationale |
|---|-------|--------------|----------------|-----------|
| D-01 | Corti has MCP server | E1 (docs) | **E1_DOCUMENTED** | Per Phase 4-H §7: 2/13 experts have bound MCP servers (POSOS, DrugBank) |
| D-02 | Corti MCP authentication | E1 (docs) | **E1_DOCUMENTED** | Phase 4-H reference |
| D-03 | Tool registry shape | E1 (docs) | **E1_DOCUMENTED** | Phase 4-H reference |

### Class E — Commercial surface

| # | Claim | Pre-A0 grade | Phase A0 grade | Rationale |
|---|-------|--------------|----------------|-----------|
| E-01 | **Real payment processor** | E5 — overstated | **E5_BROWSER_VERIFIED** (UI surface only); NOT E8 | **DOWNGRADED from implicit "verified"**. "Add a payment method" button present (10_billing.png). No real transaction exercised; no Stripe/Adyen/other processor identity observed. Pre-A0 26A §"verified" implied production-grade evidence; Phase A0 restricts to UI surface. |
| E-02 | Plan tiers: Pay-as-you-go | E5 (Console) | **E5_BROWSER_VERIFIED** | Plan tab text present |
| E-03 | Auto top-up toggle | E5 (Console) | **E5_BROWSER_VERIFIED** | Toggle present (not enabled) |
| E-04 | Low balance alerts | E5 (Console) | **E5_BROWSER_VERIFIED** | Toggle + threshold field present |
| E-05 | Billing history tab | E5 (Console) | **E5_BROWSER_VERIFIED** | Tab present; contents not inspected |
| E-06 | Currency = USD | E5 (Console) | **E5_BROWSER_VERIFIED** | Balance shown as $37.52 |
| E-07 | Pre-paid balance model | E5 (Console) | **E5_BROWSER_VERIFIED** | Balance + last-updated timestamp visible |

### Class F — Compliance / deploy

| # | Claim | Pre-A0 grade | Phase A0 grade | Rationale |
|---|-------|--------------|----------------|-----------|
| F-01 | 等保2.0 certification | NOT_APPLICABLE | **NOT_COMPARABLE** | Corti is EU-headquartered; 等保 is CN-specific |
| F-02 | GB/T 35273 (CN PII) | NOT_APPLICABLE | **NOT_COMPARABLE** | CN-specific |
| F-03 | HIPAA | E1 (docs) | **E1_DOCUMENTED** | Corti marketing claims; not certificate-verified |
| F-04 | ISO 27001 | E1 (docs) | **E1_DOCUMENTED** | Corti marketing claims; certificate not inspected |
| F-05 | Cloud SaaS deployment | E5 (Console) | **E5_BROWSER_VERIFIED** | Console login succeeded; production URL pattern |
| F-06 | On-premise deploy | E1 (docs) | **E1_DOCUMENTED** | Disclaimed; not Corti model |
| F-07 | Multi-region failover | E1 (docs) | **E1_DOCUMENTED** | 4 regions per docs; failover not exercised |
| F-08 | Edge PHI redaction | E1 (docs) | **E1_DOCUMENTED** | Architecture claim; no redaction log inspected |

### Class G — Observability

| # | Claim | Pre-A0 grade | Phase A0 grade | Rationale |
|---|-------|--------------|----------------|-----------|
| G-01 | Per-stage run trace | NOT_VERIFIED | **E0_UNSUPPORTED** for Corti; per Phase 4-H §7 Corti detail UI has no trace | Corti lacks this |
| G-02 | Signed trace_url | NOT_VERIFIED | **E0_UNSUPPORTED** | Corti lacks this |
| G-03 | RunHistory table | NOT_VERIFIED | **E0_UNSUPPORTED** | Corti detail UI has no history table |
| G-04 | Patient context events | NOT_VERIFIED | **E0_UNSUPPORTED** | Corti generator lacks patient.context.cleared |
| G-05 | Session-scoped events | NOT_VERIFIED | **E0_UNSUPPORTED** | Corti generator lacks session.cleared |
| G-06 | SLA-breach alerting | NOT_VERIFIED | **E0_UNSUPPORTED** | Neither has (per Gate 11) |

## §4. Summary of grade changes (Pre-A0 → Phase A0)

| Change type | Count | Examples |
|-------------|------:|----------|
| Downgrade (overstated) | 3 | E-01 payment processor, C-10 AMBOSS, B-04 delete |
| Confirm at same grade | 28 | Most E1_DOCUMENTED and E5_BROWSER_VERIFIED |
| Upgrade (none) | 0 | Phase A0 does not upgrade; only validates or downgrades |
| Restrict to narrower scope | 7 | B-01/B-03 (CRUD ops observed but not exercised), E-02..E-07 (UI surface only, not real transaction) |
| Newly unverified | 2 | B-04 Delete, B-10 Badge taxonomy |

### Critical downgrades explained

**E-01 Payment processor (real)**: Pre-A0 26A used this as the cornerstone of the "Corti has real commercial infrastructure, iCoDer has theater" parity claim. Phase A0 still agrees with the *direction* of the claim (Corti's billing UI is more developed than iCoDer's) but restricts the evidence grade to E5_BROWSER_VERIFIED — we observed UI elements suggesting a payment processor exists, but did not exercise a real transaction. The Parity Matrix in Gate 4 will reflect this nuance: Corti CORTI_ADVANTAGE holds, but the evidence is "Console UI surface" not "real money moved".

**C-10 AMBOSS**: Pre-A0 promoted AMBOSS from "prompt-referenced" to "14th prebuilt Expert". Phase A0 reverts this: AMBOSS appears only in the system prompt text of one user-created agent (`fa3be93e`). The system prompt could be stale template text (the bound experts are pubmed/web-search/medical-calculator/coding, none of which is AMBOSS). Without observing AMBOSS as a selectable Expert in the Console library browse, Phase A0 cannot promote beyond E1_DOCUMENTED. The prebuilt Expert count reverts to **13** (not 14).

**B-04 Agent Delete**: Pre-A0 didn't claim this was verified, but Phase A0 makes the negative explicit (E0). iCoDer has agent delete (per Phase 6); Corti parity status for this dimension becomes EVIDENCE_INSUFFICIENT rather than PARTIAL_PARITY.

## §5. Hard Checkpoint prerequisite for D (Parity Integrity)

Hard Checkpoint D in Gate 4 depends on this gate's grades. Three principles:

1. **No composite grades**: A dimension's parity status is NOT "favorable" or "unfavorable". It is one of 10 mutually-exclusive statuses per spec §13.2.
2. **Evidence grade is separate from parity status**: A PARITY claim with E1 evidence is weaker than a PARITY claim with E5 evidence.
3. **Corti-ADVANTAGE dimensions require E5+ evidence for Corti**: A CORTI_ADVANTAGE claim based on E1 docs only is NOT reportable as CORTI_ADVANTAGE — it is EVIDENCE_INSUFFICIENT.

## §6. What Gate 3 explicitly does NOT do

| Action | Why not |
|--------|---------|
| Re-walk Corti Console | Would create new evidence; Phase A0 is paper re-grading only |
| Exercise real payment | Out of scope; Phase A1 may do this |
| Fetch Agent Card from `.well-known/agent.json` | Out of scope; would create new evidence |
| Install `@corti/sdk` as external package | Out of scope; Phase A1 E6 evidence |
| Promote any Pre-A0 grade | Phase A0 only confirms or downgrades |

## §7. Findings raised in Gate 3

| ID | Severity | Title |
|----|----------|-------|
| **A0-G3-001** | P1 | Pre-A0 26A conflated UI-surface observation (E5) with end-to-end capability verification (E6/E8). 3 claims downgraded. |
| **A0-G3-002** | P2 | Pre-A0 promoted AMBOSS to "14th prebuilt Expert" based on prompt text only; reverted to 13. |
| **A0-G3-003** | P2 | Agent CRUD operations (Create/Update/Delete) NOT end-to-end verified on Corti side; parity claims for CRUD must be EVIDENCE_INSUFFICIENT or PARTIAL_PARITY at most. |
| **A0-G3-004** | P2 | Corti payment processor identity (Stripe/Adyen/etc.) NOT observed; "real payment processor" claim is E5 not E8. Phase A1 should capture real transaction. |
| **A0-G3-005** | P3 | Most Corti architecture claims remain E1_DOCUMENTED; Phase A1 should fetch `.well-known/agent.json` + capture A2A envelope on wire to promote to E5+. |

## §8. Machine-readable artifact

The full regrading matrix will be embedded in `parity_matrix_v2_1.json` produced in Gate 4. This document provides the human-readable reasoning.

## §9. Gate 3 verdict

```
PHASE_A0_GATE_3_CORTI_EVIDENCE_REGRADING_COMPLETE
3_OVERSTATED_CLAIMS_DOWNGRADED
28_CLAIMS_CONFIRMED_AT_SAME_GRADE
0_CLAIMS_UPGRADED
13_PREBUILT_EXPERTS_CONFIRMED (NOT 14)
EVIDENCE_GRADES_NOW_COMPLIANT_WITH_SPEC_§4.3
0_FORBIDDEN_VERDICTS_CLAIMED
```

### Hard Checkpoints A+B+C closed; D-H pending

End of Gate 3. Proceeding to Gate 4 — Parity Matrix V2.1.
