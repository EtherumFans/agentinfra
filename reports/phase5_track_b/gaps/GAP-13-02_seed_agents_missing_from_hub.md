# GAP-13-02 Fix — seed.py 10 agents missing from Hub

**Date:** 2026-07-11
**Class:** AUDIT_BLOCKER_FIX (per plan §"已锁定决策 3")
**Severity:** P0
**Status:** CLOSED

## The gap

iCoDer hub (`GET /api/icoder/agents/hub`) showed 14 agents. `seed.py:847` declares 16 PREBUILT_AGENTS. 10 of those declared agents had NO `agent_pack.json` file under `backend/official_agents/`, so they were invisible in the hub.

The hub reads from `official_agents/**/agent_pack.json` (`backend/app/api/icoder_agents_hub.py:62` `_load_packs`), not from seed.py DB rows. seed.py creates DB rows for backend Agent model — a different inventory entirely.

**10 missing agents (all seed.py declared, all Corti-equivalent):**

| seed.py key | Corti equivalent | Pack status before fix |
|-------------|------------------|------------------------|
| icd10-navigator | icd-10-index-navigator-agent | NO pack (pack `index_navigator` is a DIFFERENT MedCodER Stage 2 agent, hidden) |
| rule-explainer | rule-explainer-agent | NO pack |
| surgical-registry | surgical-registry-intelligence-agent | NO pack |
| icu-summary | icu-admission-summary-agent | NO pack |
| triage | triage-and-initial-assessment-agent | NO pack |
| med-reconciliation | medication-reconciliation-agent | NO pack |
| discharge-edu | patient-discharge-education-agent | NO pack |
| nursing-handoff | nursing-shift-handoff-agent | NO pack |
| prior-auth | prior-authorization-agent | NO pack |
| referral-gen | referral-generator-agent | NO pack |

## The fix

Created 10 metadata-only `agent_pack.json` files under `backend/official_agents/`:

```
backend/official_agents/
├── icd10_navigator/agent_pack.json      (new)
├── rule_explainer/agent_pack.json       (new)
├── surgical_registry/agent_pack.json    (new)
├── icu_summary/agent_pack.json          (new)
├── triage/agent_pack.json               (new)
├── med_reconciliation/agent_pack.json   (new)
├── discharge_edu/agent_pack.json        (new)
├── nursing_handoff/agent_pack.json      (new)
├── prior_auth/agent_pack.json           (new)
└── referral_gen/agent_pack.json         (new)
```

Each pack:
- `format_version: "1.2"` (matches existing packs)
- `agent_type: "certified"` (visible in hub)
- `manifest.maturity: "metadata-only"` (Coming Soon badge, runnable=false)
- `manifest.hidden_from_hub: false`
- `manifest.category_display` matches Corti's official 4 categories
- `manifest.use_case` matches Corti's 4 use cases
- `metadata.corti_match` field records the Corti equivalent ID
- `metadata.audit_note` records this was a Phase 5 Track B GAP-13-02 fix
- `experts: []`, `tools: []` (no executable wiring)

## Verification

Backend restarted (file loader reads from disk each request, no restart strictly needed). Hub count:

```
Before: 14 agents (9 runnable + 5 metadata-only)
After:  24 agents (9 runnable + 15 metadata-only)
```

Corti category coverage post-fix:

| Corti category | iCoDer runnable | iCoDer metadata-only | Total |
|----------------|-----------------|----------------------|-------|
| Coding and Revenue Cycle | 7 | 4 | 11 |
| Point of Care Tools | 0 | 3 (NEW) | 3 |
| Clinical Evidence and Research | 0 | 1 (NEW) | 1 |
| Care Coordination | 0 | 3 (NEW) | 3 |
| (uncategorized) | 0 | 5 (existing metadata) | 5 |
| **iCoDer-only** | 2 | 0 | 2 |
| **Total** | **9** | **15** | **24** |

Note: 5 metadata-only agents (denial-appeals / evidence-ranker / diagnosis-extractor / cdi-review / documentation-gap) have no `category_display` because they predate the Corti mapping convention. P2 cleanup candidate.

## What's NOT in this fix (deferred)

- Wiring (experts + tools) for the 10 new packs — deferred to Phase 5 Track B-2 if user wants to promote any to runnable
- `category_display` backfill for 5 prior metadata-only packs — P2 cleanup
- Frontend rendering check — pack loader already supports these via existing schema; no frontend changes needed

## Files added

- `backend/official_agents/icd10_navigator/agent_pack.json`
- `backend/official_agents/rule_explainer/agent_pack.json`
- `backend/official_agents/surgical_registry/agent_pack.json`
- `backend/official_agents/icu_summary/agent_pack.json`
- `backend/official_agents/triage/agent_pack.json`
- `backend/official_agents/med_reconciliation/agent_pack.json`
- `backend/official_agents/discharge_edu/agent_pack.json`
- `backend/official_agents/nursing_handoff/agent_pack.json`
- `backend/official_agents/prior_auth/agent_pack.json`
- `backend/official_agents/referral_gen/agent_pack.json`

## Audit freeze note

Per plan §"已锁定决策 3" (AUDIT_BLOCKER_FIX policy), this fix is allowed during audit freeze because:
- It unblocks B-1.4 Corti↔iCoDer agent inventory comparison
- It does NOT modify any existing agent's behavior
- It does NOT modify runtime code
- It only adds new metadata-only entries (no executable wiring)
- Reverting is trivial (delete 10 files)

No regression risk — the 10 new packs are all `runnable=false` and inherit the standard metadata-only badge workflow.
