# Audit Gate 4 — Agent Capability Audit (Track D)

> Per-agent capability card for the 10 visible Hub agents. Evidence = code + DB RunHistory + manifest JSON. Per PDF §D1–D5.

## D0. Headline evidence — RunHistory aggregates

From `backend/data/icoder.db → run_history` (240 rows, 4-day span 2026-07-10 → 2026-07-14):

```
agent_id                              runtime_mode          n   avg_lat(ms)  total_cost(CNY)
medical-coding-agent                  corti_like_fast      35        5646       0.000000   ← cost broken
drg-analyzer                          a2a_pure_llm         24        6918       0.013946   ✓
discharge-summary-structuring         a2a_pure_llm         19        3614       0.002642   ✓
evidence-extractor                    a2a_pure_llm         17        4250       0.007013   ✓
note-completeness-agent               a2a_pure_llm         14        9411       0.003791   ✓
principal-diagnosis-review            a2a_pure_llm         14        7641       0.004485   ✓
drg-analyzer                          corti_like_fast      13        9196       0.003968   ✓
compliance-guardrail                  (no mode)            12          10       0.000000   ← stub-fast
note-completeness                     (no mode)            12           8        0.000000   ← stub-fast
note-completeness-agent               corti_like_fast      11        9579       0.003311   ✓
discharge-summary-structuring         corti_like_fast       9        5447       0.001673   ✓
principal-diagnosis-review            corti_like_fast       9        9963       0.002768   ✓
procedure-extractor                   corti_like_fast       9        7951       0.001212   ✓
code-validation-agent                 llm_with_tools        8       16505       0.002400   ✓
compliance-guardrail-agent            corti_like_fast       8           7        0.000000   ← stub-fast
evidence-extractor                    corti_like_fast       8        5248       0.001780   ✓
nonexistent-agent                     corti_like_fast       5          27        0.000000   ← fake agent OK
code-validation-agent                 a2a_pure_llm          4           4        0.000000   ← stub-fast
compliance-guardrail-agent            rule_engine           3          14        0.000000   ← rule fast path
procedure-extractor                   a2a_pure_llm          3        5070       0.000403   ✓
cdi                                   (no mode)             1          36        0.000000   ← FAILED
drg-analyzer-nonexistent              corti_like_fast       1          19        0.000000   ← fake
this-agent-does-not-exist             corti_like_fast       1           7        0.000000   ← fake
```

**Totals**: 240 runs · CNY ¥0.049392 · avg latency 5.7s · max latency 63.1s · 1 FAILED · 239 COMPLETED.

## D0.1 Cross-agent critical findings

### F1 — medical-coding-agent has zero recorded cost across 35 real-LLM runs (P0)

35 completed runs in `corti_like_fast` mode, avg 5646ms (clearly hitting DeepSeek), **but `SUM(cost_usd) = 0.000000` for every single one**. Other agents using the same provider (`drg-analyzer`, `evidence-extractor`, etc.) do record cost correctly (¥0.014, ¥0.007).

→ The **core product agent's cost-recording path is broken**. Usage × Medical Coding attribution cannot be reconciled. Register as **G4-001 (P0)**.

### F2 — run_trace_events table is EMPTY for all 240 runs (P0)

```
run_trace_events: 0 rows
```

Despite Phase 5 Track C closure report claiming "trace_events persisted to RunTraceStore", **not a single run has any trace events stored**. The `/runs/:runId/trace` page (verified Gate 3) gracefully renders the empty state — but it's the **only state it can render**. The RunTrace page is functionally non-functional for any historical run. Register as **G4-002 (P0)**.

### F3 — api_client_id is NULL on all 240 runs (P1)

Phase 7 Gate 5 ("API Client Attribution") shipped alembic 014 + CRUD endpoints + UI. The column exists in `run_history`. **No run has ever been attributed to an API client**. The partner integration claims from Phase 7 Gate 12 (real-DeepSeek-via-partner-credentials) **left no footprint in RunHistory**. Register as **G4-003 (P1)**.

### F4 — `nonexistent-agent` / `drg-analyzer-nonexistent` / `this-agent-does-not-exist` all return COMPLETED (P1)

The run endpoint never raises for unknown agents (by design per `agent_run.py:20-22`). 7 runs logged against non-existent agents all returned COMPLETED. This **inflates the success-rate metric** (99.6% looks healthy but includes 3 fake-agent success records). Register as **G4-004 (P1)**.

### F5 — Snake_case + kebab-case dual agent identity (P2)

`note-completeness` (12 runs, no mode) + `note-completeness-agent` (25 runs, with mode). `compliance-guardrail` (12 runs, no mode) + `compliance-guardrail-agent` (11 runs, with mode). **The same logical agent is tracked under two registry keys**. Confirms Gate 1 G1-006. Register as **G4-005 (P2)**.

### F6 — `medcoder_deep` mode: 0 runs (P1)

The MedCodER 5-stage pipeline (PDF §E4 specifically asks about it; CLAUDE.md describes it in detail) **has never been invoked in production**. The UI exposes it as "Deep Evidence · MedCodER 5 阶段 · 30-60s+ · 高级", but no run has ever used it. It is shipped-but-unused. Register as **G4-006 (P1)**.

### F7 — CDI has 718 `cdi_cases` rows but only 1 RunHistory row (which FAILED) (P1)

CDI runs are persisted in a **separate table** (`cdi_cases`) and bypass `run_history`. The Track H calibration work created 718 CDI cases on a single patient_ref "DEID" with the same agent over 2026-07-13 — **bulk test data, not real hospital encounters**. The single `cdi` row in `run_history` is a 36ms FAILED run. Register as **G4-007 (P1)**.

### F8 — 12 `stub-fast` compliance-guardrail runs (P2)

`compliance-guardrail` (no mode) and `compliance-guardrail-agent / corti_like_fast` both have avg latency 7-10ms — **too fast to have called DeepSeek**. These return a stub/cached response. Combined with the `rule_engine` mode (3 runs, 14ms), this means **compliance-guardrail's production behavior is stub-dominant**, not rule-engine-enforced. Register as **G4-008 (P2)**.

## D1–D5. Per-agent capability cards

### Card 1 — `medical-coding-agent` (CORE_ENTRY_AGENT #2)

| Field | Value |
|-------|-------|
| Agent ID | `medical-coding-agent` |
| Display name | `医学编码智能体 (Medical Coding)` |
| Manifest version | 2.0.0 |
| Hub maturity | `mvp` (stale — actual depth is much higher) |
| `production_ready` | `false` (honest UI label confirms) |
| `human_review` | `required` (UI: "所有编码建议需人工复核") |
| Risk level | Core product |
| Python impl | `app/coding_runtime/{dispatcher,fast_runtime,medcoder_runtime}.py` + `icoder_runtime/providers/medical_coding/{deepseek_coding_adapter,hybrid_adapter,medcoder_adapter,mock_adapter}.py` + `dictionary_rag.py` + `embedding_bge_m3.py` |
| Pack manifest | `official_agents/medical_coding/agent_pack.json` (1423-char system_prompt, 1 expert, 5 tools) |
| Real execution | `POST /api/v1/agents/medical-coding-agent/run` → `agent_run.py` → `a2a_facade.dispatch_medical_coding_fast()` → `FastCodingRuntime` → `DeepSeekCodingAdapter` |
| Modes | `corti_like_fast` (35 runs, 5.6s avg) · `medcoder_deep` (**0 runs**) |
| Result schema | `MedicalCodingOutputSchema` (extracted_diagnoses list with evidence, codes, confidence) |
| Quality evidence | 201-case iCoDer fixture + 100-case CCL2026 val + 270-case standard set (offline) |
| Bypass paths | None observed — A2A facade is the sole entry |
| Cost recording | **BROKEN** (F1) |
| Status | **CORE_AGENT_WITH_BROKEN_COST_ATAttribUTION_AND_UNUSED_DEEP_PIPELINE** |

### Card 2 — `clinical-documentation-improvement-agent` (CDI, CORE_ENTRY_AGENT #1)

| Field | Value |
|-------|-------|
| Agent ID | `clinical-documentation-improvement-agent` |
| Display name | `临床文档改进智能体 (CDI)` |
| Manifest version | 1.0.0 |
| Hub maturity | `mvp` |
| `production_ready` | `false` |
| Python impl | **No dedicated .py in `official_agents/`** — implementation lives in `backend/app/icoder/agent_runtime/cdi/` + `backend/app/api/cdi.py` |
| Pack manifest | `official_agents/clinical-documentation-improvement-agent/agent_pack.json` (2554-char system_prompt, **4 experts**, **7 tools**) |
| Real execution | `POST /api/v1/cdi/*` (6 endpoints) — **separate from agent_run.py facade** |
| Persistence | **Separate table `cdi_cases`** (718 rows, all calibration test data) — bypasses `run_history` |
| States | AUTO_PASS 254 · REVIEW_REQUIRED 354 · REVIEW_RECOMMENDED 13 · BLOCKED 97 |
| Real RunHistory rows | 1 (FAILED, 36ms, 2026-07-14) |
| Calibration state | Frozen at iter 7 (`icoder-cdi-agent-v1.0.0-rc5` per commit `79b2b03`) |
| PDF pause honored | ✓ — no in-flight CDI prompt changes in workspace |
| Bypass paths | **Yes** — CDI runs do not flow through the unified `agent_run.py` A2A facade; they have their own router. PDF §H1 explicitly asks about A2A bypass paths — **CDI is one**. |
| Status | **CORE_AGENT_WITH_SEPARATE_PERSISTENCE_AND_SEPARATE_RUN_PATH** |

### Card 3 — `drg-analyzer` (DRG/DIP)

| Field | Value |
|-------|-------|
| Agent ID | `drg-analyzer` |
| Display name | `DRG/DIP 风险复核智能体` |
| Manifest version | 1.0.0 |
| Hub maturity | `mvp` |
| `production_ready` | `false` |
| Python impl | `__init__.py` only (no agent.py) — implementation is in `backend/app/agents/experts/drg_expert.py` + `backend/icoder_runtime/providers/drg/` |
| Pack manifest | `official_agents/drg-analyzer/agent_pack.json` (897-char system_prompt, 1 expert, 0 tools) |
| Real execution | `a2a_pure_llm` mode (24 runs, 6.9s avg, ¥0.014) + `corti_like_fast` mode (13 runs, 9.2s) |
| Result schema | LLM-generated risk narrative (not a real DRG grouper) |
| Real DRG grouper? | **NO** — see Gate 5/9 |
| Status | **LLM_RISK_NARRATIVE_NOT_REAL_GROUPER** |

### Card 4 — `code-validation-agent`

| Field | Value |
|-------|-------|
| Agent ID | `code-validation-agent` |
| Manifest version | 2.0.0 |
| Hub maturity | `runnable` (one of only 2) |
| Python impl | `official_agents/code_validation/agent.py` + `system_prompt_v2.py` + `output_schema_v2.py` + `agent_legacy.py` |
| Real execution | `llm_with_tools` mode (8 runs, 16.5s avg ← **longest**, tool-calling loop) + `a2a_pure_llm` mode (4 runs, 4ms — stub) |
| Tools | 4 MCP tools (verify_code / get_guidelines / explore_code / search_codes) |
| Status | **MOST_ADVANCED_NON_CORE_AGENT** |

### Card 5 — `note-completeness-agent`

| Field | Value |
|-------|-------|
| Agent ID | `note-completeness-agent` (+ legacy `note-completeness`) |
| Hub maturity | `runnable` (one of only 2) |
| Python impl | `official_agents/note_completeness/agent.py` + `agent_legacy.py` |
| Real execution | `a2a_pure_llm` (14 runs, 9.4s) + `corti_like_fast` (11 runs, 9.6s) + no-mode (12 runs, 8ms — stub) |
| Status | **RUNNABLE_BUT_DUAL_IDENTITY** (F5) |

### Card 6 — `evidence-extractor`

| Field | Value |
|-------|-------|
| Agent ID | `evidence-extractor` |
| Python impl | **None in official_agents/evidence_extractor/** (only agent_pack.json) |
| Real execution | `a2a_pure_llm` (17 runs, 4.3s, ¥0.007) + `corti_like_fast` (8 runs, 5.2s) |
| Implementation source | TBD — possibly `backend/app/agents/experts/evidence_expert.py` or `app/icoder/agent_runtime/experts/evidence_extractor_expert.py` |
| Status | **LIVE_BUT_NO_CANONICAL_PYTHON_IMPL_DIR** |

### Card 7 — `principal-diagnosis-review`

| Field | Value |
|-------|-------|
| Agent ID | `principal-diagnosis-review` |
| Python impl | **None in official_agents/** (only agent_pack.json) |
| Real execution | `a2a_pure_llm` (14 runs, 7.6s, ¥0.004) + `corti_like_fast` (9 runs, 9.9s) |
| Status | **LIVE_BUT_PACK_ONLY** |

### Card 8 — `discharge-summary-structuring`

| Field | Value |
|-------|-------|
| Agent ID | `discharge-summary-structuring` |
| Python impl | **None** (only agent_pack.json) |
| Real execution | `a2a_pure_llm` (19 runs, 3.6s, ¥0.003) + `corti_like_fast` (9 runs, 5.4s) |
| PDF §4.3 boundary | Explicitly NOT CDI per CLAUDE.md — verified correct (separate agent_id) |
| Status | **LIVE_BUT_PACK_ONLY** |

### Card 9 — `procedure-extractor`

| Field | Value |
|-------|-------|
| Agent ID | `procedure-extractor` |
| Python impl | **None** (only agent_pack.json) |
| Real execution | `corti_like_fast` (9 runs, 8.0s, ¥0.001) + `a2a_pure_llm` (3 runs, 5.1s) |
| Status | **LIVE_BUT_PACK_ONLY** |

### Card 10 — `compliance-guardrail-agent`

| Field | Value |
|-------|-------|
| Agent ID | `compliance-guardrail-agent` (+ legacy `compliance-guardrail`) |
| Python impl | `official_agents/compliance_guardrail/agent.py` |
| Real execution | stub-fast (8 runs, 7ms) + rule_engine (3 runs, 14ms) — **0 real LLM runs** |
| Status | **STUB_DOMINANT** (F8) |

## D2. Execution chain audit (high-level)

Per the PDF §D2 required trace:

```
Frontend (AgentChatPage / MedicalCodingPage)
  → POST /api/v1/agents/{id}/run (agent_run.py)
    → get_current_user_or_oauth_client (auth middleware)
    → get_current_organization
    → IdempotencyService.acquire_or_replay (Phase 7 Gate 3)
    → a2a_facade.construct_envelope + dispatch_medical_coding_fast
      → CodingRuntimeDispatcher.dispatch(request)
        → FastCodingRuntime.predict  (default)
        → MedCoderRuntime.predict    (mode=medcoder_deep, NEVER USED)
          → DeepSeekCodingAdapter / HybridAdapter
            → LLMGateway → DeepSeek API
          → Compliance RuleEngine post-validation
      → MedicalCodingOutputSchema
    → persist_trace_events (BROKEN — 0 rows in DB)
    → IdempotencyService.mark_completed
    → RunHistory.create (api_client_id always NULL)
    → AgentRunResponse (A2A-compatible envelope)
  → Frontend renders
```

**Two bypass paths found**:

1. **CDI** — separate router `POST /api/v1/cdi/*`, separate table `cdi_cases`, never touches `agent_run.py` facade or `run_history`.
2. **Coding Compliance** — separate router `POST /api/v1/coding-compliance/run` (Phase 5 Track C 7-stage orchestrator), separate persistence.

These are **A2A-compatible** (use A2A envelope construction from `a2a_facade`) but **do not flow through the unified run endpoint**. PDF §H1 explicitly warns against "绕开 A2A 的第二套独立 Runtime 主线". CDI + Coding-Compliance are **partial bypass paths** — they share the envelope but not the run-history + trace persistence path.

## D3. Real-capability breakdown

| Layer | Used in production? |
|-------|---------------------|
| Prompt | ✓ DeepSeek system_prompt for every agent |
| Rule | Only compliance-guardrail `rule_engine` mode (3 runs) |
| Tool | code-validation `llm_with_tools` mode (8 runs) |
| Retrieval (BGE-M3 + FAISS) | **0 production runs** (MedCodER `medcoder_deep` mode never used) |
| Model (DeepSeek V4) | ✓ 100+ real-LLM runs |
| Hard-coded output | 7 nonexistent-agent COMPLETED responses |
| Fixture | CDI 718 calibration cases (test data) |
| Mock | MockAdapter shipped but unused in production |
| Provider fallback | Not exercised |
| Degraded mode | compliance-guardrail stub-fast (12 runs) |

## D4. Result contract

The product uses **multiple result schemas** (term drift, G2-008):

- `MedicalCodingOutputSchema` (medical coding)
- `CodingResult` (coding_runtime flat projection)
- `AgentRunResponse` (unified envelope)
- `CodingReviewRun` (legacy DB model)
- CDI-specific dict (cdi_cases.encounter_summary JSON)
- DRG-specific narrative text

Each agent category has its own output schema — there is no single contract.

## D5. Quality evidence

| Agent | Fixture | Gold set | Real-case browser test | Expert review |
|-------|---------|----------|------------------------|----------------|
| Medical Coding | `tests/fixtures/icoder_201.json` (201), `ccl2026_val_100.json` (100), `ccl2026_train_gold.json` (1800) | Yes | Yes (Gate 3) | Not formal |
| CDI | 40-case Corti calibration (test data) | No public | Yes (Gate 3) | Not formal |
| DRG-DIP | None observed | No | Yes (Gate 3) | None |
| Others | None | None | No | None |

→ Only Medical Coding has a serious offline quality benchmark (CCL 2026 train + iCoDer 201). The other agents have no quality evidence beyond "the API returned 200".

## D6. New findings registered

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G4-001** | P0 | billing | `medical-coding-agent` has 0 recorded cost across 35 real-LLM corti_like_fast runs — Usage × Medical Coding attribution broken |
| **G4-002** | P0 | observability | `run_trace_events` table is empty (0 rows) for all 240 runs — RunTrace page is functionally non-functional for any historical run |
| **G4-003** | P1 | partner-integration | `api_client_id` NULL on all 240 runs — Phase 7 Gate 5 attribution shipped but never exercised in production |
| **G4-004** | P1 | metrics | `nonexistent-agent` × 5 + 2 other fake agents all returned COMPLETED — inflates 99.6% success rate |
| **G4-005** | P2 | registry | `note-completeness` + `note-completeness-agent` (and same for compliance-guardrail) are dual registry keys for same logical agent |
| **G4-006** | P1 | dead-code-runtime | `medcoder_deep` (MedCodER 5-stage) has 0 production invocations despite UI exposure and CLAUDE.md description |
| **G4-007** | P1 | persistence | CDI runs bypass `run_history` — 718 `cdi_cases` (all 2026-07-13 calibration data on patient_ref=DEID) vs 1 FAILED RunHistory row |
| **G4-008** | P2 | runtime | `compliance-guardrail` returns stub-fast (7-10ms) responses — 12 runs hit no real engine |
| **G4-009** | P2 | architecture | CDI + Coding Compliance are **partial A2A bypass paths** — share envelope but not RunHistory + trace persistence |
| **G4-010** | P2 | term-drift | 6 different result schemas coexist (MedicalCodingOutputSchema / CodingResult / AgentRunResponse / CodingReviewRun / CDI dict / DRG narrative) |

## D7. Gate 4 verdict

`CORE_AGENT_LIVE_WITH_P0_COST_AND_TRACE_GAPS_AND_PARTIAL_A2A_BYPASS`

- Medical Coding core agent works end-to-end via real DeepSeek ✓
- 9 of 10 Hub agents have live execution evidence ✓
- **P0 G4-001**: core agent cost not recorded
- **P0 G4-002**: trace events never persisted (RunTrace page can only show empty state)
- **P1 G4-006**: MedCodER 5-stage pipeline shipped but never used
- **P1 G4-007**: CDI persistence is in a parallel table, not run_history
- Partial A2A bypass for CDI + Coding Compliance
- 1 CDI agent + 1 medical-coding-agent qualify as CORE_ENTRY_AGENTS per CLAUDE.md §产品定位

Gate 4 closes. Proceed to **Gate 5 — Medical Coding / CDI / DRG-DIP Deep Audit**.
