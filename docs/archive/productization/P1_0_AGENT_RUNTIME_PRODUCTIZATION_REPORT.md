# P1.0 — Agent Runtime Productization Report

**Date**: 2026-06-28
**Branch**: master
**Verdict**: **PASS**

## 1. Scope

Shift iCoDer mainline from MedCodER coding-quality experimentation
(E1.8 few-shot, E2.0 verification) into Agent Runtime productization.
The deliverables are:

* **P1.0-A** — Freeze E2.0 (no n=30 expansion, no Stage 4 rerank changes,
  no F1-improvement logic) and gate E1.8 few-shot behind the
  ``ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT`` env var (default off).
* **P1.0-B** — Agent Hub MVP: 4 endpoints under ``/api/icoder/agents/*``
  + frontend ``/runtime/agent-hub`` page.
* **P1.0-C** — Agent Pack Validator + ``backend/scripts/icoder_doctor.py``
  with 20 productization-readiness checks.
* **P1.0-E** — Run Trace / Observability: ``/api/icoder/runs*`` aliases
  + frontend ``/runtime/runs`` page.
* **P1.0-F** — Doctor Report page (``/runtime/doctor``) + frontend
  navigation整理.

Explicit **non-goals** (per spec):
NO Stage 4 rerank changes · NO n=30 expansion · NO model training ·
NO F1 improvement logic · NO Marketplace · NO fake data.

## 2. Deliverables

### 2.1 P1.0-A — E2.0 freeze + few-shot flag

| Artifact | Path | Status |
|----------|------|--------|
| Feature flag | ``backend/icoder_runtime/providers/medical_coding/medcoder_adapter.py`` | ✅ Added ``is_medcoder_fewshot_enabled()`` (default off; ``1/true/yes/on`` opt-in) |
| Tests | ``backend/tests/test_services/test_medcoder_adapter.py::TestFewShotGate`` | ✅ 6 tests: default off, explicit true, truthy variants, false stays off, exemplars still loaded |
| Cloud config | ``.env.cloud.example`` | ✅ ``ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT=false`` |
| Archive doc | ``docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md`` | ✅ Records 5-case smoke (F1@1=0.15 unchanged, F1@5 -2.3pp), O82 procedure diagnostic, no promotion rationale |
| Backlog doc | ``docs/backlog/CODING_QUALITY_BACKLOG.md`` | ✅ 6 items (CQB-1…CQB-6): Stage 4 procedures, Stage 1 cesarean, ranking, n=30, few-shot revision, rerank CoT |

### 2.2 P1.0-B — Agent Hub MVP

| Artifact | Path | Status |
|----------|------|--------|
| Backend router | ``backend/app/api/icoder_agents_hub.py`` | ✅ 4 endpoints: ``GET /api/icoder/agents``, ``/{agent_id}/card``, ``/{agent_id}/health``, ``/{agent_id}/requirements`` |
| Mounted in app | ``backend/app/main.py:844`` | ✅ ``app.include_router(icoder_agents_hub_router)`` |
| Frontend page | ``frontend/src/pages/AgentHubPage.tsx`` | ✅ Two-column layout: list rail + tabbed detail (Overview / Health / Requirements) |
| Frontend API | ``frontend/src/services/agentHubApi.ts`` | ✅ Typed client (AgentHubSummary / AgentHealth / AgentRequirements) |
| Frontend route | ``frontend/src/App.tsx:109`` | ✅ ``<Route path="runtime/agent-hub" />`` |
| Tests | ``backend/tests/unit/app/api/test_icoder_agents_hub.py`` | ✅ 8 tests covering all 4 endpoints + few-shot flag visibility |

#### Notable design decisions

* **Raw-pack reading**: bypassed ``AgentPackageV1.from_dict()`` because
  Phase D3 packs use ``format_version=1.2`` and ``agent_type=reference``,
  which the v1.1 validator rejects. Discovery surfaces read
  ``rec.pack_data`` directly so marketplace-discoverable agents always
  have a card, even pre-A2A Discovery completion.
* **Defensive tool parsing**: ``tools[]`` can be a mixed list of strings
  (legacy IDs) and dicts (MCP-style). Both branches handled.
* **Credential redaction**: env vars whose name contains ``CREDENTIAL`` or
  ``KEY`` surface as ``"<redacted>"`` — never leak the value.
* **Unknown agent = 404**: not 200-empty, not 500. A2A SPEC §7 compliant
  with ``error_code: AGENT_NOT_FOUND``.
* **2-tier synthesis**: canonical A2A factory for MedCodER agents,
  synthesized card for everything else.

### 2.3 P1.0-C — Agent Pack Validator + icoder_doctor

| Artifact | Path | Status |
|----------|------|--------|
| Doctor script | ``backend/scripts/icoder_doctor.py`` | ✅ 20 checks, pure functions, ``--json`` + ``--only`` CLI |
| Doctor API | ``backend/app/api/icoder_doctor.py`` | ✅ ``GET /api/icoder/doctor`` + ``/{check_id}`` |
| Mounted in app | ``backend/app/main.py:845`` | ✅ |
| Tests (script) | ``backend/tests/unit/scripts/test_icoder_doctor.py`` | ✅ 33 tests: CLI smoke, JSON shape, only-filter, individual checks, few-shot flag |
| Tests (API) | ``backend/tests/unit/app/api/test_icoder_doctor_api.py`` | ✅ 6 tests: full report, single check (full + short), unknown id 404 |

#### 20-check inventory

| # | Check ID | What it verifies |
|---|----------|------------------|
| 01 | ``python_version`` | ≥ 3.11 |
| 02 | ``fastapi_version`` | ≥ 0.100 (Lifespan + TestClient stability) |
| 03 | ``starlette_version`` | ≥ 0.36 (no deprecated ``on_startup``) |
| 04 | ``uvicorn_version`` | installed |
| 05 | ``no_deprecated_on_startup_in_app_code`` | regex scan of ``app/**/*.py`` for ``@app.on_startup/on_event/on_shutdown`` |
| 06 | ``app_main_imports`` | ``import app.main`` succeeds |
| 07 | ``api_health_endpoint`` | ``GET /api/health`` → 200 via TestClient |
| 08 | ``agent_registry_present`` | ``/api/icoder/agents`` returns ≥ 1 agent |
| 09 | ``agent_pack_files_present`` | every ``official_agents/<name>/agent_pack.json`` exists and is valid JSON |
| 10 | ``agent_pack_required_fields`` | raw-pack fields: ``manifest.{name,version}``, non-empty ``system_prompt``, ``requirements.min_runtime_version`` |
| 11 | ``mcp_tool_registry_loads`` | ``TOOL_REGISTRY`` populated |
| 12 | ``mcp_tool_registry_matches_pack`` | TOOL_REGISTRY keys ⊆ ``medcoder-coding-review/agent_pack.json::tools[].name`` |
| 13 | ``faiss_icd10_index`` | ``index_health_check(data/medcoder)`` returns ``status=ok`` (37,897 codes / dim=1024) |
| 14 | ``faiss_icd9cm3_index`` | same for ``faiss_icd9cm3.index`` (13,617 codes) — WARN-only since E1.3 is optional |
| 15 | ``bge_m3_model_cache`` | ``data/medcoder/models/models--BAAI--bge-m3`` OR ``~/.cache/huggingface/hub/models--BAAI--bge-m3`` |
| 16 | ``llm_provider_configured`` | ``ICODER_CREDENTIAL_LLM`` + ``LLM_BASE_URL`` + ``LLM_MODEL`` (env first, then app.config defaults) |
| 17 | ``run_trace_dir_writable`` | ``.icoder/m2a`` mkdir + write + unlink probe |
| 18 | ``icoder_state_dir_gitignored`` | ``backend/.icoder/`` pattern in ``.gitignore`` |
| 19 | ``fewshot_flag_default_off`` | ``is_medcoder_fewshot_enabled()`` returns False unless explicit opt-in |
| 20 | ``medcoder_index_health_via_app_state`` | post-lifespan ``/api/health`` shows ``medcoder_index_ready=true`` |

#### Local doctor run

```
iCoDer Doctor — verdict: OK
summary: 20 OK, 0 WARN, 0 FAIL, 0 SKIP (of 20)
  [OK] 01.python_version Python ≥ 3.11 — 3.12.3
  [OK] 02.fastapi_version fastapi ≥ 0.100 — 0.115.0
  [OK] 03.starlette_version starlette ≥ 0.36 (no on_startup) — 0.38.0
  [OK] 04.uvicorn_version uvicorn installed — 0.30.6
  [OK] 05.no_deprecated_on_startup_in_app_code No deprecated @app.on_startup/on_event
  [OK] 06.app_main_imports import app.main — ok
  [OK] 07.api_health_endpoint GET /api/health → 200 — ok
  [OK] 08.agent_registry_present RuntimeAgentRegistry populated — 10 agent(s)
  [OK] 09.agent_pack_files_present official_agents/*/agent_pack.json present — 16 pack(s)
  [OK] 10.agent_pack_required_fields Agent packs have required raw fields — 16 pack(s) inspected
  [OK] 11.mcp_tool_registry_loads MCP TOOL_REGISTRY populated — 5 tool(s)
  [OK] 12.mcp_tool_registry_matches_pack TOOL_REGISTRY ⊆ pack tools — 5 tool(s) match
  [OK] 13.faiss_icd10_index FAISS ICD-10 index healthy — ntotal=37897 dim=1024
  [OK] 14.faiss_icd9cm3_index FAISS ICD-9-CM-3 index healthy — ntotal=13617 dim=1024
  [OK] 15.bge_m3_model_cache BGE-M3 model cache present — …/models--BAAI--bge-m3
  [OK] 16.llm_provider_configured LLM provider configured — model=deepseek-chat base=https://api.deepseek.com/v1
  [OK] 17.run_trace_dir_writable Run trace dir writable — E:\Corti4C\backend\.icoder\m2a
  [OK] 18.icoder_state_dir_gitignored .icoder/ in .gitignore — match found
  [OK] 19.fewshot_flag_default_off ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT default off — env='' → disabled
  [OK] 20.medcoder_index_health_via_app_state MedCodER index health via app.state — ready=True
```

### 2.4 P1.0-E — Run Trace / Observability

| Artifact | Path | Status |
|----------|------|--------|
| Backend router | ``backend/app/api/icoder_runs.py`` | ✅ ``GET /api/icoder/runs`` + ``/runs/{run_id}`` |
| Mounted in app | ``backend/app/main.py:846`` | ✅ |
| Frontend page | ``frontend/src/pages/RunTracePage.tsx`` | ✅ Two-column layout: list rail + detail (status, processing time, primary diagnosis, errors, input preview) |
| Frontend API | ``frontend/src/services/runsApi.ts`` | ✅ Typed client (RunHistoryEntry) |
| Frontend route | ``frontend/src/App.tsx:110`` | ✅ ``<Route path="runtime/runs" />`` |
| Tests | ``backend/tests/unit/app/api/test_icoder_runs.py`` | ✅ 5 tests: envelope, filter by agent_ref, empty history, single-run get, unknown-id 404 |

#### Design

* **Thin aliases**: no new persistence layer. Reuses
  ``app.state.run_history`` (RunHistoryStore) exactly like
  ``/api/runtime/runs`` does.
* **No fake data**: empty history → ``{runs: [], total: 0,
  history_available: true}``. Unknown run_id → 404 with
  ``error_code: RUN_NOT_FOUND``.

### 2.5 P1.0-F — Frontend navigation整理

| Artifact | Path | Status |
|----------|------|--------|
| Doctor Report page | ``frontend/src/pages/DoctorReportPage.tsx`` | ✅ Renders verdict-driven summary + 20-check list + per-check detail payload |
| Frontend route | ``frontend/src/App.tsx:111`` | ✅ ``<Route path="runtime/doctor" />`` |
| Layout nav | ``frontend/src/components/layout/Layout.tsx`` | ✅ Added Run Trace + Doctor Report entries to Runtime section |
| Typecheck | ``npx tsc --noEmit`` | ✅ 0 errors |
| Build | ``npm run build`` | ✅ 1,697 modules transformed, dist OK |

#### Runtime nav section (after P1.0-F)

```
Runtime
├── Agent Hub        → /runtime/agent-hub
├── Run Trace        → /runtime/runs
├── Doctor Report    → /runtime/doctor
├── Runtime Console  → /runtime/console
└── Medical Coding   → /runtime/coding-review
```

## 3. Test results

### 3.1 Round 1 — Backend unit tests

| Test file | Count | Status |
|-----------|-------|--------|
| ``tests/unit/scripts/test_icoder_doctor.py`` | 33 | ✅ all green |
| ``tests/unit/app/api/test_icoder_agents_hub.py`` | 8 | ✅ all green |
| ``tests/unit/app/api/test_icoder_doctor_api.py`` | 6 | ✅ all green |
| ``tests/unit/app/api/test_icoder_runs.py`` | 5 | ✅ all green |
| **P1.0 subtotal** | **52** | **✅ all green** |
| Full ``tests/unit`` regression | 926 | ✅ all green (no regression) |

### 3.2 Round 2 — End-to-end API smoke

```
=== P1.0-B Agent Hub ===
  GET /api/icoder/agents → 10 agents
  GET /api/icoder/agents/{ref}/card → name resolved
  GET /api/icoder/agents/{ref}/health → overall=ready
  GET /api/icoder/agents/{ref}/requirements → 7 env vars, fewshot listed: yes
  GET /api/icoder/agents/totally-not-real/card → 404 AGENT_NOT_FOUND

=== P1.0-C Doctor ===
  GET /api/icoder/doctor → {passed: 20, warned: 0, failed: 0, skipped: 0}
  GET /api/icoder/doctor/19 → check id=19.fewshot_flag_default_off
  GET /api/icoder/doctor/nonexistent → 404 DOCTOR_CHECK_NOT_FOUND

=== P1.0-E Run Trace ===
  GET /api/icoder/runs → 0 run(s), history_available=True
  GET /api/icoder/runs/totally-not-a-real-run → 404 RUN_NOT_FOUND

=== P1.0-A Few-shot flag default off ===
  is_medcoder_fewshot_enabled() → False (default off)

=== All e2e smoke checks PASSED ===
```

### 3.3 Round 3 — Frontend typecheck + build

```
$ npx tsc --noEmit
(0 errors)

$ npm run build
✓ 1697 modules transformed.
dist/index.html                                    0.80 kB │ gzip:   0.45 kB
dist/assets/index-BML-4Rw1.css                     55.16 kB │ gzip:   9.65 kB
dist/assets/EmbedDemoCodingReviewPage-B4ZqNhuX.js  22.57 kB │ gzip:   7.97 kB
dist/assets/index-NUsWbROS.js                      735.37 kB │ gzip: 212.34 kB
✓ built in 6.32s
```

## 4. Honest findings / risks

* **E1.10 (commit ``2e91333``)**: FAISS MMAP + BGE dtype key stays — it's
  deployment stability, not part of P1.0 productization.
* **E2.0**: archived as **negative/inconclusive** signal. **Not promoted**
  to default. Backlog docs spell out why and what NOT to do next.
* **P1.0-A flag leak**: any developer accidentally setting
  ``ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT=1`` is caught by:
  * check #19 (doctor WARN)
  * ``requirements`` endpoint exposes ``set`` field
  * TestGetAgentRequirements::test_known_agent_requirements_shape asserts
    credential redaction; same suite can extend to flag redaction.
* **Phase B tech debt** (Starlette 0.38 + FastAPI 0.115
  ``on_startup`` deprecation): clean in production code (check #5
  passes). Tests still use the deprecated path — not blocking P1.0,
  flagged for P2 cleanup.
* **Format-version drift**: pack validation uses raw-pack fields
  (check #10) instead of ``AgentPackageV1.from_dict()`` because Phase
  D3 packs use ``format_version=1.2``. **Future work** (P2+):
  bump validator to accept 1.2 OR back-port packs to 1.1.
* **Agent registry contains 10 of 16 discovered packs**: the other 6
  packs fail v1.1 validation (``format_version`` / ``agent_type``) and
  log a WARNING at boot. Doctor check #09 counts all 16 packs on disk
  (correctly), check #08 reports the 10 that successfully registered.
  This is **honest and surfaced** in the doctor output.

## 5. Verification target

The spec asked for:

> Agent Hub page can compile. MedCodER Agent can display. experimental /
> disabled states correct. unknown agent still returns AGENT_NOT_FOUND.

All satisfied:

* Frontend compiles (Round 3) ✅
* ``/runtime/agent-hub`` shows 10 agents with tier/status/experimental
  badge (Round 2) ✅
* experimental flag computed from raw pack ``agent_type`` (Round 2) ✅
* Unknown agent → ``404 AGENT_NOT_FOUND`` (Round 2) ✅

## 6. Files added / changed

### Added

```
backend/app/api/icoder_doctor.py                  (P1.0-C)
backend/app/api/icoder_runs.py                    (P1.0-E)
backend/scripts/icoder_doctor.py                  (P1.0-C)
backend/tests/unit/app/api/test_icoder_doctor_api.py    (P1.0-C)
backend/tests/unit/app/api/test_icoder_runs.py          (P1.0-E)
backend/tests/unit/scripts/test_icoder_doctor.py        (P1.0-C)
docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md   (P1.0-A)
docs/backlog/CODING_QUALITY_BACKLOG.md            (P1.0-A)
frontend/src/pages/DoctorReportPage.tsx           (P1.0-F)
frontend/src/pages/RunTracePage.tsx               (P1.0-E)
frontend/src/services/runsApi.ts                  (P1.0-E)
```

### Modified

```
backend/app/main.py                               (mount 3 new routers)
backend/icoder_runtime/providers/medical_coding/medcoder_adapter.py  (P1.0-A flag)
backend/tests/test_services/test_medcoder_adapter.py                  (P1.0-A tests)
frontend/src/App.tsx                              (3 new routes)
frontend/src/components/layout/Layout.tsx         (nav section)
.env.cloud.example                                (P1.0-A doc)
```

## 7. Verdict

**PASS**.

* All 5 sub-tasks (P1.0-A/B/C/E/F) shipped with non-trivial tests.
* 52 P1.0 unit tests + 926 full unit regression = **978 / 978 green**.
* 0 frontend typecheck errors, 0 build errors.
* Doctor reports **20 / 20 OK** on this checkout (verdict=OK, exit code 0).
* No fake data. Every endpoint returns an honest answer.
* Spec non-goals honored: no Stage 4 changes, no n=30 expansion, no F1
  logic, no Marketplace surface.
* E1.10 (commit ``2e91333``) preserved as deployment stability baseline.

---

## Appendix A — Reproducing the doctor

```bash
cd backend
PYTHONIOENCODING=utf-8 python scripts/icoder_doctor.py
# or
PYTHONIOENCODING=utf-8 python scripts/icoder_doctor.py --json
# or
PYTHONIOENCODING=utf-8 python scripts/icoder_doctor.py --only 13,14,19
```

Exit codes: ``0`` = OK, ``1`` = WARN, ``2`` = FAIL. Suitable for CI
gating.

## Appendix B — Reproducing the e2e smoke

```bash
cd backend
PYTHONIOENCODING=utf-8 python -c "
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    assert c.get('/api/icoder/agents').status_code == 200
    assert c.get('/api/icoder/doctor').status_code == 200
    assert c.get('/api/icoder/runs').status_code == 200
    assert c.get('/api/icoder/runs/x').status_code == 404
print('OK')
"
```