# A1B-AE.2 — Unified Agent / Expert / Pack / Preset Agent Taxonomy

**Charter**: A1B-AE.0 (v1.0, 2026-07-22)
**Worktree**: `E:/Corti4C-agent-expert`
**Branch**: `phase-a1b/agent-expert-clean-room`
**Clean-room basis**: Corti public contracts (A1B-AE.1 §2–§7) + iCoDer filesystem observation
**Generated**: 2026-07-22 (UTC)
**Machine-rebuildable from**: `scripts/a1b_ae_2_build_catalogs.py` → `backend/agent_catalog/*.json`

---

## §1. Purpose

Before A1B-AE, iCoDer used the words "Agent", "Expert", "Pack", "Prebuilt",
"Preset Agent", "Tool", "MCP Server" with shifting meanings across at least
6 distinct sources:

1. **Filesystem Packs** under `backend/official_agents/<dir>/agent_pack.json`
2. **Legacy Python Packs** under `backend/official_agents/<dir>/__init__.py`
3. **DB rows** in `agents` table (seeded via `backend/app/seed.py`)
4. **Runtime registry** (`icoder_runtime.core.registry.RuntimeAgentRegistry`)
5. **Hub API surface** (`backend/app/api/icoder_agents_hub.py` `_load_packs()`)
6. **Run API surface** (`backend/app/api/agent_run.py` `_load_pack_by_agent_id()`)
7. **Admin API surface** (`backend/app/api/admin.py`)
8. **Frontend Agent Cards** (`frontend/src/pages/AgentsPage.tsx`)

The result was that "how many agents does iCoDer ship?" had no single answer
(historical claims in prior audit reports: 11 / 14 / 16 / 23 / 29 — see §3
of the companion Reconciliation report).

This document defines the **single canonical taxonomy** going forward.
Every downstream A1B-AE commit MUST use these terms per these definitions.

## §2. Core taxonomy (8 kinds)

| # | Kind | Definition | Canonical source | Unique ID |
|---|---|---|---|---|
| 1 | **Agent** | A user-addressable capability composed of one or more Experts + a system prompt + optional MCP servers. Corti `agentType ∈ {expert, orchestrator, interviewing-expert}` (A1B-AE.1 §2.3). | `backend/agent_catalog/agent_catalog.json` | canonical_name (dash-form) |
| 2 | **Expert** | A discrete LLM-powered capability an Agent can call. Corti public 9-key registry is the reference frame; iCoDer adds internal Python experts (A1B-AE.1 §3). | `backend/agent_catalog/expert_catalog.json` | key (dash-form) |
| 3 | **Agent Pack** (or just **Pack**) | A filesystem directory under `backend/official_agents/<dir>/` that materialises an Agent. Pack = the **distribution format**, NOT the Agent itself. | `backend/agent_catalog/pack_catalog.json` | dir_name |
| 4 | **Preset Agent** | A Corti-clean-room-authored Agent that ships with the platform (5 in A1B-AE.8). Tagged `origin=ICODER_CLEAN_ROOM`, `official_corti_preset=false`. | (A1B-AE.8) | canonical_name |
| 5 | **Tool** | An MCP-server-provided callable (`tools/call` endpoint). Per Corti public MCP contract (A1B-AE.1 §4). | (deferred to A1B-AE.7) | namespaced by MCP server |
| 6 | **MCP Server** | An external process implementing MCP (`tools/list`, `tools/call`). Token is write-only (A1B-AE.1 §4.1–4.2). | (deferred to A1B-AE.7) | name |
| 7 | **Agent Card** | The Corti-style JSON "business card" for an Agent: identity, endpoint, A2A capabilities, auth, skills (A1B-AE.1 §5). | `docs/ICODER_V1_AGENT_CARD_SPEC.md` | agent_id |
| 8 | **Task / Message / Part / Artifact / Context / Memory** | The 6 Corti public runtime elements (A1B-AE.1 §6). | (A1B-AE.5 / A1B-AE.6) | per-element |

The single sentence summary:
> **A Pack materialises an Agent. An Agent composes Experts. Experts call Tools on MCP Servers. Agents advertise themselves via Agent Cards. Agents communicate via Messages composed of Parts, grouped into Tasks within Contexts, indexed by Memory.**

## §3. Classification taxonomy (replaces all prior ad-hoc labels)

### §3.1 Pack classification (4 exhaustive values)

| Class | Definition | Source-of-truth marker | Count (A1B-AE.2) |
|---|---|---|---|
| `RUNNABLE_PACK` | dir has both `__init__.py` (Python) AND `agent_pack.json` | filesystem | 2 |
| `METADATA_ONLY_PACK` | dir has only `agent_pack.json` (no runnable Python) | filesystem | 27 |
| `LEGACY_CODE_ORPHAN` | dir has only `__init__.py` (missing Pack manifest) | filesystem | 3 |
| `EMPTY` | dir is empty | filesystem | 0 |
| **total** | | | **32** |

**Replaces** prior labels `runnable`, `metadata-only`, `stub`, `internal_engine`,
`expert-stub`, `certified`, `beta`, etc. — those remain inside Pack manifests
as the legacy `agent_type` field but are NOT the canonical classification.

### §3.2 Agent classification (3 exhaustive values)

| Class | Definition |
|---|---|
| `RUNNABLE_PACK` | The Agent has a runnable Pack backing it (class copied from Pack). |
| `METADATA_ONLY_PACK` | The Agent has only a metadata Pack; no execution path (yet). |
| `SEED_ONLY_NO_PACK` | The Agent appears in `seed.py#PREBUILT_AGENTS` but has NO Pack. |

(No `LEGACY_CODE_ORPHAN` Agents exist because the alias resolver in A1B-AE.4
will collapse `code_validation` legacy code into the canonical
`code-validation` Pack entry. Until A1B-AE.4 lands, the 3 legacy orphans
are visible in `pack_catalog.json` but already mapped via `aliases.json`.)

### §3.3 Expert classification (3 exhaustive values)

| Class | Definition | Count (A1B-AE.2) |
|---|---|---|
| `CORTI_PUBLIC` | One of the Corti public 9-key registry (A1B-AE.1 §3.2). | 9 |
| `ICODER_INTERNAL` | Python module under `backend/app/agents/experts/*.py`. | 11 |
| `PACK_DECLARED` | Referenced inside an `agent_pack.json#experts[]` but not in either of the above. | 20 |
| **total unique keys** | | **40** |

Corti alignment verdict per Expert:
- `CORTI_REFERENCE` — the 9 clean-room Corti keys
- `ALIGNED` — iCoDer internal/Pack-declared Expert whose name matches a Corti key
- `ICODER_ONLY` — no Corti counterpart (this is fine — iCoDer is a superset)
- `UNKNOWN` — Pack-declared but not yet inspected

## §4. Pack ↔ Agent ↔ Expert join semantics

A canonical Agent entry in `agent_catalog.json` has:

```
canonical_name           # unique key (dash-form)
canonical_agent_ref      # e.g. "icoder/code-validation-agent@2.0.0" (or null for seed-only)
sources                  # list of files that mention this Agent
pack_dir                 # the canonical Pack dir name
seed_key                 # matching key in seed.py#PREBUILT_AGENTS (or null)
expert_ids               # deduped union of Pack-declared + seed-named experts
classification           # RUNNABLE_PACK | METADATA_ONLY_PACK | SEED_ONLY_NO_PACK
dual_name_migration      # "legacy_name -> canonical_name" or null
```

### §4.1 Dual-name resolution rule (canonical)

For the 3 observed dual-name pairs:

```
code_validation       → code-validation        (Pack metadata canonical)
compliance_guardrail  → compliance-guardrail   (Pack metadata canonical)
note_completeness     → note-completeness      (Pack metadata canonical)
```

The dash-form is canonical because:
- Corti public convention uses dashes (A1B-AE.1 §3.2 — `medical-calculator-expert`, `web-search-expert`, etc.).
- The dash-form has the newer version claim (code-validation `@2.0.0` vs code_validation `@1.0.0`).
- `seed.py#PREBUILT_AGENTS` already uses dash-form keys (e.g. `"code-validation"`, `"compliance-guardrail"`).

The underscore-form continues to work as an alias resolved by the A1B-AE.4
alias resolver. The legacy Python code in `code_validation/__init__.py`
will be liquidated in A1B-AE.9 once the alias resolver has been online for
a full Gate 4-style negative test cycle.

## §5. "Preset Agent" vs "Prebuilt Agent" — disambiguation

These two terms have been used interchangeably in prior iCoDer docs. A1B-AE
establishes:

| Term | Definition | A1B-AE section |
|---|---|---|
| **Prebuilt Agent** | Any Agent that ships in the platform (Pack-backed OR seed-only). | §2.1 above |
| **Preset Agent** | A Corti-clean-room-authored Agent (5 in A1B-AE.8) that demonstrates a Corti agentType pattern. | A1B-AE.8 |

`Prebuilt` is the larger set (32 Pack dirs + 16 seed rows - duplicates =
29 canonical Agents per the catalog).
`Preset` is the smaller clean-room set (5).

Both are tagged `is_prebuilt=True` in the DB. Only Preset Agents additionally
carry `origin=ICODER_CLEAN_ROOM` + `official_corti_preset=false` (Corti does
not publicly enumerate any preset Agents per A1B-AE.1 §3.2 note).

## §6. Source-of-truth hierarchy (when sources disagree)

For any Agent, the canonical answer to "what is X?" comes from this
precedence order:

1. **`backend/agent_catalog/agent_catalog.json`** (machine-rebuilt by
   `scripts/a1b_ae_2_build_catalogs.py`).
2. If the catalog is stale (file system changed but catalog not rebuilt):
   a. **`backend/official_agents/<canonical-name>/agent_pack.json`** — for
      Agent identity, version, manifest, agent_ref, declared experts.
   b. **`backend/app/seed.py#PREBUILT_AGENTS`** — for DB-seeded Agent name,
      description, category, expert_name.
3. If both 2a and 2b are silent: the Agent does NOT exist. (Hub UI showing
   it is a bug; runtime accepting it is a bug.)
4. The legacy `__init__.py` Python docstring claim (e.g.
   `# Agent ref: icoder/code-validation-agent@1.0.0`) is **informational
   only** — never authoritative.

This hierarchy is binding on all A1B-AE.3+ implementations.

## §7. What this taxonomy is NOT

- It is NOT a new schema or DB migration (those land in A1B-AE.3).
- It is NOT a runtime behaviour change (that lands in A1B-AE.4 onwards).
- It is NOT a Corti parity claim — see A1B-AE.1 §14 verdict.
- It is NOT a verdict on Pack quality (a Pack may be `METADATA_ONLY_PACK`
  and still ship useful documentation).

## §8. Maintenance contract

- Anyone adding a new Pack MUST re-run
  `python scripts/a1b_ae_2_build_catalogs.py` and commit the regenerated
  catalog files alongside the Pack.
- Anyone renaming a Pack MUST update `aliases.json` (which the script
  regenerates) and ensure no dual-name shadowing is introduced.
- Anyone seeding a new Agent via `seed.py` MUST re-run the catalog builder.
- The catalog builder is hermetic: no DB, no network, no env vars.
  Output is byte-stable for a given filesystem state.

## §9. Verdict for A1B-AE.2 taxonomy

```
A1B_AE_2_TAXONOMY_AND_CANONICAL_CATALOGS_ESTABLISHED
```

**Established** because:
- 8-kind taxonomy documented (§2).
- 4-value Pack classification with machine-derived counts (§3.1): 2 / 27 / 3 / 0.
- 3-value Agent classification with machine-derived counts (§3.2): 27 + 2 + 0 (post-alias) = 29 canonical.
- 3-value Expert classification with machine-derived counts (§3.3): 9 + 11 + 20 = 40 unique.
- Source-of-truth hierarchy binding on all downstream commits (§6).
- Maintenance contract documented (§8).

Forbidden verdicts NOT emitted: all 8 in Charter §11.

---

End of A1B-AE.2 Taxonomy.
