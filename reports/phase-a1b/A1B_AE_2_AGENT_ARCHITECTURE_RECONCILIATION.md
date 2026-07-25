# A1B-AE.2 — Agent Architecture Reconciliation Report

**Charter**: A1B-AE.0 (v1.0, 2026-07-22)
**Worktree**: `E:/Corti4C-agent-expert`
**Branch**: `phase-a1b/agent-expert-clean-room`
**Generated**: 2026-07-22 (UTC)
**Companion documents**:
- [A1B_AE_2_TAXONOMY.md](A1B_AE_2_TAXONOMY.md) — 8-kind unified taxonomy
- `backend/agent_catalog/*.json` — machine-rebuildable canonical catalogs
- `scripts/a1b_ae_2_build_catalogs.py` — hermetic catalog generator

---

## §0. Executive summary

iCoDer currently has **5 parallel sources of truth for "what is an Agent"**:

| # | Source | Count | Files |
|---|---|---|---|
| A | Filesystem Packs (`agent_pack.json`) | 29 | `backend/official_agents/*/agent_pack.json` |
| B | Legacy Python code dirs (`__init__.py`) | 3 | `backend/official_agents/*/__init__.py` (only `code_validation`, `compliance_guardrail`, `note_completeness`) |
| C | seed.py PREBUILT_AGENTS | 16 | `backend/app/seed.py#L847-864` |
| D | Runtime registry | runtime-loaded | `icoder_runtime.core.registry` (installs from A) |
| E | Hub API surface | 27 visible | `backend/app/api/icoder_agents_hub.py` filters A |

The 5 sources have **3 disagreements** and **2 shadowings** (this report
enumerates them in §3..§10 below).

This commit (A1B-AE.2) does NOT yet resolve the disagreements. It only
**records them in machine-rebuildable form** (`backend/agent_catalog/*.json`)
and establishes the **canonical taxonomy** ([Taxonomy doc](A1B_AE_2_TAXONOMY.md)).

A1B-AE.3 (Expert Registry model + migration) and A1B-AE.4 (Agent CRUD +
alias resolver) are the commits that will actually mutate behaviour.
A1B-AE.9 (Tech debt liquidation) removes the 3 legacy Python orphans.

---

## §1. Machine-derived counts (no hardcoded numbers)

Re-run `python scripts/a1b_ae_2_build_catalogs.py` to regenerate. As of
A1B-AE.2 (baseline HEAD `3d50b11`, 2 commits layered):

```
pack_total              = 32
pack_runnable           = 2     (medical_coding, drg-analyzer)
pack_metadata_only      = 27
pack_legacy_orphan      = 3     (code_validation, compliance_guardrail, note_completeness)
pack_empty              = 0
dual_named_pairs        = 3     (the 3 legacy orphans above)
agent_total_canonical   = 29
expert_total            = 40
expert_corti_public     = 9     (clean-room copy of Corti public 9-key)
expert_icoder_internal  = 11
expert_pack_declared    = 20
seed_prebuilt_agents    = 16
```

These numbers are the **first iCoDer Agent counts that are reproducible
from a hermetic Python script reading the filesystem**. Prior counts
(11 / 14 / 16 / 23 / 29 in various prior audit reports) were sourced from
different subsets of the 5 sources above.

## §2. Why historical counts varied (11 / 14 / 16 / 23 / 29)

| Historical claim | Most-likely source | What it counted |
|---|---|---|
| **11** | `backend/app/agents/experts/*.py` | The 11 iCoDer internal Expert Python modules (NOT Agents). Conflated Experts with Agents. |
| **14** | Hub `/api/icoder/agents/hub` visible cards at an earlier date | A filtered subset of Pack cards (some Packs gained `hidden_from_hub=true` over time). |
| **16** | `seed.py#PREBUILT_AGENTS` list | The 16 DB-seeded Agents. This is the count most often quoted. |
| **23** | An intermediate count after the dash-form Packs were added | 16 seed + ~7 dash-form Packs that hadn't yet been aliased. |
| **29** | Full Pack scan including both halves of every dual-name pair | 32 Packs − 3 legacy orphans = 29. This is the post-alias canonical count. |

**Resolution**: A1B-AE.2 catalog builder produces **29 canonical Agents** by:
1. Listing all 32 Pack dirs.
2. Classifying 3 as LEGACY_CODE_ORPHAN (dedicated to A1B-AE.9 deletion).
3. Collapsing the 3 dual-name pairs (`code_validation` + `code-validation` → 1 canonical `code-validation`, etc.).
4. Adding 0 SEED_ONLY_NO_PACK entries (every seed.py row has a matching Pack).

This **29** is the binding canonical count until the filesystem changes.

## §3. Question 1 — Agent source of truth

**Question**: Which of {YAML, Python code, seed.py, DB, admin endpoint, runtime registry} is authoritative for "what Agents exist"?

**Answer (current, pre-A1B-AE.4)**:

There is **no single source of truth**. There are 5 parallel sources
(see §0 table). When they disagree, the de-facto resolution is:

| Consumer | Source it consults | File:line |
|---|---|---|
| Hub UI browse | Pack filesystem (filtered) | `backend/app/api/icoder_agents_hub.py:63-86` (`_load_packs`) |
| Run endpoint (legacy `/api/v1/agents/{id}/run`) | DB Agent table | `backend/app/api/agents.py:411-442` (`run_agent`) |
| Run endpoint (A2A `/api/runtime/agents/{ref}/run`) | Runtime registry | `backend/app/api/runtime_platform.py` |
| Agent Hub clone | DB Agent table (prebuilt filter) | `backend/app/api/icoder_agents_hub.py:387-396` (`_find_prebuilt_by_agent_id`) |
| Admin dashboard | DB Agent table | `backend/app/api/admin.py` |
| seed.py bootstrap | Pack-less; hardcoded Python dict | `backend/app/seed.py:847-864` |

**Target (A1B-AE.4 onwards)**: `backend/agent_catalog/agent_catalog.json`
is the **canonical source**. The catalog is regenerated from filesystem
Packs (the dominant source) + seed.py (the seed-completeness check).
All 5 consumers above are migrated in A1B-AE.4 to consult the catalog first
and fall back only for legacy compatibility.

## §4. Question 2 — Hub / A2A / clone / admin / runtime consistency

**Question**: For the same `agent_id`, do `/api/icoder/agents/hub`, `/api/runtime/agents/{ref}/run`, `/api/icoder/agents/{id}/clone`, `/api/admin/agents`, and the runtime registry all return the same Agent?

**Answer**: **NO** — they can disagree because they consult different sources.

Concrete example (the code-validation shadowing, see §5 below for full detail):

| Surface | What it returns for "code-validation" |
|---|---|
| `/hub` | The dash-form Pack (metadata-only, `@2.0.0`). |
| `/api/runtime/.../run` | Refuses (no runnable Python — the legacy `code_validation/agent.py` is NOT mounted in the runtime registry). |
| `/{id}/clone` | 404 — the DB Agent table has no row with `config.agent_ref == "icoder/code-validation-agent@2.0.0"` (seed.py only seeds 16 Agents; code-validation is seeded by key not by agent_ref). |
| `/api/admin/agents` | Returns whatever's in the DB. |
| Runtime registry | Empty (Pack not installed). |

**Target (A1B-AE.4)**: All 5 surfaces consult `agent_catalog.json` first.
The alias resolver (A1B-AE.4) translates `code_validation` ↔ `code-validation`
so the surfaces stop disagreeing.

## §5. Question 3 — Why historical counts varied (11/14/16/23/29)

See §2 above.

## §6. Question 4 — Version shadowing (`code-validation-agent@1.0.0` vs `@2.0.0`)

**Observation** (machine-derived, see `backend/agent_catalog/migrations.json`):

| Dir | Has | Version claim | Source |
|---|---|---|---|
| `backend/official_agents/code_validation/` | `__init__.py` + 4 `.py` files | `@1.0.0` | docstring in `__init__.py` |
| `backend/official_agents/code-validation/` | only `agent_pack.json` | `@2.0.0` | `agent_pack.json#agent_ref` |

This is the **textbook version-shadowing defect**:

- The legacy `@1.0.0` code_validation is what runtime Python imports do today
  (`from official_agents.code_validation import ...`).
- The metadata `@2.0.0` Pack is what the Hub UI displays.
- They disagree on version AND on whether the Agent is metadata-only vs runnable.

Two other pairs (`compliance_guardrail`/`compliance-guardrail` and
`note_completeness`/`note-completeness`) have **same version (`@1.0.0`)** on
both halves — they are dual-location defects but NOT version drift.
Still liquidated in A1B-AE.9 for taxonomy consistency.

**Resolution plan (binding)**:

- **A1B-AE.4** ships the alias resolver (`code_validation` → `code-validation`).
- **A1B-AE.9** deletes `code_validation/__init__.py` (and the 4 `.py` siblings)
  after the alias resolver has passed a full negative test cycle.
- The dash-form `code-validation@2.0.0` becomes the single canonical truth.
- If `code_validation@1.0.0`'s Python behaviour is still needed in A1B-AE.9,
  the Python files move INTO `code-validation/` first (preserving git history),
  then the legacy dir is deleted.

## §7. Question 5 — Why clone `medical-coding-agent` returned 404

**Reproduced from the clone code path** (`backend/app/api/icoder_agents_hub.py:417-458`):

```python
source = await _find_prebuilt_by_agent_id(db, agent_id)  # DB query
if not source:
    raise HTTPException(404, AGENT_NOT_FOUND, ...)
```

`_find_prebuilt_by_agent_id` iterates DB Agent rows where
`is_prebuilt == True` and matches `config.agent_ref` short form.
The Hub list endpoint (`/hub`) reads from the **Pack filesystem**.

**When the Pack filesystem has a Pack that the DB Agent table does not**,
browsing works (you see the card) but cloning fails (404). This is exactly
the bug observed with `medical-coding-agent` historically.

**Catalog cross-check** (machine-derived):

- 13 canonical Agents appear in Pack filesystem but NOT in seed.py (see §8 below).
- `medical-coding` is in that 13. Its Pack is `RUNNABLE_PACK` (has both `__init__.py` AND `agent_pack.json`).
- If seed.py has never been re-run since the Pack landed, the DB Agent table is missing it, and clone returns 404.

**Resolution plan (binding)**:

- **A1B-AE.4**: Clone endpoint consults `agent_catalog.json` first; if the
  Agent has a Pack but no DB row, it lazily seeds the DB row on first clone.
  This makes clone idempotent with respect to DB seed state.

## §8. Question 6 — Seed DB row shadowing of Pack-backed Agent

**Observation**: 13 canonical Agents have a Pack but NO seed.py row:

```
cdi-review
clinical-documentation-improvement-agent
code-reconciler
discharge-summary-structuring
documentation-gap
drg-analyzer
evidence-extractor
evidence-ranker
index-navigator
medcoder-coding-review
medical-coding                    ← the MVP runnable Pack!
principal-diagnosis-review
tabular-validator
```

Plus 16 Agents that have BOTH a Pack AND a seed.py row (the well-behaved
majority — see `seed_prebuilt_agents=16` in §1).

Plus 0 Agents with a seed.py row but no Pack (`SEED_ONLY_NO_PACK=0`).

**Implication**: The DB Agent table and the Pack filesystem are
**independently maintained**, with no automated check that they stay in sync.
`agent_registry_sync_service.py` reconciles the **runtime registry** with
the DB, but NOT the **Pack filesystem** with the DB.

**Resolution plan (binding)**:

- **A1B-AE.3** introduces a new model field `Agent.pack_dir` and a
  generation-time check that every Pack filesystem entry has a corresponding
  DB row (or is explicitly marked `hidden_from_hub=true`).
- **A1B-AE.9** ships a CI check (`scripts/a1b_ae_9_pack_db_sync_check.py`)
  that fails CI if `agent_catalog.json` and the DB Agent table disagree.

## §9. Question 7 — Agent Card field consistency

**Fields that should agree for a given Agent**:

| Field | Hub card source (`_build_card`) | DB Agent row source | Pack manifest source |
|---|---|---|---|
| `name` | `manifest.name` | `Agent.name` | `manifest.name` |
| `display_name` | `manifest.name` (alias) | (none) | `manifest.name` |
| `version` | `manifest.version` OR last `@x.y.z` from `agent_ref` | `Agent.version` (default `"1.0.0"`) | `manifest.version` |
| `category` | `manifest.category` | `Agent.category` | `manifest.category` |
| `icon` | `manifest.icon` | `Agent.icon` | `manifest.icon` |
| `description` | `manifest.description` | `Agent.description` | `manifest.description` |

When seed.py creates a DB Agent from `PREBUILT_AGENTS[key, name, desc, category, expert_name]`,
the `Agent.name` and `Agent.description` come from the seed dict, NOT from
the Pack. If the Pack and seed.py disagree, the Hub (which reads the Pack)
shows different text than the Agent Detail page (which reads the DB).

**Concrete observed case**: `note-completeness` Pack manifest name is
`"病历完整性智能体 (Note Completeness Agent)"` but seed.py#L857 has
`"病历完整性"`. Same Agent, two names.

**Resolution plan (binding)**:

- **A1B-AE.4**: Agent Detail page falls back to Pack manifest fields when
  DB row fields are empty; warns when they disagree.
- **A1B-AE.9**: seed.py is regenerated FROM `agent_catalog.json` (round-trip
  closes). After A1B-AE.9, editing seed.py by hand is forbidden — edits go
  into the Pack manifest and seed.py is regenerated.

## §10. Question 8 — Metadata-only Pack mislabeled as runnable

**Observation**: 27 of 32 Packs are `METADATA_ONLY_PACK` (no Python). Of
those 27, several have `manifest.maturity` values that imply runnability:

- 19 are `manifest.maturity = "metadata-only"` (consistent)
- 6 are `manifest.maturity = "mvp"` (drift — MVP implies runnable but there's no Python)
- 2 are `manifest.maturity = "stub"` (consistent — stubs)
- 0 are `manifest.maturity = "production-ready"` (good — none over-claim)

The 6 `mvp`-maturity-no-Python Packs are:
(re-run `python -c "import json; d=json.load(open('backend/agent_catalog/pack_catalog.json')); [print(e['dir_name'], e['manifest_maturity']) for e in d['entries'] if e['classification']=='METADATA_ONLY_PACK' and e['manifest_maturity']=='mvp']"` to list them.)

**Resolution plan (binding)**:

- **A1B-AE.4**: `_is_runnable()` in `icoder_agents_hub.py` is tightened to
  require BOTH `manifest.maturity in {mvp, runnable, production-ready}` AND
  `pack_catalog[dir].classification == RUNNABLE_PACK` (i.e. Python exists).
- **A1B-AE.9**: The 6 drift Packs are either downgraded to `metadata-only`
  OR their Python is added — no middle ground.

## §11. Question 9 — Expert stub in Agent Hub

**Observation**: Hub code (`icoder_agents_hub.py:101`) excludes
`agent_type in ("expert-stub", "internal_engine")` from listing. This was
the historical way to keep "Experts that are also Agents" out of the Hub.

**Current state**: 0 Packs have `agent_type=expert-stub` and 0 have
`agent_type=internal_engine` in the catalog. The filter is **vestigial**.

**Resolution plan**:

- **A1B-AE.4**: The filter is removed. With the new taxonomy
  ([Taxonomy §2](A1B_AE_2_TAXONOMY.md)), Experts are NEVER Agents and
  vice versa; the filter is unneeded.

## §12. Question 10 — MCP / A2A / Hub / Admin / Runtime consistency for same Agent ID

This is the same as Question 2 but scoped to a single Agent ID. See §4.

## §13. Catalog file format (binding on downstream commits)

Every catalog JSON file under `backend/agent_catalog/` follows:

```json
{
  "_summary": {
    "charter": "A1B-AE.2",
    "generated_by": "scripts/a1b_ae_2_build_catalogs.py",
    "clean_room_attested": true,
    "counts": { ... machine-derived ... },
    "classification_legend": { ... },
    "expert_origin_legend": { ... },
    "canonical_name_rule": "..."
  },
  "entries": [ ... ]
}
```

Downstream code MUST:
- read `_summary.counts` for totals (never compute its own count);
- read `entries[]` for per-record detail;
- treat unknown classification values as `UNKNOWN` (forward-compat);
- never write to these files by hand.

## §14. Acceptance conditions for A1B-AE.2

| # | Condition | Status |
|---|---|---|
| 1 | Catalog builder script committed | DONE (`scripts/a1b_ae_2_build_catalogs.py`) |
| 2 | 5 catalog JSON files committed | DONE (`backend/agent_catalog/*.json`) |
| 3 | Taxonomy document committed | DONE ([A1B_AE_2_TAXONOMY.md](A1B_AE_2_TAXONOMY.md)) |
| 4 | This reconciliation document committed | DONE |
| 5 | 10 §9 questions answered with file:line evidence | DONE (§3-§12) |
| 6 | No DB schema change | DONE (no migration added) |
| 7 | No runtime behaviour change | DONE (no `*.py` under `backend/app/` touched) |
| 8 | No frontend change | DONE |
| 9 | Clean-room attested (no Corti private assets) | DONE |
| 10 | Forbidden verdicts honoured | DONE (only `A1B_AE_2_..._ESTABLISHED` emitted) |

## §15. Carry-forward to A1B-AE.3..A1B-AE.9

Each downstream commit picks up specific items from this report:

| Commit | Picks up |
|---|---|
| A1B-AE.3 (Expert Registry model + alembic + API) | Expert catalog (40 entries) → DB table |
| A1B-AE.4 (Agent CRUD + Card + alias resolver) | §3, §4, §5, §6 (alias resolver), §7, §8, §10, §11 |
| A1B-AE.5 (Message → Task → Context + Memory Expert) | Experts: memory-expert, icoder-internal memory path |
| A1B-AE.6 (Calculator + PubMed + Clinical Trials) | Experts: medical-calculator-expert, pubmed-expert, clinical-trials-expert |
| A1B-AE.7 (Interviewing + Coding wrapper + external) | Experts: interviewing-expert, coding-expert, drugbank-expert, posos-expert, web-search-expert |
| A1B-AE.8 (5 Preset Agents) | 5 new canonical Agents tagged `origin=ICODER_CLEAN_ROOM` |
| A1B-AE.9 (Tech debt liquidation) | §6 (delete 3 legacy orphans), §8 (CI sync check), §10 (6 drift Packs) |
| A1B-AE.10 (10 headed-browser journeys) | Browse the catalog via UI |
| A1B-AE.11 (Final reconciliation + verdict) | Confirm all carry-forwards closed |

## §16. Verdict for A1B-AE.2

```
A1B_AE_2_AGENT_ARCHITECTURE_RECONCILED_AND_CATALOGED_FILED
```

**Filed** (not `VERIFIED`) because:
- Catalogs are descriptive (machine-derived); they do not yet bind the 5 sources.
- The 3 dual-name pairs are documented but not yet aliased in code.
- The 13 Pack-no-seed rows are documented but not yet reconciled in DB.
- The 6 maturity-drift Packs are documented but not yet downgraded/upgraded.

All binding resolutions land in A1B-AE.3..A1B-AE.9. A1B-AE.11 verifies they landed.

Forbidden verdicts NOT emitted: `PRODUCTION_READY`, `FULLY_VERIFIED`,
`PHI_BOUNDED`, `CORTI_PARITY_VERIFIED`, `PASS_A1A_GATE4_FINAL`,
`READY_FOR_HOSPITAL_DEPLOYMENT`, `CLINICAL_GRADE_VERIFIED`,
`CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED`.

---

End of A1B-AE.2 Architecture Reconciliation.
