# Phase 4-H §13 — Corti Fork / Version / Publish Audit

**Audit date:** 2026-07-10
**Auditor:** Phase 4-H audit (Corti Console + iCoDer code inspection)
**Source PDF:** `Phase 4-H Audit Report.pdf` §13 (3 sub-sections: §13.1 Fork / §13.2 Version / §13.3 Publish/Marketplace)
**Dev mode:** FROZEN per §2.1 — this is a READ-ONLY audit. No code changes.

---

## Executive Summary

Corti's agent lifecycle is **deliberately simple** — there is **NO traditional version control** and **NO public marketplace**. The model is:

1. **20 pre-built agents** ship as built-in templates (read-only)
2. **User clicks a pre-built agent** → opens `/agents/new?preset=<slug>` form pre-filled with template config
3. **User customizes name/system prompt/experts** → clicks "Create agent" → saves as a new agent owned by the user
4. **No version field** (no Draft/Published/Version Number/Immutable/Latest)
5. **No upstream link** (no "forked from" badge, no upstream update notification, no diff/sync)
6. **No marketplace** (no public/private publish, no review, no install/uninstall, no dependency, no pricing, no license)

This is a **template-instantiation model**, not a true fork/version/publish model. Corti explicitly chose simplicity over git-like complexity.

**Verdict (§13):** PASS — iCoDer matches Corti's template-instantiation model + has 2 ADVANTAGES (Forked-from badge + "已复制到我的智能体" toast). iCoDer should NOT add versioning or marketplace unless Corti adds them first (avoiding feature creep beyond parity).

---

## §13.1 — Fork

### Corti fork surface (OBSERVED)

**Fork mechanism:** Click a pre-built agent card on `/ai-studio/agents` (Pre-built agents tab) → navigates to `/ai-studio/agents/new?preset=<preset_slug>` (e.g., `?preset=medical-coding-icd-10-cpt-agent`).

**Verification matrix:**

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | Built-in Agent fork mechanism | ✅ **YES** — click pre-built agent → `/agents/new?preset=<slug>` form pre-filled | URL `?preset=medical-coding-icd-10-cpt-agent` + "Customize agent" panel |
| 2 | Fork copies: Name | ⚠️ **PARTIAL** — pre-built agent name is shown as template; user must rename (Name field is empty in customize panel, not pre-filled with "Medical Coding Agent") | New agent page snapshot |
| 3 | Fork copies: System prompt | ✅ **YES** (INFERRED) — preset's system prompt is loaded server-side; not visible in form but applied at run time | New agent page (system prompt editor empty in UI, but preset is loaded via `?preset=` query param) |
| 4 | Fork copies: Experts | ✅ **YES** (INFERRED) — preset's expert bindings loaded server-side | Same |
| 5 | Fork copies: Tools | ✅ **YES** (INFERRED) — preset's MCP server bindings loaded server-side (for agents like Coding Agent that has coding-expert + 4 tools) | §8 audit |
| 6 | Fork copies: Context | ⚠️ **PARTIAL** — context is session-bound, not part of agent config; fork doesn't carry context (per §9 audit) | §9 audit |
| 7 | Fork copies: Version | ❌ **NOT OBSERVED** — no version field; preset has no version exposed | New agent page |
| 8 | Records source (forked-from) | ❌ **NOT OBSERVED** — no "forked from" badge on the user's forked agent | "My agents" tab — agents show name + date + author only, no source badge |
| 9 | Upstream update notification | ❌ **NOT OBSERVED** — no "upstream updated" indicator | Same |
| 10 | Diff comparison | ❌ **NOT OBSERVED** — no diff view | Same |
| 11 | Re-sync from upstream | ❌ **NOT OBSERVED** — no "sync" / "pull upstream" button | Same |

### Corti fork flow (OBSERVED + INFERRED)

```
┌──────────────────────────┐
│ Pre-built agents tab     │
│ (20 built-in templates)  │
└────────┬─────────────────┘
         │ click
         ▼
┌──────────────────────────┐
│ /agents/new?preset=X     │
│ Name: (empty)            │
│ System prompt: (hidden)  │
│ Experts: (hidden)        │
│ Customize agent panel:   │
│   "Ask the agent..."     │
│   [Create agent] button  │
└────────┬─────────────────┘
         │ click "Create agent"
         ▼
┌──────────────────────────┐
│ My agents tab            │
│ New agent shown:         │
│   <user-chosen name>     │
│   <today's date>         │
│   Luhua Song             │
│   (no "Forked from" badge)│
└──────────────────────────┘
```

### iCoDer fork surface (OBSERVED + code-confirmed)

**Fork mechanism:** Hub card "Chat / Use Agent" CTA → calls `POST /api/agents/{id}/clone` endpoint → navigates to `/ai-studio/agents/{forked_id}`.

**Verification matrix:**

| # | Item | iCoDer status | Evidence |
|---|---|---|---|
| 1 | Built-in Agent fork mechanism | ✅ **YES** — Hub "Chat / Use Agent" CTA → clone endpoint → AgentChatPage | `AgentChatPage.tsx:6` "Hub CTA 'Chat / Use Agent' calls clone endpoint (Loop 1)" |
| 2 | Fork copies: Name | ✅ **YES** — `agentHubApi.clone(agentId)` returns `project_agent_id` with copied name (typically prefixed or suffixed) | `AgentDetailPage.tsx:507` |
| 3 | Fork copies: System prompt | ✅ **YES** — `agent_pack.json` has `system_prompt` field, copied on clone | `agent_pack_schema.py` |
| 4 | Fork copies: Experts | ✅ **YES** — `experts[]` array copied on clone | Same |
| 5 | Fork copies: Tools | ✅ **YES** — `mcp_servers[]` / `tools[]` array copied on clone | Same |
| 6 | Fork copies: Context | ⚠️ **PARTIAL** — context is session-bound, not part of pack; not copied (matches Corti) | §9 audit |
| 7 | Fork copies: Version | ⚠️ **PARTIAL** — `version` field copied from source pack (e.g., "1.0.0"), but no version lifecycle (Draft/Published) | `agent_pack_schema.py` |
| 8 | Records source (forked-from) | ✅ **YES — iCoDer ADVANTAGE** — `config.source_agent_ref` preserved on clone; "Forked" badge rendered on AgentDetailPage | `AgentDetailPage.tsx:911-915` |
| 9 | Upstream update notification | ❌ **NOT OBSERVED** — no upstream update indicator | code grep |
| 10 | Diff comparison | ❌ **NOT OBSERVED** — no diff view | Same |
| 11 | Re-sync from upstream | ❌ **NOT OBSERVED** — no "sync" button | Same |

### iCoDer fork flow (OBSERVED)

```
┌──────────────────────────┐
│ Agent Hub (iCoDer built) │
│ (8 built-in packs)       │
└────────┬─────────────────┘
         │ click "Chat / Use Agent"
         ▼
POST /api/agents/{id}/clone
         │
         ▼
┌──────────────────────────┐
│ /ai-studio/agents/{new_id}│
│ Name: <copied>           │
│ System prompt: <copied>  │
│ Experts: <copied>        │
│ [Forked] badge ← config.source_agent_ref │
│ Toast: "已复制到我的智能体"│
└──────────────────────────┘
```

### §13.1 verdict

| # | Dimension | Corti | iCoDer | Parity |
|---|---|---|---|---|
| 1 | Fork mechanism | ✅ `?preset=` query | ✅ `clone` endpoint | **MATCH** (different impl, same UX) |
| 2 | Copies Name | ⚠️ PARTIAL (empty) | ✅ copied | **iCoDer ADVANTAGE** |
| 3 | Copies System prompt | ✅ (INFERRED) | ✅ | **MATCH** |
| 4 | Copies Experts | ✅ (INFERRED) | ✅ | **MATCH** |
| 5 | Copies Tools | ✅ (INFERRED) | ✅ | **MATCH** |
| 6 | Copies Context | ⚠️ PARTIAL | ⚠️ PARTIAL | **MATCH** (both lack, by design) |
| 7 | Copies Version | ❌ | ⚠️ PARTIAL (string only, no lifecycle) | **iCoDer ADVANTAGE** (partial) |
| 8 | Records source (Forked-from badge) | ❌ | ✅ | **iCoDer ADVANTAGE** |
| 9 | Upstream update notification | ❌ | ❌ | **MATCH** (both lack) |
| 10 | Diff comparison | ❌ | ❌ | **MATCH** (both lack) |
| 11 | Re-sync from upstream | ❌ | ❌ | **MATCH** (both lack) |

**Overall §13.1:** iCoDer matches Corti on fork mechanism + has 2 ADVANTAGES (Forked-from badge + Name auto-copied). Both lack upstream sync (this is a Corti design choice — match).

---

## §13.2 — Version

### Corti version surface (OBSERVED)

**Finding:** Corti does **NOT have version control** for agents.

**Verification matrix:**

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | Draft state | ❌ **NOT OBSERVED** — no "Draft" badge on agent cards or detail page | "My agents" tab + agent detail page snapshots |
| 2 | Published state | ❌ **NOT OBSERVED** — no "Published" badge | Same |
| 3 | Version Number | ❌ **NOT OBSERVED** — no v1.0, v1.1, etc. on agent cards | Same |
| 4 | Immutable Version | ❌ **NOT OBSERVED** — no version-pinning concept | Same |
| 5 | Latest Alias | ❌ **NOT OBSERVED** — no "latest" pointer | Same |
| 6 | Breaking Change | ❌ **NOT OBSERVED** — no breaking-change marker | Same |
| 7 | Schema Change | ❌ **NOT OBSERVED** — no schema migration indicator | Same |
| 8 | Rollback | ❌ **NOT OBSERVED** — no rollback button | Same |
| 9 | Deprecated | ❌ **NOT OBSERVED** — no deprecation marker | Same |
| 10 | Migration | ❌ **NOT OBSERVED** — no migration tool | Same |
| 11 | API call version pinning | ⚠️ **PARTIAL** — the API Client dropdown (topbar) selects API Client, not Agent version. Runtime API uses whatever agent is currently saved (no version pinning in API call). | §11 audit + topbar observation |

### Corti version model (OBSERVED + INFERRED)

```
[User saves agent] → [Single "current" state persisted]
                    ↓
                    [No version history]
                    ↓
                    [API calls always use current state]
```

This is the simplest possible model: **last-saved-wins, no history, no rollback**.

### iCoDer version surface (OBSERVED + code-confirmed)

| # | Item | iCoDer status | Evidence |
|---|---|---|---|
| 1 | Draft state | ❌ **NOT OBSERVED** — no "Draft" badge; clones go directly to "My agents" without a draft state | `AgentDetailPage.tsx:510-515` — clone returns `project_agent_id`, navigates immediately (no draft step) |
| 2 | Published state | ❌ **NOT OBSERVED** — no "Published" badge | Same |
| 3 | Version Number | ⚠️ **PARTIAL** — `agent_pack.json` has `version` field (e.g., "1.0.0"), shown in pack metadata; but no per-save version increment | `agent_pack_schema.py` + `icoder_agents_hub.py` pack loading |
| 4 | Immutable Version | ❌ **NOT OBSERVED** — packs are mutable (user can edit + save) | Same |
| 5 | Latest Alias | ❌ **NOT OBSERVED** | Same |
| 6 | Breaking Change | ❌ **NOT OBSERVED** | Same |
| 7 | Schema Change | ❌ **NOT OBSERVED** | Same |
| 8 | Rollback | ❌ **NOT OBSERVED** | Same |
| 9 | Deprecated | ❌ **NOT OBSERVED** | Same |
| 10 | Migration | ❌ **NOT OBSERVED** | Same |
| 11 | API call version pinning | ⚠️ **PARTIAL** — `agent_ref` attribute on Web Component accepts `medical-coding-agent-1.0.0` format with version suffix; runtime resolves to current pack | `embedded.py:55-58` (preview page agent_ref options) |

### §13.2 verdict

| Dimension | Corti | iCoDer | Parity |
|---|---|---|---|
| Draft | ❌ | ❌ | MATCH (both lack) |
| Published | ❌ | ❌ | MATCH (both lack) |
| Version Number | ❌ | ⚠️ PARTIAL (string only) | **iCoDer ADVANTAGE** (partial) |
| Immutable Version | ❌ | ❌ | MATCH (both lack) |
| Latest Alias | ❌ | ❌ | MATCH (both lack) |
| Breaking Change | ❌ | ❌ | MATCH (both lack) |
| Schema Change | ❌ | ❌ | MATCH (both lack) |
| Rollback | ❌ | ❌ | MATCH (both lack) |
| Deprecated | ❌ | ❌ | MATCH (both lack) |
| Migration | ❌ | ❌ | MATCH (both lack) |
| API version pinning | ⚠️ PARTIAL | ⚠️ PARTIAL | **MATCH** (both partial — Corti via API Client, iCoDer via agent_ref) |

**Overall §13.2:** Both Corti and iCoDer lack traditional version control. iCoDer has a slight ADVANTAGE via the `version` string field in `agent_pack.json` (used for display, not for pinning). **Recommendation: DO NOT add full version control** — match Corti's simpler model.

---

## §13.3 — Publish / Marketplace

### Corti marketplace surface (OBSERVED)

**Finding:** Corti does **NOT have a public marketplace** for agents. The 20 pre-built agents are built-in (Corti-curated), and users cannot publish their own agents to a shared marketplace.

**Verification matrix:**

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | Who can publish | ❌ **NOT OBSERVED** — no "Publish" button on user's agents | "My agents" tab — no publish action |
| 2 | Publish scope | ❌ **NOT OBSERVED** | Same |
| 3 | Organization Private | ❌ **NOT OBSERVED** — no per-org sharing | Console |
| 4 | Public | ❌ **NOT OBSERVED** — no public marketplace | Console left nav (no "Marketplace" / "Store" / "Discover") |
| 5 | Review | ⚠️ **PARTIAL** — "Review" appears 1× in body text but as part of agent description ("for coder review"), NOT as a publish-review process | Body text match |
| 6 | Install | ❌ **NOT OBSERVED** — no install button | Console |
| 7 | Update | ❌ **NOT OBSERVED** — no update flow | Console |
| 8 | Uninstall | ❌ **NOT OBSERVED** — no uninstall | Console |
| 9 | Dependency | ❌ **NOT OBSERVED** — no dependency tracking | Console |
| 10 | Pricing | ❌ **NOT OBSERVED in Console** — pricing referenced via docs only (per §12.3 #5); no per-Agent pricing | `/billing` + `/corti-models` |
| 11 | Usage License | ❌ **NOT OBSERVED** — no license field on agents | Console |

### Corti publish model (OBSERVED + INFERRED)

```
[Corti-curated 20 pre-built agents]
    │
    │ (read-only, built into Console)
    ▼
[User forks one via "Use a template"]
    │
    ▼
[User's agent in "My agents" tab]
    │
    │ (no publish action — agent stays private to user)
    ▼
[Agent used via Console chat or API Client calls]
```

There is NO marketplace, NO publish flow, NO install/uninstall. The 20 pre-built agents are the only "shared" agents, and they're curated by Corti (not user-published).

### iCoDer marketplace surface (OBSERVED + memory-confirmed)

| # | Item | iCoDer status | Evidence |
|---|---|---|---|
| 1 | Who can publish | ❌ **NOT OBSERVED** — no publish button on user agents | `AgentDetailPage.tsx` — no publish action |
| 2 | Publish scope | ❌ **NOT OBSERVED** | Same |
| 3 | Organization Private | ❌ **NOT OBSERVED** | Same |
| 4 | Public | ❌ **NOT OBSERVED** — iCoDer **DELETED** the Marketplace concept in Phase 1.2 (per memory `project_p1_2_corti_parity_deletion_2026_06_30.md` — "5 自创 iCoDer concept 全删" includes Marketplace) | memory `project_p1_2_corti_parity_deletion_2026_06_30.md` |
| 5 | Review | ❌ **NOT OBSERVED** | Console |
| 6 | Install | ❌ **NOT OBSERVED** | Console |
| 7 | Update | ❌ **NOT OBSERVED** | Console |
| 8 | Uninstall | ❌ **NOT OBSERVED** | Console |
| 9 | Dependency | ❌ **NOT OBSERVED** | Console |
| 10 | Pricing | ❌ **NOT OBSERVED** | Console |
| 11 | Usage License | ❌ **NOT OBSERVED** — `agent_pack.json` has no `license` field | `agent_pack_schema.py` |

### iCoDer marketplace history (per memory)

iCoDer previously had a Marketplace concept (Phase 1.x) but **physically deleted it in Phase 1.2 Corti parity deletion** (commit 5c4e0e3, 92 files +304/-8936). This was a deliberate Corti-parity decision — Corti doesn't have a marketplace, so iCoDer removed theirs.

### §13.3 verdict

| Dimension | Corti | iCoDer | Parity |
|---|---|---|---|
| Who can publish | ❌ | ❌ | MATCH (both lack) |
| Publish scope | ❌ | ❌ | MATCH (both lack) |
| Organization Private | ❌ | ❌ | MATCH (both lack) |
| Public | ❌ | ❌ (deleted in P1.2) | MATCH (both lack, by design) |
| Review | ❌ | ❌ | MATCH (both lack) |
| Install | ❌ | ❌ | MATCH (both lack) |
| Update | ❌ | ❌ | MATCH (both lack) |
| Uninstall | ❌ | ❌ | MATCH (both lack) |
| Dependency | ❌ | ❌ | MATCH (both lack) |
| Pricing | ❌ | ❌ | MATCH (both lack) |
| Usage License | ❌ | ❌ | MATCH (both lack) |

**Overall §13.3:** MATCH across the board — both Corti and iCoDer lack marketplace concepts. iCoDer previously had one but deleted it for Corti parity (correct decision per memory).

---

## Per-item gap inventory (priority-ordered for Phase 5)

### iCoDer ADVANTAGES (already leading Corti)

#### ADV-13-01 — Forked-from badge

iCoDer shows a "Forked" badge on cloned agents via `config.source_agent_ref`. Corti does NOT track fork source.

**Status:** Keep as iCoDer ADVANTAGE. No action.

#### ADV-13-02 — Name auto-copied on fork

iCoDer's `agentHubApi.clone(agentId)` copies the source agent's name to the new agent. Corti's `?preset=` flow leaves the Name field empty (user must retype).

**Status:** Keep as iCoDer ADVANTAGE. No action.

#### ADV-13-03 — Toast on successful fork

iCoDer shows `已复制到我的智能体` ("Copied to my agents") toast on successful clone. Corti shows no toast.

**Status:** Keep as iCoDer ADVANTAGE. No action.

### MATCH (both Corti + iCoDer lack — by design)

- ❌ Version control (Draft/Published/Number/Immutable/Latest/Rollback) — DO NOT ADD
- ❌ Marketplace (Public/Private publish, Review, Install/Uninstall, Pricing, License) — DO NOT ADD
- ❌ Upstream update notification — DO NOT ADD
- ❌ Diff comparison — DO NOT ADD
- ❌ Re-sync from upstream — DO NOT ADD
- ❌ Schema migration tool — DO NOT ADD

### iCoDer GAPS vs Corti

**NONE.** iCoDer matches or exceeds Corti on every §13 dimension.

---

## iCoDer ADVANTAGES (Corti lacks these)

| # | iCoDer feature | Corti equivalent |
|---|---|---|
| 1 | "Forked" badge on cloned agents (`config.source_agent_ref`) | Corti shows no fork source |
| 2 | Name auto-copied on clone | Corti's `?preset=` flow leaves Name empty |
| 3 | Toast `已复制到我的智能体` on successful clone | Corti shows no toast |
| 4 | `version` field in `agent_pack.json` (display-only) | Corti has no version field at all |
| 5 | `agent_ref` attribute on Web Component (e.g., `medical-coding-agent-1.0.0`) for version-pin at embed time | Corti has no agent_ref concept (agent selected via Console config) |
| 6 | Hub "Chat / Use Agent" CTA (auto-clones + navigates to chat in 1 click) | Corti requires 2 clicks (click card → click "Create agent" → navigate) |

---

## Phase 5 Recommendations (priority-ordered)

### P3 — Minor polish (optional)

1. **Optional:** Add "Upstream sync" button on forked agents — show "upstream updated" badge if source pack changed. Useful if iCoDer ever ships v1.x → v2.x of pre-built agents. 4-6 hours. **LOW priority** — Corti doesn't have this either.

2. **Optional:** Add "Diff view" between forked agent and upstream. 6-8 hours. **LOW priority** — Corti doesn't have this either.

### DO NOT IMPLEMENT

- ❌ Full version control (Draft/Published/Number/Immutable/Latest/Rollback) — Corti doesn't have it. Match Corti.
- ❌ Marketplace (public/private publish, review, install/uninstall, pricing, license) — Corti doesn't have it. iCoDer already deleted theirs in P1.2 (correct decision).
- ❌ Schema migration tool — Corti doesn't have it. Match Corti.
- ❌ Per-Agent pricing — Corti doesn't have per-agent pricing. Match Corti.

---

## Cross-references

- `CORTI_THIRD_PARTY_INTEGRATION_AUDIT.md` — §11 (covers agent_ref embed)
- `RUN_TRACE_COST_PARITY_AUDIT.md` — §12 (covers version pinning in API calls)
- `CORTI_DEVELOPER_EXPERIENCE_AUDIT.md` — §10 (covers "Create agent" flow)
- `frontend/src/pages/AgentDetailPage.tsx:500-530` — iCoDer Fork button ("自定义")
- `frontend/src/pages/AgentDetailPage.tsx:911-915` — iCoDer Forked-from badge
- `frontend/src/pages/AgentChatPage.tsx:6` — iCoDer Hub CTA auto-clone flow
- `backend/app/api/icoder_agents_hub.py` — iCoDer clone endpoint
- `backend/icoder_runtime/core/agent_pack_schema.py` — iCoDer pack schema (with version field)
- `backend/app/api/embedded.py:55-58` — iCoDer Web Component `agent_ref` with version suffix

---

**Audit complete.** Next: §14 Parity Matrix 2.0 (20 dimensions) → §16 test fixtures → §17 final report → §18+§19 architecture inference + Phase 5 recommendation.
