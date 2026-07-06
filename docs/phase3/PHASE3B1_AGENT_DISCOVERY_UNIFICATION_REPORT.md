# Phase 3-B1 Section C — Agent Discovery Source Unification Report

**Date**: 2026-07-04
**Status**: COMPLETE — 4 entry points have clear, non-overlapping responsibilities; 12/13 contract tests pass (1 intentional gate test fails until Section D adds the medical-coding-agent card factory)

## C.1 Problem

Before Phase 3-B1, the iCoDer platform had 4 agent entry points with overlapping and unclear responsibilities:

1. `/api/icoder/agents/hub` — **404 (deleted in Phase 2.1-B)**
2. `/api/icoder/agents` — A2A discovery, returned only 1 agent (medcoder-coding-review)
3. `/.well-known/agent.json` — A2A standard, also returned only 1 agent
4. `/api/rest/v1/agent_definitions` — DB-mastered, auth-gated, mixed seed.py prebuilt + user-created

Users and developers saw different "Agent worlds" depending on which endpoint they hit. Section C unifies these 4 entry points with clear, non-overlapping responsibilities.

## C.2 4 Entry Point Responsibilities (Contract)

### C.2.1 Agent Hub — `/api/icoder/agents/hub` (Section B restored)

| Property | Value |
|---|---|
| **Purpose** | Product browsing — show users what Agents exist |
| **Data source** | `official_agents/**/agent_pack.json` (pack-mastered, file-system canonical) |
| **Auth** | No auth (read-only browsing) |
| **Returns** | 11 visible packs: 10 metadata-only (Coming Soon) + Medical Coding Agent MVP |
| **Excludes** | hidden_from_hub=true, expert-stub, internal_engine |
| **Operation ID** | `icoder_agents_hub_list_v1` |

**Card shape**: `agent_ref`, `name`, `display_name`, `category`, `maturity`, `production_ready`, `runnable`, `badge`, `red_lines`, `output_contract`, `run_endpoint` (None for metadata-only).

### C.2.2 A2A Discovery — `/api/icoder/agents` + `/.well-known/agent.json`

| Property | Value |
|---|---|
| **Purpose** | A2A v0.3 standard discovery — show what Agents can be invoked via A2A |
| **Data source** | `agent_card.py` card factories (pack-mastered via factory functions) |
| **Auth** | No auth (protocol standard) |
| **Returns** | Pre-Section-D: 1 agent (medcoder-coding-review). Post-Section-D: 2 agents (medcoder-coding-review + medical-coding-agent) |
| **Excludes** | metadata-only packs (no run path), expert-stubs (internal), internal_engine from user-level discovery |
| **Operation IDs** | `a2a_list_agents_v0_3`, `a2a_well_known_agent_json_v0_3`, `a2a_get_agent_card_v0_3`, `a2a_llms_txt_v0_3` |

**Card shape**: A2A v0.3 AgentCard (name, description, url, version, provider, capabilities, skills, securitySchemes, metadata.icoder).

### C.2.3 Agent Definitions — `/api/rest/v1/agent_definitions*`

| Property | Value |
|---|---|
| **Purpose** | Developer/ISV Agent CRUD — create, edit, delete user-owned agents |
| **Data source** | `Agent` DB model (DB-mastered; seed.py prebuilt + user-created) |
| **Auth** | Auth-gated in production (401 without token); test env bypasses via `ICODER_DISABLE_AUTH_FOR_TESTS=1` |
| **Returns** | DB rows with `is_prebuilt` field, NOT pack cards |
| **Distinct from Hub** | Hub returns pack cards with `agent_ref`; agent_definitions returns DB rows with `id` (UUID) |
| **Operation IDs** | 9 endpoints: list/get/create/update/delete/clone/categories/templates/version |

**Row shape**: `id`, `name`, `description`, `system_prompt`, `icon`, `category`, `expert_ids`, `is_prebuilt`, `is_published`, `version`, `status`, `created_by`, `usage_count`.

### C.2.4 Templates — `/api/rest/v1/agent_definitions/templates`

| Property | Value |
|---|---|
| **Purpose** | "New Agent" wizard starting points |
| **Data source** | Hardcoded `AGENT_TEMPLATES` list in `app/api/agents.py` |
| **Auth** | No auth (browsing templates is allowed; creating from a template requires auth at POST) |
| **Returns** | List of templates with `id`, `title`, `system_prompt`, `icon`, `category` |
| **NOT runnable** | Templates have NO `run_endpoint` — they're starting points, not deployed agents |
| **Operation ID** | `get_agent_templates` + `download_template_pack` |

**Critical distinction**: templates are NOT runnable Agents. They're skeletons for the "new agent" wizard. A user picks a template, customizes it, and saves — that creates a DB row in agent_definitions. The DB row can then be invoked (if it has experts wired).

## C.3 Visibility Matrix

| Pack type | Hub | A2A discovery | agent_definitions | templates |
|---|---|---|---|---|
| Medical Coding Agent (MVP, runnable) | ✅ visible + runnable | ✅ (post-Section-D) | ❌ (not a DB row) | ❌ |
| 10 metadata-only certified packs | ✅ visible + Coming Soon | ❌ (no run path) | ❌ (not DB rows) | ❌ |
| 4 expert-stub packs | ❌ hidden | ❌ hidden | ❌ (not DB rows) | ❌ |
| 1 internal_engine (medcoder-coding-review) | ❌ hidden | ✅ (card factory exists, internal orchestrator use) | ❌ (not DB row) | ❌ |
| seed.py 16 PREBUILT_AGENTS (DB rows) | ❌ (not pack-backed) | ❌ (no card factories) | ✅ (DB rows, is_prebuilt=True) | ❌ |
| User-created agents (DB rows) | ❌ (not pack-backed) | ❌ (no card factories; Phase 4 plugs in) | ✅ (DB rows, is_prebuilt=False) | ❌ |
| AGENT_TEMPLATES (hardcoded) | ❌ | ❌ | ❌ | ✅ |

**Key invariants**:
- Hub and A2A discovery are pack-mastered (read from `official_agents/agent_pack.json` or card factories)
- agent_definitions is DB-mastered (reads from `Agent` DB model)
- templates is hardcoded (reads from `AGENT_TEMPLATES`)
- No entry point mixes pack cards and DB rows

## C.4 seed.py PREBUILT_AGENTS vs agent_pack.json — Naming Collision Audit

### C.4.1 The two sources

| Source | Count | Type | Namespace |
|---|---|---|---|
| `app/seed.py` PREBUILT_AGENTS | 16 | DB rows (is_prebuilt=True) | kebab-case key (e.g., `code-validation`) |
| `official_agents/**/agent_pack.json` | 16 | File packs | agent_ref `icoder/{slug}@{version}` (e.g., `icoder/code-validation@1.0.0`) |

### C.4.2 Overlap (6 keys)

| seed.py key | agent_pack.json agent_ref | Status |
|---|---|---|
| `code-validation` | `icoder/code-validation@1.0.0` | Both exist — pack is canonical |
| `compliance-guardrail` | `icoder/compliance-guardrail@1.0.0` | Both exist — pack is canonical |
| `denial-appeals` | `icoder/denial-appeals@1.0.0` | Both exist — pack is canonical |
| `diagnosis-extractor` | `icoder/diagnosis-extractor@1.0.0` | Both exist — pack is canonical |
| `note-completeness` | `icoder/note-completeness@1.0.0` | Both exist — pack is canonical |
| `procedure-extractor` | `icoder/procedure-extractor@1.0.0` | Both exist — pack is canonical |

### C.4.3 Non-overlap (10 + 10)

**In seed.py only** (10 keys, NOT in agent_pack.json):
- `icd10-navigator`, `rule-explainer`, `surgical-registry`, `icu-summary`, `triage`, `med-reconciliation`, `discharge-edu`, `nursing-handoff`, `prior-auth`, `referral-gen`

These are legacy iCoDer concepts (pre-Corti pivot). Most are NOT in Corti's 20 Pre-built Agents list. They remain as DB rows for backwards compatibility but have no pack file — they won't appear in Hub or A2A discovery.

**In agent_pack.json only** (10 packs, NOT in seed.py):
- `cdi-review`, `code_reconciler`, `documentation-gap`, `drg-analyzer`, `evidence-ranker`, `evidence_extractor`, `index_navigator`, `medical_coding`, `medcoder-coding-review`, `tabular_validator`

These are Corti-aligned packs added in Phase 2-F / 3-A. They are file-system canonical — they appear in Hub and A2A discovery but not in seed.py DB rows.

### C.4.4 Collision avoidance strategy

1. **Different namespaces**: seed.py DB rows use kebab-case `key`; agent_pack.json uses `agent_ref = icoder/{slug}@{version}`. They don't collide at the identifier level.
2. **Hub and A2A discovery only read packs** — they never read DB rows. So the 10 seed.py-only DB rows are invisible to Hub/A2A users.
3. **agent_definitions reads DB only** — the 10 pack-only files are invisible to agent_definitions list. (Phase 4 may sync packs → DB, but that's out of scope.)
4. **The 6 overlapping keys** — when a user browses Hub, they see the pack version (Corti-aligned, with maturity=metadata-only, production_ready=false). When they list agent_definitions, they see the DB version (legacy seed.py row). These are clearly distinguished by shape (pack card vs DB row) and the `agent_ref` field (only pack cards have it).

**Result**: No silent collision. Users can tell which is which by:
- Hub/A2A cards have `agent_ref` starting with `icoder/`
- agent_definitions rows have `is_prebuilt` boolean and no `agent_ref`

## C.5 Files changed

| File | Change | LOC |
|---|---|---|
| `backend/tests/integration/icoder/test_phase3b1_discovery_unification_contract.py` | **new** — 13 contract tests | +295 |
| **Total** | | **+295** |

No code changes — Section C is documentation + contract tests. The Hub router (Section B) and A2A card factory (Section D) implement the contract.

## C.6 Tests added (13 new tests, 12 pass + 1 intentional gate)

| Test | Verifies | Status |
|---|---|---|
| `test_hub_is_pack_mastered_and_no_auth` | Hub reads packs, no auth, 11 visible | ✅ |
| `test_a2a_discovery_is_pack_mastered` | A2A discovery reads card factories, no auth | ✅ |
| `test_a2a_discovery_does_not_include_metadata_only_packs` | 10 metadata-only packs excluded from A2A | ✅ |
| `test_a2a_discovery_does_not_include_expert_stubs` | 4 expert-stubs excluded from A2A | ✅ |
| `test_agent_definitions_is_db_mastered` | agent_definitions is DB-shaped (is_prebuilt, no agent_ref) | ✅ |
| `test_templates_endpoint_no_auth` | templates endpoint returns 200, no auth | ✅ |
| `test_templates_are_not_runnable_agents` | templates have no run_endpoint | ✅ |
| `test_hub_and_a2a_discovery_are_both_pack_mastered` | Both pack-mastered, Hub has 11, A2A has ≥1 | ✅ |
| `test_medical_coding_agent_appears_in_hub` | Medical Coding Agent in Hub (Section B done) | ✅ |
| `test_medical_coding_agent_appears_in_a2a_after_section_d` | Medical Coding Agent in A2A (Section D gate) | ❌ **intentional gate** (passes after Section D) |
| `test_seed_prebuilt_agents_no_silent_collision_with_packs` | 6 overlapping keys appear in Hub as pack versions | ✅ |
| `test_well_known_agent_json_returns_200` | A2A standard discovery 200 | ✅ |
| `test_llms_txt_returns_200` | LLM-friendly A2A discovery 200 | ✅ |

**Result**: 12/13 PASS. The 1 failure is the Section D gate test — intentional, surfaces the Section D scope. After Section D adds the medical-coding-agent card factory, this test passes.

## C.7 Prompt success criteria mapping

| Prompt §C requirement | Implementation | Test |
|---|---|---|
| 1. Clear responsibilities for each entry point | C.2 contract (4 entry points, distinct data source + auth + return shape) | All 13 tests |
| 2. Medical Coding Agent in Hub AND A2A | Hub: ✅ (Section B). A2A: gate (Section D) | `test_medical_coding_agent_appears_in_hub` ✅; `test_medical_coding_agent_appears_in_a2a_after_section_d` ❌→✅ after D |
| 3. metadata-only in Hub, NOT in A2A runnable | Hub shows 10 metadata-only; A2A excludes them | `test_metadata_only_packs_visible_but_not_runnable` (Section B) + `test_a2a_discovery_does_not_include_metadata_only_packs` (Section C) ✅ |
| 4. expert-stubs not in Hub, not in user-level A2A | Hub excludes 4 expert-stubs; A2A excludes them | `test_expert_stubs_excluded` (Section B) + `test_a2a_discovery_does_not_include_expert_stubs` (Section C) ✅ |
| 5. internal_engine not in Hub, but exists as internal dependency | Hub excludes medcoder-coding-review; A2A includes it (card factory exists for internal orchestrator use) | `test_internal_engine_excluded` (Section B) ✅ |
| 6. seed.py vs agent_pack.json relationship documented | C.4 audit (6 overlap, 10+10 non-overlap, no silent collision) | `test_seed_prebuilt_agents_no_silent_collision_with_packs` ✅ |
| 7. Canonical source documented | C.2 contract: packs (Hub/A2A), DB (agent_definitions), hardcoded (templates) | All 13 tests |

## C.8 Verdict

**Section C verdict**: PASS — 4 entry points have clear, non-overlapping responsibilities; 12/13 contract tests pass; 1 intentional gate test will pass after Section D; seed.py vs agent_pack.json naming collision audited and documented; canonical sources clearly defined.

The unification is complete at the contract level. Section D implements the medical-coding-agent card factory that closes the gate test.
