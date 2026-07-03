# P1.1 — Agent Pack Standardization & Developer Experience Hardening — Baseline

**Date**: 2026-06-29
**Branch**: master
**Verdict target**: PASS only if all 14 success criteria (§10 of spec) met
**Status**: Read-only audit — no code changed.

---

## 0. Git & docs context

* Branch: `master`
* Working tree changes (uncommitted): 6 files modified, 12 files new
  (mostly P1.0 deliverables: `icoder_agents_hub.py`, `icoder_doctor.py`,
  `icoder_runs.py`, `icoder_doctor.py` script, 3 new tests, 2 new
  frontend pages, 2 new docs, `eval_e20_smoke.json`)
* Recent commits (top 10):
  1. `2e91333` feat(medcoder): E1.10 — faiss MMAP + BGE dtype key
  2. `df00b3c` feat(medcoder): E1.9 — BGE-M3 fp16 + Memory-Safe Load
  3. `019ee4d` docs(cloud): Group D flip language
  4. `97e1a25` feat(platform): Group C cloud-flip
  5. `5c17e3d` chore(cloud): Group B deployment artifact
  6. `1623bde` docs(cloud): Group A cloud-flip
  7. `3628870` chore(gitignore): exclude MedCodER eval ablation scratch
  8. `6d6071d` feat(medcoder): E1.8 — Stage 1 few-shot exemplars
  9. `570c049` fix(runtime): E1.1 — Real Boot Gate
  10. `8d5deb5` feat(medcoder): E1.7 — catalog-text scanner
* P1.0 report present: `docs/productization/P1_0_AGENT_RUNTIME_PRODUCTIZATION_REPORT.md` ✅
* P1.0 baseline present: `docs/productization/P1_0_BASELINE.md` ✅
* No `docs/specs/` directory exists (target for P1.1-A spec doc).

---

## 1. The 16 official agent packs

| # | dir | format | agent_type | agent_ref | manifest.name | tools | validator |
|---|-----|--------|-----------|-----------|---------------|-------|-----------|
| 1 | cdi-review | 1.1 | certified | `icoder/cdi-review@1.0.0` | 临床文书改进 | 6 | ✅ PASS |
| 2 | code-validation | 1.1 | certified | `icoder/code-validation@1.0.0` | 编码校验 | 5 | ✅ PASS |
| 3 | code_reconciler | 1.2 | expert-stub | `icoder/code-reconciler@1.0.0` | Code Reconciler | 5 | ❌ FAIL |
| 4 | compliance-guardrail | 1.1 | certified | `icoder/compliance-guardrail@1.0.0` | 合规护栏 | 5 | ✅ PASS |
| 5 | denial-appeals | 1.1 | certified | `icoder/denial-appeals@1.0.0` | 拒付申诉 | 6 | ✅ PASS |
| 6 | diagnosis-extractor | 1.1 | certified | `icoder/diagnosis-extractor@1.0.0` | 诊断提取 | 5 | ✅ PASS |
| 7 | documentation-gap | 1.1 | certified | `icoder/documentation-gap@1.0.0` | 文档缺口检测 | 6 | ✅ PASS |
| 8 | drg-analyzer | 1.1 | certified | `icoder/drg-analyzer@1.0.0` | DRG 分组分析 | 5 | ✅ PASS |
| 9 | evidence-ranker | 1.1 | certified | `icoder/evidence-ranker@1.0.0` | 证据排名 | 6 | ✅ PASS |
| 10 | evidence_extractor | 1.2 | expert-stub | `icoder/evidence-extractor@1.0.0` | Evidence Extractor | 2 | ❌ FAIL |
| 11 | index_navigator | 1.2 | expert-stub | `icoder/index-navigator@1.0.0` | Index Navigator | 3 | ❌ FAIL |
| 12 | medcoder-coding-review | 1.2 | reference | `icoder/medcoder-coding-review-agent@1.0.0` | MedCodER Coding Review Agent | 5 | ❌ FAIL |
| 13 | medical_coding | 1.2 | certified | `icoder/medical-coding-agent@2.0.0` | Medical Coding Agent | 5 | ❌ FAIL |
| 14 | note-completeness | 1.1 | certified | `icoder/note-completeness@1.0.0` | 病历完整性 | 6 | ✅ PASS |
| 15 | procedure-extractor | 1.1 | certified | `icoder/procedure-extractor@1.0.0` | 手术提取 | 5 | ✅ PASS |
| 16 | tabular_validator | 1.2 | expert-stub | `icoder/tabular-validator@1.0.0` | Tabular Validator | 4 | ❌ FAIL |

**Tally**: 16 discovered on disk · 10 v1.1 certified ✅ · 6 v1.2 (5 expert-stub + 1 reference + 1 v1.2/certified) ❌.

---

## 2. The 6 failing packs — root causes

Reproduced by mirroring `AgentPackageV1.from_dict` rules:

| pack | format_version | agent_type | primary failures |
|------|---------------|-----------|-----------------|
| **code_reconciler** | 1.2 | expert-stub | `format_version '1.2' unsupported (expected 1.1)`; `agent_type 'expert-stub' unsupported (expected certified/community)`; every tool `id missing`; every tool `tier must be 1 or 2, got None` |
| **evidence_extractor** | 1.2 | expert-stub | same set |
| **index_navigator** | 1.2 | expert-stub | same set |
| **medcoder-coding-review** | 1.2 | reference | same set (but `agent_type=reference` is the real blocker for "production_readiness" semantics) |
| **medical_coding** | 1.2 | certified | format_version drift; tools have no `tier` field (MCP-style refs) |
| **tabular_validator** | 1.2 | expert-stub | same set |

**Pattern**: the v1.2 packs use MCP-style `tools[].ref` (e.g. `app.icoder.mcp.server:/mcp/v1/tools/call/search_icd`) instead of v1.1's `tools[].tier` + `tools[].executor_file` model. The v1.1 validator was never updated to read MCP refs.

**Critical implication**: the **MedCodER Coding Review agent** itself is in the failure set. It IS the canonical reference implementation (real Python experts, real FAISS, real MCP) — it just can't be loaded by the v1.1 validator.

---

## 3. Two-layer registry: 10 in Hub ≠ 10 v1.1 packs

Audit of `RuntimeAgentRegistry` sources:

* **Source A — `BuiltinAgentPackProvider`** (loads `official_agents/*/agent_pack.json`):
  discovers 16, registers 10 (the 10 v1.1 certified), logs
  `Failed to register pack` warning for the other 6.
* **Source B — DB-backed `.icoder/agent_registry.json`** (10 Chinese-named
  agents, 编码校验/手术提取/…): separate store, populated at first boot.

The Hub `/api/icoder/agents` returns **10 agents** (the Chinese-named
DB-backed ones). The 10 v1.1 certified packs that BuiltinAgentPackProvider
registers may or may not be the same as the DB-backed 10 — there is no
guarantee they refer to the same executions. **This needs disambiguation
in P1.1.**

---

## 4. Agent Hub raw-pack bypass (P1.0 debt)

`backend/app/api/icoder_agents_hub.py:107-121` (`_agent_summary`) and
`226-288` (`get_agent_card`) both bypass `AgentPackageV1.from_dict()` and
read `rec.pack_data` directly. The docstrings even call this out:

> Discovery surface reads `rec.pack_data` directly so marketplace-
> discoverable agents always have a card, even pre-A2A Discovery
> completion.

**Risk**:
* Two Agent Pack standards will drift: Runtime's v1.1 validator vs
  Hub's raw-pack view.
* Newly-added fields (e.g. `recorder_required`, `human_review_required_when`)
  will be silently ignored by the Hub.
* Tier computation (`_tier_from_raw_pack`) is a re-implementation of
  `AgentPackageV1.security_tier` — two implementations of the same logic
  will diverge.

**Fix path (P1.1-A + P1.1-C)**: bring raw-pack reading inside a
normalized `AgentPackLoader` that knows v1.1 AND v1.2. Hub reads the
normalized view, never raw `pack_data`.

---

## 5. Doctor (P1.0-C) coverage of pack compatibility

Current doctor has 20 checks. None of them directly answer
"is this pack v1.1 vs v1.2 compatible?" The relevant checks:

* `#09 agent_pack_files_present` — files exist + valid JSON
  (catches missing/malformed packs)
* `#10 agent_pack_required_fields` — raw-pack field shape
  (catches missing manifest/system_prompt/requirements)
* `#12 mcp_tool_registry_matches_pack` — TOOL_REGISTRY ⊆ medcoder pack
  (catches missing tool implementations)

**Gaps**:
* No check that distinguishes v1.1 vs v1.2 packs.
* No count of `discovered` vs `registered` vs `executable`.
* No check that MedCodER (the canonical reference agent) is in the
  executable set.
* No per-pack "why not executable" output.

---

## 6. Run Trace (P1.0-E) — reads wrong store

Two persistence stores exist for run history:

* **`/api/icoder/runs`** (P1.0-E): reads `app.state.run_history`
  → backed by `backend/.icoder/run_history.jsonl` → **file does not
  exist** (zero bytes; legacy RunHistoryStore is wired but no agent
  writes to it in current code path). The endpoint returns
  `{runs: [], total: 0, history_available: true}`.
* **`/api/m2a/runs`** (existing): reads `_run_trace.list_production()`
  → backed by `backend/.icoder/m2a/production_runs.jsonl` → **1799 real
  MedCodER production runs already on disk** with full
  expert/stage/tool-call structure.

**P1.0-E shipped the wrong alias.** Run Trace in P1.1-F must either:
1. Re-alias `/api/icoder/runs` to the m2a store, OR
2. Add a second alias to the m2a store with a different prefix
   (e.g. `/api/icoder/runs/medcoder`), AND/OR
3. Backfill run_history.jsonl from production_runs.jsonl (read-only projection)

Per P1.1 spec §6, option (1) is the right answer for "no fake data".
P1.1-F will:

* Make `/api/icoder/runs` return the **m2a production trace** by default
  (real expert / tool_call / stage data), with the legacy RunHistoryStore
  available as a fallback.
* Surface tool_call count, expert timeline, degraded flag, error_code.
* Provide `backend/scripts/run_medcoder_smoke.py` to deterministically
  generate one real MedCodER run on demand.

---

## 7. CLI inventory

Existing scripts under `backend/scripts/`:

| script | purpose | belongs to |
|--------|---------|-----------|
| `analyze_retrieval.py` | retrieval diagnostics | MedCodER |
| `build_icoder_201_fixture.py` | build icoder_201 gold | MedCodER eval |
| `build_medcoder_icd9cm3_index.py` | build FAISS index | MedCodER |
| `build_medcoder_index.py` | build FAISS index | MedCodER |
| `combine_medcoder_reports.py` | report aggregation | MedCodER eval |
| `download_bge_m3.py` | model download | MedCodER |
| `e2e_medcoder_validation.py` | e2e F1 eval | MedCodER eval |
| `e2e_runtime_validation.py` | e2e runtime | Runtime |
| `icoder_doctor.py` | P1.0-C doctor | Runtime DX |
| `pilot_eval_runbook.py` | pilot eval | MedCodER eval |
| `validate_kb_schema.py` | KB validation | MedCodER eval |

**No agent-related CLI exists** — no `validate_agent_pack.py`, no
`icoder_agent.py`, no `init_agent.py`. P1.1-E will add
`backend/scripts/icoder_agent.py` with subcommands: `list` /
`inspect` / `validate` / `init` / `doctor-summary`.

---

## 8. Files in scope for P1.1

### 8.1 To create (P1.1-A — Spec + Loader)

```
backend/icoder_runtime/core/agent_pack_schema.py     # normalized model
backend/icoder_runtime/core/agent_pack_loader.py     # v1.1 + v1.2 loader
backend/tests/unit/icoder_runtime/test_agent_pack_loader.py  # 25+ tests
docs/specs/AGENT_PACK_SPEC_V1_2.md                   # v1.1 vs v1.2 spec
```

### 8.2 To create (P1.1-B — Registry compat)

```
backend/icoder_runtime/core/registry_status.py        # AgentCompatibilityReport
backend/icoder_runtime/core/builtin_pack_provider.py  # MODIFIED: use Loader
backend/tests/unit/icoder_runtime/test_registry_compat.py  # 30+ tests
```

### 8.3 To create (P1.1-C — Hub enhancement)

```
backend/app/api/icoder_agents_hub.py                  # MODIFIED: use Loader
backend/app/api/icoder_agents_compat.py              # NEW: /{agent_id}/validation, /{agent_id}/compatibility
frontend/src/services/agentHubApi.ts                 # MODIFIED: types
frontend/src/pages/AgentHubPage.tsx                  # MODIFIED: status badge, Why-not-executable
frontend/src/components/agent/StatusBadge.tsx        # NEW
frontend/src/components/agent/ValidationPanel.tsx    # NEW
backend/tests/unit/app/api/test_icoder_agents_compat.py  # NEW
```

### 8.4 To create (P1.1-D — Doctor expansion)

```
backend/scripts/icoder_doctor.py                     # MODIFIED: 6 new checks
backend/tests/unit/scripts/test_icoder_doctor.py     # MODIFIED: 12+ new tests
```

### 8.5 To create (P1.1-E — Agent CLI)

```
backend/scripts/icoder_agent.py                      # NEW: list/inspect/validate/init
backend/tests/unit/scripts/test_icoder_agent.py       # NEW
docs/agents/AGENT_AUTHORING.md                       # NEW: how to author
```

### 8.6 To create (P1.1-F — Run Trace real)

```
backend/app/api/icoder_runs.py                       # MODIFIED: dual-source
backend/scripts/run_medcoder_smoke.py                # NEW: deterministic real run
backend/tests/unit/app/api/test_icoder_runs.py       # MODIFIED: smoke
frontend/src/pages/RunTracePage.tsx                  # MODIFIED: expert timeline
```

### 8.7 To create (P1.1-G — Cross-link)

```
frontend/src/components/agent/AgentLinkGroup.tsx     # NEW: View Runs / Doctor / Validate
frontend/src/components/agent/WhyNotExecutable.tsx    # NEW
frontend/src/pages/AgentHubPage.tsx                  # MODIFIED
frontend/src/pages/RunTracePage.tsx                  # MODIFIED
frontend/src/pages/DoctorReportPage.tsx              # MODIFIED
```

### 8.8 To create (Report)

```
docs/productization/P1_1_AGENT_PACK_DX_HARDENING_REPORT.md
```

### 8.9 To NOT touch (non-goals)

```
backend/icoder_runtime/providers/medical_coding/medcoder_adapter.py  (no Stage 4 changes)
backend/scripts/build_medcoder_*.py                                  (no index changes)
backend/data/medcoder/                                               (no eval changes)
backend/icoder_runtime/m2a/                                          (M2a recorder is fine, just re-alias)
```

---

## 9. Risks & open questions

1. **DB-backed registry overlap**: the 10 Chinese-named agents in
   `.icoder/agent_registry.json` may overlap with the 10 v1.1 packs.
   P1.1-B should keep both sources but mark DB-backed entries clearly
   (e.g. `source=db` vs `source=builtin_pack`).
2. **m2a re-alias breakage**: changing `/api/icoder/runs` to return
   m2a data could break any frontend consumer expecting the legacy
   RunHistoryStore shape. P1.1-F will keep the legacy shape on a new
   path (`/api/icoder/runs/legacy`) and put m2a on the default.
3. **6 v1.2 packs re-classification**: per the spec rule "no fake
   status", `expert-stub` packs (4 of the 6) should be marked
   `metadata_only` not `executable` until they have real handlers wired
   in `official_agents/<name>/`. P1.1-B will surface this honestly.
4. **No UI for editing packs**: P1.1 stays CLI-driven; Marketplace /
   visual editor explicitly excluded by spec.
5. **Existing tests that use `AgentPackageV1.from_dict` directly**:
   must be updated to use the new `AgentPackLoader` if the new loader
   becomes the SSOT. P1.1-A will keep the old validator intact and
   deprecate it gradually.

---

## 10. Verification target (success criteria checklist)

| # | criterion | status (baseline) |
|---|-----------|-------------------|
| 1 | 16 packs discoverable | ✅ (filesystem) / ❌ (Hub shows 10) |
| 2 | each pack has clear status | ❌ (only 10 in Hub) |
| 3 | failure reasons visible | ❌ (logs only, not surfaced) |
| 4 | MedCodER executable | ❌ (currently in failure set) |
| 5 | metadata-only ≠ executable | ❌ (no distinction today) |
| 6 | Hub stops using raw-pack bypass | ❌ (still in P1.0-B code) |
| 7 | doctor has pack compat summary | ❌ (no per-pack check) |
| 8 | CLI list/inspect/validate/init | ❌ (no agent CLI today) |
| 9 | Run Trace shows real MedCodER run | ❌ (wrong store aliased) |
| 10 | Hub/Doctor/Runs nav closed loop | partial (Hub→Runs works; Runs→Hub, Doctor→Hub, Doctor→Runs not wired) |
| 11 | backend + frontend tests pass | ✅ (978/978 backend, 0 TS errors) |
| 12 | no coding-quality logic | ✅ (none touched) |
| 13 | no fake data | ✅ (all P1.0 endpoints honest) |
| 14 | no experimental/metadata-only marked production-ready | ❌ (currently no distinction) |

**0 of 14 success criteria met at baseline.** P1.1 must close all 14.

---

## 11. P1.1 work plan (per spec sections)

1. **P1.1-A** — AgentPackLoader (v1.1 + v1.2) + normalized model + spec doc
2. **P1.1-B** — 6 failing packs re-classified; Hub/Registry both use Loader
3. **P1.1-C** — Agent Hub: status badge + Why-not-executable + Compatibility panel
4. **P1.1-D** — Doctor: 6 new pack-compat checks (per-pack status count)
5. **P1.1-E** — `icoder_agent.py` CLI: list / inspect / validate / init
6. **P1.1-F** — Run Trace re-aliased to m2a store + smoke script
7. **P1.1-G** — Cross-link Agent Hub ↔ Doctor ↔ Runs ↔ Coding
8. **3 testing rounds** + report
