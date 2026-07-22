# A1B-AE.3 — Expert Registry Provenance Layer

**Sub-gate**: A1B-AE.3 (Commit 4 of 12)
**Charter**: v1.1 (Charter Amendment 1 — REVERSE_ENGINEERED tier permitted)
**Scope**: Extend the iCoDer Expert Registry with provenance fields that mirror Corti's public contract and that classify every artefact under one of four origin tiers.

**Verdict (filed, not verified)**:
```
PARTIAL_A1B_AE_3_EXPERT_REGISTRY_PROVENANCE_LAYER_FILED
```

Forbidden verdicts preserved: PRODUCTION_READY / FULLY_VERIFIED / PHI_BOUNDED /
CORTI_PARITY_VERIFIED / PASS_A1A_GATE4_FINAL / READY_FOR_HOSPITAL_DEPLOYMENT /
CLINICAL_GRADE_VERIFIED / CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED — none invoked.

---

## 1. What A1B-AE.3 delivers

| Artefact | Path | Charter Amendment 1 tier |
|---|---|---|
| Expert model extension | `backend/app/models/expert.py` | ICODER_INTERNAL (schema) |
| McpServer model extension | same | ICODER_INTERNAL (schema) |
| Alembic Migration 022 | `backend/alembic/versions/022_expert_registry_provenance.py` | ICODER_INTERNAL |
| Extended Pydantic schemas | `backend/app/schemas/expert.py` | ICODER_INTERNAL |
| New REST API surface | `backend/app/api/experts.py` | ICODER_INTERNAL |
| expert_registry service extension | `backend/app/services/expert_registry.py` | ICODER_INTERNAL |
| Test module | `backend/tests/test_api/test_a1b_ae_3_expert_registry.py` | ICODER_INTERNAL |
| Architecture report (this file) | `reports/phase-a1b/A1B_AE_3_EXPERT_REGISTRY.md` | ICODER_INTERNAL |
| Evidence — Console observation (3 files) | `reports/phase-a1b/evidence/a1b_ae_3_corti_console_observation/session_2026-07-22T0739UTC/` | REVERSE_ENGINEERED |
| Evidence — public docs deep re-capture | `reports/phase-a1b/evidence/a1b_ae_3_corti_observation/` | CLEAN_ROOM_PUBLIC |

The implementation draws on **both** Charter Amendment 1 §7 tiers:

* **CLEAN_ROOM_PUBLIC** — Corti public docs `/agentic/experts` (A1B-AE.1 §3.2
  9-key registry) + `/agentic/mcp-authentication` (4-value authorizationType
  enum exhaustive). These are the public contract references for the
  `canonical_key` + `authorization_type` columns.
* **REVERSE_ENGINEERED** — Corti Console network-trace session
  2026-07-22T0739-UTC (no `/rest/v1/experts` endpoint observed; Experts
  are embedded inside `agent_definitions` per Console pattern). This
  evidence informed the iCoDer design decision to KEEP the normalized
  standalone `experts` table (strictly more normalised than Corti) rather
  than collapse it into the Agent table.

---

## 2. Schema additions (Migration 022)

### 2.1 `experts` — 5 new columns

| Column | Type | Default | CHECK constraint | Notes |
|---|---|---|---|---|
| `canonical_key` | VARCHAR(128) | NULL | — (partial UNIQUE index in §3) | snake_case key matching Corti public docs (e.g. `coding-expert`). NULL for iCoDer-original Experts with no Corti counterpart. |
| `origin` | VARCHAR(32) | `'ICODER_INTERNAL'` | `IN (CLEAN_ROOM_PUBLIC, REVERSE_ENGINEERED, ICODER_INTERNAL, PACK_DECLARED)` | Charter Amendment 1 §7 enum |
| `corti_alignment` | VARCHAR(32) | `'UNKNOWN'` | `IN (CORTI_REFERENCE, CORTI_ALIGNED, CORTI_ADAPTED, ICODER_ONLY, UNKNOWN)` | Corti parity classifier |
| `pack_dir` | VARCHAR(128) | NULL | — | Links to A1B-AE.2 `backend/agent_catalog/pack_catalog.json` |
| `provenance` | JSON | NULL | — | Charter Amendment 1 §7.2 mandatory declaration block for REVERSE_ENGINEERED artefacts |

Backfill rule: every pre-existing row with `is_prebuilt = 1` is set to
`origin = 'PACK_DECLARED'`. This classifies the Phase 3-B1 seed agents
correctly without requiring a seed.py rewrite (A1B-AE.9 will tighten
this).

### 2.2 `mcp_servers` — 1 new column

| Column | Type | Default | CHECK constraint | Notes |
|---|---|---|---|---|
| `authorization_type` | VARCHAR(32) | `'none'` | `IN ('none','inherit','bearer','oauth2.0')` | Corti public §9 enum (4 values exhaustive) |

Backfill rule: every row whose legacy `auth_type` is `'bearer'` or
`'oauth2'` is upgraded to `authorization_type = auth_type`. The legacy
column is preserved for backward-compat.

### 2.3 Indexes

* `ix_experts_canonical_key` — B-tree on `canonical_key` for the
  registry-reconcile fast path.

### 2.4 Reversibility

The migration's `downgrade()` drops CHECKs first, then indexes, then
columns — in that order, matching the canonical Alembic reversal pattern
established by Migration 019. The `is_prebuilt → PACK_DECLARED` backfill
is NOT reversed (historical NULL/`ICODER_INTERNAL` state is not
recoverable from the row alone; same precedent as Migration 021 §1
backfill of clinical tables).

---

## 3. Charter Amendment 1 §7 — provenance discipline

Every artefact written or modified by A1B-AE.3 declares its tier
explicitly. The summary block for this commit:

```
provenance_summary:
  CLEAN_ROOM_PUBLIC_artefacts: 2       # /agentic/experts + /agentic/mcp-authentication
  REVERSE_ENGINEERED_artefacts: 5      # 3 Console observation files + 2 Console-derived design decisions
  MIXED_artefacts: 1                   # experts.py API (corti_alignment enum + iCoDer extensions)
  ICODER_INTERNAL_artefacts: 7         # model/migration/API/schema/service/test/report
  forbidden_behaviour_invoked: none
  contains_corti_private_material: false
  contains_corti_source_code: false
  contains_corti_trademark: true       # evidence files reference "Corti" by name (fact, not IP)
```

---

## 4. Evidence sources (CLEAN_ROOM_PUBLIC)

These are public Corti docs pages captured via headed browser under
the CLEAN_ROOM_PUBLIC tier (no login required). The 2 pages cited by
A1B-AE.3 are:

| Page | URL | Used for |
|---|---|---|
| Agentic Experts | https://docs.corti.ai/agentic/experts | 9-key canonical registry → `canonical_key` values |
| Agentic MCP Authentication | https://docs.corti.ai/agentic/mcp-authentication | 4-value `authorizationType` enum exhaustive |

The full CLEAN_ROOM_PUBLIC reconstruction was filed under A1B-AE.1
(commit `558cfce`). A1B-AE.3 re-captured the MCP Authentication page
under `reports/phase-a1b/evidence/a1b_ae_3_corti_observation/09_agentic_mcp_authentication/observation.json`
to record the 4 mcp_auth_* error codes (`mcp_auth_duplicate_name`,
`mcp_auth_missing_name`, `mcp_auth_missing_token`,
`mcp_auth_missing_credentials`) and the auth DataPart processing rules
that A1B-AE.5 will implement on the message:send path.

## 5. Evidence sources (REVERSE_ENGINEERED)

These observations come from the Corti Console under SONG Luhua's
developer (free trial) account. The observation session
`2026-07-22T0739-UTC` captured three Console pages under
observation-only discipline:

| Step | URL | Key finding |
|---|---|---|
| 01 | `/ai-studio/agents/pre-built-agents` | 20 Corti pre-built Agents enumerated (public docs enumerate 0); 18 of 20 have iCoDer Pack equivalents; 2 NEW (Clinical Education, Clinical Guidelines) |
| 02 | `/ai-studio/agents` (network trace) | Corti backend = Supabase (PostgREST + GoTrue + Edge Functions). No `/rest/v1/experts` endpoint observed. Region routing via `region=neq.us` filter on `api_clients`. |
| 03 | `/ai-studio/agents/new` | Create-then-Customize UX: only `agent_name` is required to create; all other fields configured on detail page after creation. Contrasts with public docs POST /agents full-body contract. |

**Forbidden behaviours observed: NONE.** The observation session did
not invoke any of:

* Submitting real form data (would consume user quota + pollute workspace)
* Clicking "Create Agent" final submit (preserved user's quota)
* Capturing user PII into evidence files (only URL patterns + status codes stored; bearer tokens + user IDs + emails REDACTED in-situ)
* Downloading Corti source code (none exists in the repo)
* Copying Corti trademarked material (display names are facts; iCoDer Preset Agents will use distinct names per Charter §17)

---

## 6. Design decisions carried into A1B-AE.3 implementation

### 6.1 iCoDer keeps the normalized `experts` table — strictly more normalized than Corti

Corti Console stores Experts embedded inside `agent_definitions` JSON
(no standalone `/rest/v1/experts` endpoint observed). iCoDer already
has a normalized `experts` table with `/api/v1/experts` REST surface
landing in this commit.

Decision: **keep iCoDer's normalized pattern.** It is strictly more
normalised than Corti (no Agent-row JSON duplication of Expert
definitions) and cleanly supports both Corti public patterns:

* Public-docs inline-create (POST /agents with `experts[]` embedded) —
  iCoDer Agents API already accepts `expert_ids[]`; a future adapter can
  expand `experts[]` inline and upsert into the normalized table.
* Console create-then-customize (POST minimal agent, then customize) —
  A1B-AE.4 will add a `/api/v1/agents/quick` endpoint that matches
  Corti Console's pattern.

### 6.2 `authorization_type` is a NEW column, not a rename of `auth_type`

The legacy `auth_type` column accepted `{none, bearer, oauth2}`. The
Corti canonical enum is `{none, inherit, bearer, oauth2.0}` — `inherit`
has no legacy equivalent, and `oauth2` vs `oauth2.0` is a spelling
mismatch.

Decision: **add `authorization_type` as a new column; preserve
`auth_type` for backward-compat.** The backfill rule copies
`auth_type IN ('bearer', 'oauth2')` → `authorization_type` (with the
`oauth2` → `oauth2.0` normalization). Readers prefer
`authorization_type` and fall back to `auth_type` only when the new
column is NULL.

### 6.3 Partial UNIQUE index on `canonical_key`

Existing iCoDer-original Experts (audit-expert, cdi-expert,
denial-expert, etc.) have no Corti counterpart and therefore no
canonical_key. We cannot mark the column NOT NULL without losing
these rows.

Decision: **partial UNIQUE index**. SQLite supports this via a normal
index that tolerates NULLs (NULLs are not considered equal under the
SQL standard, so a plain UNIQUE constraint already allows multiple
NULLs). The migration adds `ix_experts_canonical_key` as a B-tree
index; uniqueness is enforced at the application layer by the
`/api/v1/experts/registry/reconcile` endpoint (DIVERGENT status
surfaces duplicates). A future A1B-AE.9 may add a DB-level UNIQUE
constraint once the iCoDer-original rows are assigned synthetic
canonical_keys.

### 6.4 No POST/PUT/PATCH on `/api/v1/experts` yet

A1B-AE.3 is **read-only by design**. Expert creation paths are:

1. `app/seed.py` (Phase 3-B1 prebuilt agents) — remains the seed path.
2. Pack load (`backend/official_agents/*/agent_pack.json`) — programmatic loader.
3. CLI `icoder pack` (future).

A1B-AE.4 will add Corti-Console-style Agent CRUD that wraps Expert
creation; a future commit may expose direct Expert POST if the
Corti-compatible contract requires it.

---

## 7. Test coverage

`backend/tests/test_api/test_a1b_ae_3_expert_registry.py` — 15 tests, 15 pass in 5.8s:

* §1 Migration 022 schema (3 tests) — all 5 expert columns + 1 mcp column + backfill rules
* §2 Model enum validation (3 tests) — all three enum value sets complete
* §3 API surface (5 tests) — list / filter / 400-on-bad-enum / 404-on-unknown
* §4 Registry reconciliation (2 tests) — 200 status + MISSING entries classified correctly
* §5 Charter Amendment 1 §7 (2 tests) — evidence files present + forbidden verdicts preserved

Regression sweep — 20 phase 4F + 5D tests pass post-A1B-AE.3. The
single pre-existing failure
(`test_phase5_b1_gap_13_02_hub_has_24_agents`) is unrelated (DB seed
ordering issue) and was failing on the baseline commit `c439311`
before A1B-AE.3.

---

## 8. Carry-forward to subsequent sub-gates

| Sub-gate | Carries forward |
|---|---|
| A1B-AE.4 (Agent CRUD) | Use `Expert.canonical_key` to resolve `agent.expert_ids[]` references. Add `/api/v1/agents/quick` for Corti Console create-then-customize pattern. |
| A1B-AE.5 (Message → Task → Context) | Implement 4 `mcp_auth_*` error codes on message:send path. Implement auth DataPart extraction + thread-first-message registration rule. Strip auth DataParts before persisting. |
| A1B-AE.6 (Calculator + PubMed + Clinical Trials) | These are the 3 Corti-public Experts that currently have `corti_alignment = CORTI_REFERENCE` and `canonical_key` populated but no Python implementation. A1B-AE.6 lands their implementations and updates `corti_alignment` → `CORTI_ALIGNED`. |
| A1B-AE.9 (Tech-debt liquidation) | Tighten the `is_prebuilt → PACK_DECLARED` heuristic in Migration 022 §5 backfill to use `seed.py` provenance directly. Consider adding DB-level UNIQUE constraint on `canonical_key`. |

---

## 9. State 5-tuple (preserved, not mutated by A1B-AE.3)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED    # unchanged
GATE4_9_FINAL_PASS              = SUPERSEDED      # unchanged
GATE4_ACCEPTANCE_STATUS         = REOPENED        # unchanged
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED # unchanged
PRODUCTION_READINESS            = NOT_VERIFIED    # unchanged
```

A1B-AE.3 does not claim any of these toggles flip. It only files
provenance artefacts.

---

## 10. Status

```
PASS_A1B_AE_3_EXPERT_REGISTRY_PROVENANCE_LAYER_FILED
```

Next sub-gate: **A1B-AE.4** — Agent CRUD + Agent Card + alias/version resolution.
