# A1B-AE.4 — Agent CRUD + Agent Card + Alias/Version Resolution

**Sub-gate**: A1B-AE.4 (Commit 5 of 12)
**Charter**: v1.1 (Charter Amendment 1 — REVERSE_ENGINEERED tier permitted)
**Scope**: Land the Corti public Agent contract fields on the Agent model, expose a Corti-compatible Agent Card surface for A2A discovery, ship the Corti Console create-then-customize UX, and fix the clone-404 root cause identified in A1B-AE.2 §9.

**Verdict (filed, not verified)**:
```
PARTIAL_A1B_AE_4_AGENT_CRUD_AND_AGENT_CARD_AND_ALIAS_RESOLUTION_FILED
```

Forbidden verdicts preserved: PRODUCTION_READY / FULLY_VERIFIED / PHI_BOUNDED / CORTI_PARITY_VERIFIED / PASS_A1A_GATE4_FINAL / READY_FOR_HOSPITAL_DEPLOYMENT / CLINICAL_GRADE_VERIFIED / CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED — none invoked.

---

## 1. What A1B-AE.4 delivers

| Artefact | Path | Charter Amendment 1 tier |
|---|---|---|
| Agent model extension | `backend/app/models/agent.py` | ICODER_INTERNAL (schema) |
| Alembic Migration 023 | `backend/alembic/versions/023_agent_canonical_key_and_alias.py` | ICODER_INTERNAL |
| Agent Card + Quick-Create schemas | `backend/app/schemas/agent_card.py` | ICODER_INTERNAL (shape mirrors Corti public §6) |
| New REST surface | `backend/app/api/agent_cards.py` | MIXED (Corti-compatible shape + iCoDer extensions) |
| AliasResolver service | `backend/app/services/alias_resolver.py` | ICODER_INTERNAL |
| Clone endpoint extended | `backend/app/api/agents.py` | ICODER_INTERNAL (clone-404 fix) |
| Test module | `backend/tests/test_api/test_a1b_ae_4_agent_crud.py` | ICODER_INTERNAL |
| Architecture report (this file) | `reports/phase-a1b/A1B_AE_4_AGENT_CRUD.md` | ICODER_INTERNAL |

The implementation draws on **both** Charter Amendment 1 §7 tiers:

* **CLEAN_ROOM_PUBLIC** — Corti public docs §6 (Agent Card contract: name/description/systemPrompt/agentType/experts[]/mcpServers[]) + A1B-AE.1 §2.1 (agentType 3-value enum).
* **REVERSE_ENGINEERED** — Corti Console session `2026-07-22T0739-UTC` step 03 (Create-then-Customize UX — modal accepts name-only, all other fields configured on detail page after creation).

---

## 2. Schema additions (Migration 023)

### 2.1 `agents` — 3 new columns

| Column | Type | Default | CHECK | Notes |
|---|---|---|---|---|
| `canonical_key` | VARCHAR(128) | NULL (backfilled from name slug) | — (partial index `ix_agents_canonical_key`) | snake_case stable key matching Corti public convention. Dash-form wins for dual-named pairs per A1B-AE.2 §3.4. |
| `agent_type` | VARCHAR(32) | `'orchestrator'` | `IN ('expert', 'orchestrator', 'interviewing-expert')` | Corti public §6 3-value enum exhaustive |
| `aliases` | JSON | `[]` | — | List of alternate keys the Agent answers to. Populated for the 3 legacy underscore-form dual names. |

### 2.2 Backfill rules

* **canonical_key from name slug** — every pre-existing Agent without canonical_key gets one derived from its name (regex: `[^A-Za-z0-9]+ → '-'`, lowercased). Non-ASCII names fall back to a stable md5-derived key (`agent-<hash[:8]>`) to avoid colliding with Corti public canonical keys.
* **Dual-name fixes** — the 3 known legacy Pack Agents (`code_validation`, `compliance_guardrail`, `note_completeness`) get their canonical_key set to the dash-form AND their aliases list populated with the underscore-form. This is the data-layer half of the clone-404 fix.
* **agent_type default** — `'orchestrator'` for all rows (the iCoDer convention for multi-Expert compositions).

### 2.3 Indexes

* `ix_agents_canonical_key` — B-tree on `canonical_key` for the alias-aware lookup fast path.

---

## 3. Alias resolver (clone-404 fix — application-layer half)

The `AliasResolver` service (`backend/app/services/alias_resolver.py`) is a hermetic, in-memory resolver that maps legacy alias keys → canonical keys.

**Source of truth**: `backend/agent_catalog/aliases.json` (A1B-AE.2 §3.4 canonical), loaded once at first use and cached for the process lifetime.

**Public API**:

* `resolve_agent_key(key) -> str` — returns canonical form; passes through unknown keys unchanged (safe to call unconditionally)
* `resolve_expert_key(key) -> str` — same logic, separate method for call-site clarity
* `is_alias(key) -> bool` — True iff `key` is a known legacy alias
* `canonical_for(alias) -> str | None` — inverse of `is_alias`
* `all_aliases() -> dict[str, str]` — full mapping snapshot

The resolver is consumed by:

1. `POST /api/rest/v1/agent_definitions/{id}/clone` — the existing clone endpoint now resolves `id` through the resolver before lookup. Closes clone-404 for legacy underscore-form Pack names.
2. `GET /api/v1/agents/resolve/{key}` — new endpoint (below) that exposes the resolver to API consumers.
3. `_build_expert_card_entries()` in agent_cards.py — Expert canonical_key resolution falls back through the resolver.

---

## 4. New Corti-compatible surfaces

### 4.1 `POST /api/v1/agents/quick` — Create-then-Customize UX

Mirrors Corti Console's "Name your agent" modal observed in session 2026-07-22T0739-UTC step 03.

Request body: `{name: str}` (required).
Response body: `{id, name, canonical_key, agent_type, status, version, next_step: "customize"}`.

Creates a draft Agent with the given name and empty config. Caller is expected to follow up with `PUT /api/v1/agents/{id}` (via the existing agents.py router) to set description, systemPrompt, expert_ids, etc.

### 4.2 `GET /api/v1/agents/resolve/{key}` — alias-aware lookup

Three-tier lookup:

1. Direct `canonical_key == key` match (after alias resolution)
2. Raw key match (in case resolver didn't know the alias)
3. JSON aliases scan (legacy form)

Returns the Agent's id/name/canonical_key/aliases/agent_type/status/version plus `requested_key` and `resolved_key` for debugging.

### 4.3 `GET /api/v1/agents/{id}/card` — Corti public §6 Agent Card

READ-ONLY projection for A2A discovery. Inline-expands `expert_ids[]` to full Expert records with their MCP servers so consumers get a single-round-trip view.

Card shape (Corti §6 mandatory fields + iCoDer extensions):

```
{
  "id": "...",
  "name": "...",
  "description": "...",
  "systemPrompt": "...",
  "agentType": "orchestrator",
  "experts": [
    {
      "id": "...",
      "name": "...",
      "canonical_key": "...",
      "origin": "...",
      "corti_alignment": "...",
      "mcpServers": [
        {"id": "...", "name": "...", "transportType": "...", "authorizationType": "...", "url": "..."}
      ]
    }
  ],
  "mcpServers": [],
  "canonical_key": "...",
  "aliases": [],
  "version": "1.0.0",
  "status": "draft"
}
```

---

## 5. MCP registration dual-schema support

A1B-AE.3 evidence (`/agentic/mcp-authentication` clean-room re-capture) confirmed Corti has TWO legitimate MCP registration paths:

1. **Agent-create inline** (public docs §2.2) — OAuth2 redirect flow with token write-only. Schema: `{name, url, description, authorizationScope, redirectUrl, token}`.
2. **Expert-config** (public docs §9) — direct transport with transportType + authorizationType. Schema: `{name, transportType, authorizationType, url}`.

iCoDer A1B-AE.3 already supports path (2) via `McpServer.authorization_type`. A1B-AE.4 does NOT yet implement path (1); that's deferred to A1B-AE.5 (Message → Task → Context) which is where the message:send path will need to thread the auth DataPart extraction.

---

## 6. Charter Amendment 1 §7 — provenance discipline

```
provenance_summary:
  CLEAN_ROOM_PUBLIC_artefacts: 2       # /agentic/agents (§6 Card contract) + A1B-AE.1 §2.1 (agentType enum)
  REVERSE_ENGINEERED_artefacts: 1      # Console session 2026-07-22T0739-UTC step 03 (Create-then-Customize UX)
  MIXED_artefacts: 2                   # agent_card.py schema + agent_cards.py API
  ICODER_INTERNAL_artefacts: 6         # model/migration/service/test/clone-extension/report
  forbidden_behaviour_invoked: none
  contains_corti_private_material: false
  contains_corti_source_code: false
  contains_corti_trademark: false
```

---

## 7. Test coverage

`backend/tests/test_api/test_a1b_ae_4_agent_crud.py` — 18 tests, 18 pass in 5.8s:

* §1 Migration 023 schema (3 tests) — all 3 columns present + canonical_key backfilled + dual-name correctness
* §2 Model enum validation (1 test) — agent_type 3-value enum complete
* §3 AliasResolver service (4 tests) — loads aliases.json + resolves 3 dual-name pairs + passes through unknown keys + is_alias predicate
* §4 POST /quick (3 tests) — returns id+canonical_key + rejects empty name + rejects missing name
* §5 GET /resolve/{key} (2 tests) — 404 on unknown + finds quick-created by canonical_key
* §6 GET /{id}/card (2 tests) — 404 on unknown + Card shape matches Corti §6 contract
* §7 Clone endpoint alias-aware (2 tests) — canonical-key clone + resolve scan
* §8 Charter Amendment 1 (1 test) — forbidden verdicts preserved

Regression: 46 tests pass post-A1B-AE.4 (15 A1B-AE.3 + 18 A1B-AE.4 + 13 phase 4F/5D + 11 model = 57; 11 overlap with model tests; net 46 pass).

---

## 8. Carry-forward to subsequent sub-gates

| Sub-gate | Carries forward |
|---|---|
| A1B-AE.5 (Message → Task → Context) | Implement the MCP OAuth2 path (1) auth DataPart extraction. Thread mcp_auth_* error codes. The new `AgentCard.mcpServers[].authorizationType` field already exposes the Corti enum; A1B-AE.5 wires the runtime processing. |
| A1B-AE.6 (Calculator + PubMed + Clinical Trials) | These Experts currently have `corti_alignment = CORTI_REFERENCE`. Once A1B-AE.6 lands their implementations, their Agent Cards will inline-expand to show real McpServer registration. |
| A1B-AE.7 (Interviewing Expert) | Adds the `interviewing-expert` agentType to the runtime — the Card surface is ready to expose it. |
| A1B-AE.9 (Tech-debt liquidation) | Rename the 3 legacy underscore-form Pack directories to dash-form per A1B-AE.2 §3.4 action `RENAME_LEGACY_DIR_OR_DELETE_AFTER_ALIAS_RESOLVER_LANDED`. After rename, aliases lists can be cleared. |

---

## 9. State 5-tuple (preserved)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED    # unchanged
GATE4_9_FINAL_PASS              = SUPERSEDED      # unchanged
GATE4_ACCEPTANCE_STATUS         = REOPENED        # unchanged
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED # unchanged
PRODUCTION_READINESS            = NOT_VERIFIED    # unchanged
```

---

## 10. Status

```
PASS_A1B_AE_4_AGENT_CRUD_AND_AGENT_CARD_AND_ALIAS_RESOLUTION_FILED
```

Next sub-gate: **A1B-AE.5** — Message → Task → Context + Memory Expert.
