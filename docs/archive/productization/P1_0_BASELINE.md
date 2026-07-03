# P1.0 Baseline — Agent Runtime Productization Foundation

Read-only audit preceding P1.0 implementation. No code changes.

Branch: `master` · Head: `2e91333` · Date: 2026-06-28

---

## 0. Git state

- Branch: `master`, ahead of `origin/master` by 1 commit (E1.10 — `2e91333`)
- Working tree: clean except untracked `backend/data/medcoder/eval_e20_smoke.json` (E2.0 5-case output)

Last 10 commits:

```
2e91333 feat(medcoder): E1.10 — faiss MMAP + BGE dtype key for Windows OOM
df00b3c feat(medcoder): E1.9 — BGE-M3 fp16 + Memory-Safe Load
019ee4d docs(cloud): Group D flip language — flip 13 docs + delete HOSPITAL_DATA_REQUEST
97e1a25 feat(platform): Group C cloud-flip — 3 platform API stub + regions.yaml
5c17e3d chore(cloud): Group B deployment artifact — flip docker-compose to local-dev
1623bde docs(cloud): Group A cloud-flip — 4 篇 cloud 架构 doc + .env.cloud.example
3628870 chore(gitignore): exclude MedCodER eval ablation scratch
6d6071d feat(medcoder): E1.8 — Stage 1 few-shot exemplars for procedure extraction
570c049 fix(runtime): E1.1 — Real Boot Gate + AGENT_NOT_FOUND + Stage2Result envelope
8d5deb5 feat(medcoder): E1.7 — catalog-text scanner for procedure mentions
```

Required artifacts:
- `docs/audit_remediation/E1_1_REAL_BOOT_GATE_REPORT.md` — **PRESENT** (E1.1)
- `2e91333 feat(medcoder): E1.10 — faiss MMAP + BGE dtype key for Windows OOM` — **PRESENT**

---

## 1. E1.8 few-shot — current default state

**Finding:** E1.8 few-shot is **HARD-ENABLED in product default path**. No feature flag.

- `backend/icoder_runtime/providers/medical_coding/medcoder_adapter.py:113-125`
  ```python
  def build_extraction_messages(emr_text: str) -> list[dict[str, str]]:
      messages: list[dict[str, str]] = [
          {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
          *_EXTRACTION_FEW_SHOT,   # ← always injected
          {"role": "user", "content": emr_text},
      ]
      return messages
  ```
- `_EXTRACTION_FEW_SHOT` is a module-level constant (3 exemplars, lines 51-110) — always loaded into prompt.
- All 5 MedCodER call sites use `build_extraction_messages`: hybrid_adapter, medcoder_strategy, e2e_medcoder_validation, runtime_platform's medical-coding/test endpoint, test_medcoder_adapter.

**P1.0-A action:** Add `ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT` env var, default `false`. Gate inside `build_extraction_messages`. No deletion of `_EXTRACTION_FEW_SHOT`.

---

## 2. E2.0 experimental code locations

- `backend/data/medcoder/eval_e20_smoke.json` — 5-case full variant output (untracked).
- `backend/data/medcoder/eval_e20_smoke.log` — companion log (if written).
- `backend/scripts/e2e_medcoder_validation.py` — eval driver (UNCHANGED in this round; do not modify).
- `backend/data/medcoder/e2e_regression_check.json` — pre-E1.8 baseline, 5 cases, F1@1=0.15.

**P1.0-A action:** Archive `eval_e20_smoke.json` + write `docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md`. Do NOT commit the json into `data/medcoder/` (eval scratch is already gitignored).

---

## 3. Stage 4 rerank — read-only acknowledgment (NOT to modify)

- `build_rerank_messages` in `medcoder_adapter.py:180+` — Stage 4 RankGPT prompt builder.
- `app/icoder/mcp/handlers/rerank_codes.py` — MCP tool handler for Stage 4.
- `TOOL_REGISTRY["rerank_codes"]` in `app/icoder/mcp/tool_registry.py:207-214`.
- `official_agents/medcoder-coding-review/agent_pack.json::tools[].ref` points to MCP rerank_codes handler.

**P1.0 NO-OP:** Do not edit any of the above. Do not add CoT few-shot to rerank. Out of scope per P1.0 non-goals.

---

## 4. Agent management capabilities — current state

### 4.1 Backend — already substantial

| Path | Status | Notes |
|------|--------|-------|
| `/api/runtime-platform/agents` (legacy prefix) | ✅ | `runtime_platform.py:241` — list agents in registry |
| `/api/runtime-platform/agents/{ref}/lifecycle` | ✅ | enable/disable/uninstall/rollback |
| `/api/runtime-platform/agents/{ref}/run` | ✅ | run agent via canonical ref |
| `/api/runtime-platform/registry/health` | ✅ | DB ↔ registry consistency check |
| `/api/runtime-platform/registry/repair` | ✅ | repair direction |
| `/api/runtime/agents` | ✅ | Standard prefix alias |
| `/api/runtime/agents/{ref}/lifecycle` | ✅ | alias |
| `/api/runtime/agents/{ref}/run` | ✅ | alias |
| `/api/runtime/evaluation/run-single` | ✅ | eval smoke (dev) |
| `/api/agents` (DB-backed CRUD) | ✅ | `agents.py` — prebuilt + custom |
| `/api/agents/{id}` | ✅ | get/update/delete |
| `/api/agents/{id}/run`, `/{id}/stream` | ✅ | legacy execution path |
| `/api/agents/templates` | ✅ | 20 hardcoded iCoDer templates |
| `/api/agents/{id}/threads*` | ✅ | thread state |

### 4.2 A2A Discovery — partial

- `app/icoder/agent_runtime/a2a/routes_discovery.py` — A2A endpoints for `.well-known/agent.json` etc.
- `app/icoder/agent_runtime/a2a/agent_card.py` — Agent Card factory `medcoder_coding_review_card()`.
- `agent_pack.json::tools[].ref` — already points to MCP handlers (M2).
- `tests/unit/icoder/a2a/test_agent_card_medcoder.py` — 9 unit tests covering card factory.

### 4.3 P1.0-B gap

User spec asks for 4 endpoints under `/api/icoder/agents/*`:
- `GET /api/icoder/agents` — already covered by `/api/runtime/agents`. **Add thin alias** (or document the mapping).
- `GET /api/icoder/agents/{agent_id}/card` — A2A agent card. **Add thin alias** mapping to existing A2A discovery.
- `GET /api/icoder/agents/{agent_id}/health` — **NEW** per-agent health (index + recorder + model load).
- `GET /api/icoder/agents/{agent_id}/requirements` — **NEW** per-agent requirements (assets, models, MCP tools, env vars, permissions).

### 4.4 Frontend — partial

Existing pages:
- `frontend/src/pages/AgentsPage.tsx` — Agent Hub-like listing.
- `frontend/src/pages/AgentDetailPage.tsx` — Detail view.
- `frontend/src/pages/NewAgentPage.tsx` — Custom agent creation.
- `frontend/src/pages/AIStudioOverviewPage.tsx` — Studio entry.

Routes (App.tsx):
- `/ai-studio/agents`, `/ai-studio/agents/new`, `/ai-studio/agents/:agentId`
- `/studio/agents*` — duplicate of above

**P1.0-F action:** Add `/runtime/agent-hub` route (Agent Hub product surface) and `/runtime/doctor` (doctor report). Keep `/ai-studio/agents` working for AI Studio flow.

---

## 5. Agent Pack validator — current state

- **No dedicated validator module.** Existing checks scattered:
  - `tests/unit/icoder/agent_pack/test_e1_alignment.py` — E1 pack alignment tests (73 tests).
  - `app/icoder/mcp/server.py::assert_tool_registry_matches_agent_pack` — boot-time tool name match.
  - `icoder_runtime/core/agent_pack_v1.py` — `AgentPackageV1.from_dict()` — schema validation only.
  - `tests/unit/icoder/a2a/test_agent_card.py`, `test_agent_card_medcoder.py` — agent card factory.

- **5 official agent packs** in `backend/official_agents/`:
  - `medcoder-coding-review/agent_pack.json` (M2 — uses MCP tools ref)
  - `medical_coding/agent_pack.json` (legacy)
  - `evidence_extractor/`, `index_navigator/`, `tabular_validator/`, `code_reconciler/` (D2 stubs)

**P1.0-C action:** Add `backend/scripts/icoder_doctor.py` with 20 checks (see spec). All 5 packs must pass validator.

---

## 6. doctor / health / startup check — current state

- `app/main.py::health_check` (line 747) — basic `/api/health`.
- `app/api/runtime_platform.py::runtime_status` — PlatformRuntime status.
- `app/services/medcoder_index_health.py::index_health_check` — FAISS index health (E1.10).
- E1.1 lifespan check — verified `agent_registry` loads, MCP middleware mounted after lifespan, A2A returns AGENT_NOT_FOUND.

**P1.0-C action:** Add `icoder_doctor.py` that aggregates: python version, FastAPI/Starlette version (MUST be 0.38.x compatible — known issue from Phase B tech debt), uvicorn boot, `/api/health`, registry load, agent pack presence + validator pass, MCP tools/list, FAISS index, BGE model cache, MMAP flag, LLM provider, run_trace path writability, `.icoder` gitignore status, E1.8 few-shot flag default.

---

## 7. run_trace / observability — current state

### 7.1 Backend — already substantial

| Path | Status | Notes |
|------|--------|-------|
| `app.state.run_history` | ✅ | `RunHistoryStore` (line 207-220 main.py) |
| `app.state.fallback_tracker` | ✅ | line 221 |
| `app.state.shadow_diff_service` | ✅ | line 222 |
| `app.state.runtime_audit_logger` | ✅ | line 223 |
| `app.state.m2a_recorder` | ✅ | line 666 — wired into Runtime |
| `/api/runtime/runs` | ✅ | list runs (filter by agent_ref) |
| `/api/runtime/runs/{run_id}` | ✅ | get one run |
| `/api/runtime/observability/fallback` | ✅ | fallback stats |
| `/api/runtime/observability/shadow` | ✅ | shadow diff stats |
| `/api/runtime/audit-log` | ✅ | audit events |
| `/api/m2a/runs` POST | ✅ | start a run (M2a) |
| `/api/m2a/runs/{id}` GET | ✅ | get trace |
| `/api/m2a/runs/{id}/finalize` POST | ✅ | finalize |
| `/api/m2a/runs/{id}/human-review` POST | ✅ | human review |
| `/api/m2a/runs/{id}/reviews` GET | ✅ | list reviews |
| `/api/m2a/learning-loop` GET | ✅ | learning stats |

### 7.2 Frontend

- `frontend/src/pages/RuntimeConsolePage.tsx` — generic Runtime console.
- `frontend/src/services/runtimeApi.ts` — runtime client.

**P1.0-E action:** Wire `/api/icoder/runs*` thin aliases (already exist as `/api/runtime/runs*`). Build a focused Run Trace page that explicitly shows "no trace available" when recorder is inactive. Do NOT fabricate fake traces. If M2a is not yet auto-wired into MedCodER `infer_async`, document that gap as a follow-up.

---

## 8. Frontend navigation — current state

- 64 routes total in `App.tsx`.
- `/runtime/*` namespace exists for runtime product surface.
- `/ai-studio/*` namespace for AI Studio flows.
- `/studio/*` duplicate of `/ai-studio/*` (legacy).
- `/studio/agents/homepage-coding-review` already redirects to `/runtime/coding-review` (homepage shim from M2d/D3).
- No `Agent Hub` or `Doctor Report` product entry yet.

**P1.0-F action:**
- Add `/runtime/agent-hub` → Agent Hub page (uses `/api/icoder/agents*`).
- Add `/runtime/doctor` → Doctor Report page (renders `icoder_doctor.py --json`).
- Add `/runtime/runs` → Run Trace list page.
- Verify `homepage-coding-review` stays as a redirect shim (no new primary surface).
- Verify MedCodER page (`/runtime/coding-review` or `/ai-studio/medical-coding`) keeps working.

---

## 9. Files in scope for P1.0 (predicted)

### New files
- `backend/scripts/icoder_doctor.py`
- `backend/app/api/icoder_agents_hub.py` (or extend `runtime_platform.py`)
- `frontend/src/pages/AgentHubPage.tsx`
- `frontend/src/pages/DoctorReportPage.tsx`
- `frontend/src/pages/RunTracePage.tsx`
- `frontend/src/services/agentHubApi.ts`
- `docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md`
- `docs/backlog/CODING_QUALITY_BACKLOG.md`
- `docs/productization/P1_0_AGENT_RUNTIME_PRODUCTIZATION_REPORT.md`

### Modified files (predicted)
- `backend/icoder_runtime/providers/medical_coding/medcoder_adapter.py` — add few-shot flag gate (≤10 LOC).
- `backend/app/main.py` — minor lifespan init for new singletons (no behavioral change).
- `frontend/src/App.tsx` — add 3 routes.
- `frontend/src/components/Sidebar.tsx` (or equivalent) — add nav entries.
- `.env.example` — add `ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT=false`.

### Untouched
- Stage 4 rerank (`medcoder_adapter.py::build_rerank_messages`, `app/icoder/mcp/handlers/rerank_codes.py`).
- `_EXTRACTION_FEW_SHOT` content (kept for opt-in re-enable).
- `e2e_medcoder_validation.py`.
- Existing `/api/runtime/*`, `/api/agents/*`, `/api/m2a/*` endpoints.

---

## 10. Verification target

After implementation, all 3 rounds must pass:

Round 1 (backend):
- `python -c "from icoder_runtime.providers.medical_coding.medcoder_adapter import build_extraction_messages; m = build_extraction_messages('x'); print(len(m))"` → 2 (system + user, no few-shot) when flag off; 5 when flag on.
- `python scripts/icoder_doctor.py` exits 0; missing FAISS or BGE → WARN/FAIL not silent OK.
- `python -m pytest backend/tests/unit -q` → all green.

Round 2 (e2e API):
- uvicorn boots.
- `GET /api/health` → 200.
- `GET /api/icoder/agents` → 200 with at least 1 agent.
- `GET /api/icoder/agents/icoder%2Fmedical-coding-agent%401.0.0/card` → 200.
- `GET /api/icoder/agents/.../health` → 200.
- `GET /api/icoder/agents/.../requirements` → 200.
- `GET /mcp/v1/tools/list` → 200 with 5 tools.
- unknown agent → `AGENT_NOT_FOUND` (404, not 500).
- `python scripts/icoder_doctor.py --json` → valid JSON with `product_readiness_summary`.

Round 3 (frontend):
- `npm run typecheck` → 0 errors.
- `npm run build` → success.
- Routes compile: `/runtime/agent-hub`, `/runtime/doctor`, `/runtime/runs`.
- MedCodER page still accessible.
- `homepage-coding-review` not in primary nav.

---

## 11. Risks flagged before implementation

1. **Starlette 0.38.x compatibility** — Phase B tech debt memory noted fastapi 0.115 + starlette 1.3.1 incompatibility with on_startup; doctor must FAIL if Starlette version is wrong.
2. **Windows OOM regression risk** — E1.10 fix is committed; doctor must verify faiss IO_FLAG_MMAP is actually used (grep for `IO_FLAG_MMAP` in retrievers).
3. **recorder trace gap** — MedCodER `infer_async` may not yet wire `app.state.m2a_recorder` into every code path. P1.0-E must show real or "no trace available", never fake.
4. **Few-shot gate** — must be ONE line change in `build_extraction_messages` (skip `_EXTRACTION_FEW_SHOT` when env false); over-gating risks breaking non-MedCodER callers.
5. **Eval scratch** — `eval_e20_smoke.json` is gitignored (`.gitignore` excludes medcoder eval ablation). Do not commit.

---

End of baseline.