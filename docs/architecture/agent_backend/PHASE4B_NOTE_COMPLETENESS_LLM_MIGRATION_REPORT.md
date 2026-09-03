# Phase 4-B — Note Completeness LLM Migration Report

**Date:** 2026-07-08
**Status:** PASS
**Scope:** Migrate `note-completeness` agent from regex-based to LLM-based via `PureLLMProvider`. First real LLM agent in iCoDer — proves the Phase 4-A `AgentBackendProvider` foundation works end-to-end.

---

## 1. Goal & Scope

**Goal:** Replace the existing regex-based `note-completeness` agent with an LLM-based implementation using `PureLLMProvider`. Preserve the regex logic as `agent_legacy.py` for A/B fallback. Wire `emit_backend_metadata_event` into production so the frontend `BackendProviderSummary` renders with real data.

**In scope:**
- `LLMGatewayAdapter` — bridges `LLMGateway.generate(messages)` ↔ `LLMClient.complete(system_prompt, user_input)` Protocol
- `PureLLMProvider` real-LLM wiring (constructor accepts `llm_gateway`, lazy-resolves via `registry.get_gateway()`)
- `emit_backend_metadata_event` call from `PureLLMProvider.invoke()`
- Registry `set_gateway_lookup` / `get_gateway` module-level gateway lookup
- `app/main.py` wiring at startup
- New `agent.py` (LLM-based) for `note_completeness`
- Legacy regex preserved as `agent_legacy.py`
- `note-completeness/agent_pack.json` declares `backend_provider="icoder.pure-llm.v1"`
- Chinese system prompt based on《病历书写基本规范》7+1 sections
- 3 new test files + 2 extended test files

**Out of scope (Phase 4-C+):**
- Streaming (`LLMGatewayAdapter.stream()` raises `NotImplementedError`)
- Code Validation / Compliance Guardrail migration
- Medical Coding Agent changes
- `LLMWithToolsProvider` real tool-calling (still skeleton)

**Approach choice:** User chose Option A (Full replace) — replace the regex agent entirely with the LLM agent, preserve regex as `agent_legacy.py` for fallback only. This proves the LLM path is real, not a parallel-track experiment.

---

## 2. What Changed (files + LOC delta)

| File | Action | LOC |
|------|--------|-----|
| `backend/icoder_runtime/backends/llm_gateway_adapter.py` | new | 157 |
| `backend/icoder_runtime/backends/pure_llm_provider.py` | edit | +60 (constructor + `_resolve_client` + `_emit_backend_metadata`) |
| `backend/icoder_runtime/backends/registry.py` | edit | +30 (`set_gateway_lookup` / `get_gateway` module-level) |
| `backend/app/main.py` | edit | +3 (lifespan wires `set_gateway_lookup`) |
| `backend/official_agents/note_completeness/agent.py` | new (replaces regex) | 383 |
| `backend/official_agents/note_completeness/agent_legacy.py` | renamed from `agent.py` | 142 (unchanged logic, +deprecation header) |
| `backend/official_agents/note-completeness/agent_pack.json` | edit | +10 / -5 |
| `backend/tests/unit/icoder/backends/test_llm_gateway_adapter.py` | new | 201 |
| `backend/tests/unit/icoder/backends/test_pure_llm_provider_backend_metadata.py` | new | 222 |
| `backend/tests/unit/icoder/note_completeness/test_agent_llm.py` | new | 341 |
| `backend/tests/unit/icoder/note_completeness/__init__.py` | new | 0 |
| `backend/tests/unit/icoder/backends/test_pure_llm_provider.py` | edit | +40 (3 new tests + `fresh_registry_with_gateway` fixture) |
| `backend/tests/unit/icoder/backends/test_agent_pack_backend_schema.py` | edit | +30 (2 new tests for note-completeness pack) |
| `docs/architecture/agent_backend/phase4b_walkthrough.png` | new | screenshot |

**Total:** ~1430 LOC added/modified across 13 files.

---

## 3. LLMGatewayAdapter Design

**Problem:** `LLMGateway.generate()` takes `messages: list[dict]` (OpenAI chat format). `PureLLMProvider.LLMClient` Protocol expects `complete(system_prompt, user_input)`. The signature mismatch blocks direct wiring.

**Solution:** `LLMGatewayAdapter` is a stateless wrapper that adapts one to the other.

```python
class LLMGatewayAdapter:
    def __init__(self, gateway, *, provider=""):
        self._gateway = gateway
        self._provider = provider

    async def complete(self, *, system_prompt, user_input,
                       temperature=0.0, max_tokens=None,
                       timeout_seconds=60.0) -> LLMResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        context = {"temperature": temperature, "max_tokens": max_tokens,
                   "timeout_seconds": timeout_seconds}
        try:
            result = await self._gateway.generate(
                messages, provider=self._provider, context=context,
            )
        except Exception as e:
            return LLMResponse(text="", finish_reason=f"gateway_error:{type(e).__name__}", raw={"adapter_error": str(e)[:500]})
        # ... normalize dict → LLMResponse, detect degraded flag
```

**Key design choices:**
1. **Stateless** — one adapter instance can be shared across providers. No cleanup needed when the gateway is replaced.
2. **Never raises** — gateway exceptions become `LLMResponse(finish_reason="gateway_error:...")`. The caller (`PureLLMProvider`) decides fail vs. warning.
3. **Degraded detection** — if gateway returns `degraded=True` (mock fallback), adapter sets `finish_reason="degraded:{reason}"` so `PureLLMProvider` can mark `fallback_used=True` in the trace.
4. **No streaming** — `stream()` raises `NotImplementedError("Phase 4-B: ...")`. Streaming lands in Phase 4-C with the first `LLMWithToolsProvider` migration (likely Code Validation, ~12s latency benefits from SSE).
5. **`gateway` typed as `Any`** — avoids circular import (`llm_gateway` imports from `icoder_runtime.circuit_breaker`). The backends package stays self-contained.

**Tests:** 13 tests in `test_llm_gateway_adapter.py` — message construction, context propagation, provider passthrough, LLMResponse shape, raw dict passthrough, degraded detection, gateway exception swallowing, non-dict result handling, stream NotImplementedError, reusability across invokes.

---

## 4. `emit_backend_metadata_event` Wiring

**Problem:** Phase 4-A defined `emit_backend_metadata_event` in `run_trace.py` but never called it from production code. The frontend `BackendProviderSummary` rendered from this event — without the call, the panel was always empty.

**Solution:** `PureLLMProvider._emit_backend_metadata()` calls `emit_backend_metadata_event` after every successful LLM response. Defensive try/except ensures observability never breaks the agent run.

```python
def _emit_backend_metadata(self, ctx, latency_ms, status, *, fallback_used=False):
    try:
        from app.icoder.agent_runtime.orchestrator.run_trace import (
            emit_backend_metadata_event, get_default_store,
        )
        emit_backend_metadata_event(
            ctx.run_id,
            backend_provider=self.provider_id,           # "icoder.pure-llm.v1"
            backend_type=self.backend_type,              # "pure_llm"
            provider_latency_ms=latency_ms,
            provider_status=status,                      # parsed from markdown
            provider_deterministic=self.deterministic,   # False
            supports_tool_calling=self.supports_tool_calling,  # False
            fallback_used=fallback_used,                 # True if LLM degraded
            output_contract=self.output_contract(),      # "icoder/PureLLMOutput/v1"
            tool_rounds=0,
            store=get_default_store(),
        )
    except Exception as e:
        logger.warning("PureLLMProvider: emit_backend_metadata_event failed: %s", e)
```

**Call sites in `invoke()`:**
1. Skeleton path (no LLM wired) — emits with `provider_status="complete"`, `fallback_used=False`
2. Real LLM success — emits with parsed status, `fallback_used` = whether LLM returned `degraded:...`
3. Fail envelope (LLM timeout / error) — does NOT emit (the run didn't complete)

**Tests:** 6 tests in `test_pure_llm_provider_backend_metadata.py` — all 8 fields populated, `fallback_used=True` when degraded, skeleton path emits, fail envelope doesn't emit, gateway adapter path emits, doesn't break when RunTrace unavailable.

---

## 5. New System Prompt (Chinese, 7+1 sections)

The full prompt is inlined in `backend/official_agents/note_completeness/agent.py::SYSTEM_PROMPT`. Key structure:

```
你是 iCoDer 病历完整性智能体 (Note Completeness Agent)。

# 角色与职责
你接收中国医院入院记录 / 出院小结 / 病程记录文本，按《病历书写基本规范》
(2010 年版卫生部修订) 检测必填章节是否齐全，输出结构化 JSON 结果。

# 必填章节 (7 + 1)
非手术病例必填 7 个章节：
1. 主诉  2. 现病史  3. 既往史  4. 体格检查  5. 辅助检查  6. 诊断  7. 治疗经过

手术病例 (文本含"手术"/"切除术"/"吻合术"/"修补术"/"置换术"/"剖宫产"/
"刮宫"/"介入"等关键词) 必填第 8 个章节：8. 手术记录

# 评分规则
completeness_score = present_sections 数量 / required_sections 数量
review_conclusion:
  - PASS: completeness_score >= 0.85
  - WARNING: 0.5 <= completeness_score < 0.85
  - FAIL: completeness_score < 0.5

# 输出格式 (严格 JSON,不要任何额外文字 / Markdown 标记)
{review_conclusion, completeness_score, missing_sections, present_sections,
 required_sections, is_surgical_case, manual_review_required, documentation_gaps}

# 硬约束
- 不调用任何工具 — 你只读取文本并输出 JSON
- 不修改病历 — 只评估完整性
- 不分配 ICD 编码 — 编码由 Medical Coding Agent 完成
- 不输出任何额外文字、解释、Markdown 标记 — 只输出 JSON
- 不在输出中包含患者姓名 / 身份证号 / 联系方式等 PHI — 只输出章节级评估
- 章节名使用中文 (主诉 / 现病史 / 既往史 / 体格检查 / 辅助检查 / 诊断 / 治疗经过 / 手术记录)

# 示例
输入 (非手术病例,缺主诉):
"现病史：患者3年前出现心悸..."
输出:
{"review_conclusion": "WARNING", "completeness_score": 0.8571, ...}
```

**Rationale:** Corti's prompt isn't in the repo (probe captures are external). Per user direction, I wrote a Chinese prompt based on《病历书写基本规范》7+1 sections + Corti's 6-section Markdown structure. The prompt:
- Outputs JSON (not Markdown) — easier to parse, matches `NoteCompletenessOutputSchema` field names directly
- Hard constraints prevent PHI leakage, tool calls, ICD assignment
- Example anchors the expected shape
- Score thresholds (0.85 / 0.5) match Corti's PASS/WARNING/FAIL convention

---

## 6. Legacy Regex Fallback Policy

**Policy:** `agent.run()` always returns a valid `NoteCompletenessOutputSchema` dict. If the LLM path fails for any reason, fall back to the regex implementation.

**Fallback triggers (3 cases):**
1. **LLM invoke raises** — `try/except` around `_invoke_llm()`, falls back to `_legacy_run()`
2. **LLM returns `status="fail"`** — gateway timeout, degraded mode, or `LLMGatewayAdapter` returned `gateway_error:...`. Falls back to `_legacy_run()`
3. **LLM output unparseable** — `_extract_json()` returns None (no JSON in markdown). Falls back to `_legacy_run()`

**`agent_legacy.py` preservation:**
- Renamed from `agent.py` (preserved logic, +deprecation header)
- Same `async def run(input_text, *, run_id="") -> dict` signature
- Invocable directly: `from official_agents.note_completeness.agent_legacy import run`
- Deprecation header documents Phase 4-B replacement and A/B fallback policy

**Empty input:** Returns a fail envelope (`review_conclusion="FAIL"`, `completeness_score=0.0`) without calling the LLM. Saves a wasted API call.

**Score-conclusion consistency:** If LLM says `PASS` but `score=0.4`, `_parse_llm_json_to_schema()` re-derives conclusion from score. Defensive — LLM may be inconsistent.

---

## 7. Test Results

### Phase 4-B new + extended tests

```
backend/tests/unit/icoder/backends/test_llm_gateway_adapter.py         13 tests
backend/tests/unit/icoder/backends/test_pure_llm_provider_backend_metadata.py  6 tests
backend/tests/unit/icoder/note_completeness/test_agent_llm.py         12 tests
backend/tests/unit/icoder/backends/test_pure_llm_provider.py          +3 tests (Phase 4-B section)
backend/tests/unit/icoder/backends/test_agent_pack_backend_schema.py  +2 tests (note-completeness pack)
```

**Total Phase 4-B added:** 36 new tests.

### Full Phase 4-B suite

```bash
cd backend && python -m pytest tests/unit/icoder/backends/ tests/unit/icoder/note_completeness/ tests/unit/icoder_runtime/test_agent_pack_loader.py --tb=short -q
```

**Result:** `213 passed, 65 warnings in 2.61s` ✅

### Broader regression (icoder unit + icoder_runtime)

```bash
cd backend && python -m pytest tests/unit/icoder/ tests/unit/icoder_runtime/ --tb=short -q
```

**Result:** `2 failed, 1108 passed` — the 2 failures are PRE-EXISTING and unrelated to Phase 4-B:
- `tests/unit/icoder/a2a/test_agent_card.py::test_medcoder_card_basics`
- `tests/unit/icoder/a2a/test_agent_card.py::test_agent_list_response_minimal`

Both failures are due to the `medcoder-coding-review` pack's name being changed to Chinese (`MedCodER 编码审核智能体`) in an earlier phase, but the test still expects the English name `"MedCodER Coding Review Agent"`. Verified by `git stash` + re-run: with all Phase 4-B + earlier changes stashed, the test passes. The Phase 4-B changes don't touch `medcoder-coding-review/agent_pack.json` or `app/icoder/agent_runtime/a2a/agent_card.py`.

### TypeScript

```bash
cd frontend && npx tsc --noEmit
```

**Result:** 0 errors ✅ (no frontend code change in Phase 4-B; `BackendProviderSummary` was shipped in Phase 4-A).

### End-to-end smoke tests

**1. Legacy fallback path (dev mode = MockLLMProvider):**
```bash
python -c "
from official_agents.note_completeness.agent import run
import asyncio
result = asyncio.run(run('主诉：心悸3年...', run_id='smoke-1'))
print(result['review_conclusion'], result['completeness_score'])
"
```
**Output:** `PASS 1.0` — LLM was called, returned MockLLMProvider's generic JSON (wrong schema), `_parse_llm_json_to_schema` returned None, legacy regex fallback fired, all 7 sections detected. ✅

**2. Happy path with custom mock returning correct schema:**
```python
class _NoteCompleteMock:
    async def generate(self, messages, ...):
        return {"content": '{"review_conclusion":"WARNING","completeness_score":0.714,...}', ...}

result = asyncio.run(run(emr_text, run_id='smoke-2'))
# review_conclusion: WARNING
# completeness_score: 0.714
# is_surgical_case: True
# missing_sections: ['手术记录']
# present_sections count: 7
# required_sections count: 8
# manual_review_required: True
# trace_refs.run_id: smoke-2
```
All fields passed through correctly from LLM. ✅

**3. RunTrace event emission:**
```python
store = get_default_store()
events = store.get_run('smoke-trace-1')
# Total trace events: 1
# backend_metadata event:
#   backend_provider: icoder.pure-llm.v1
#   backend_type: pure_llm
#   provider_latency_ms: 123
#   provider_status: warning
#   provider_deterministic: False
#   supports_tool_calling: False
#   fallback_used: False
#   output_contract: icoder/PureLLMOutput/v1
#   tool_rounds: 0
```
All 8 backend metadata fields correctly emitted. ✅

---

## 8. Frontend Walkthrough Evidence

**Screenshot:** `docs/architecture/agent_backend/phase4b_walkthrough.png`

**Walkthrough steps:**

1. **Login** at `http://localhost:3001/login` with test user `phase4b / Phase4B!2026` (registered via `/api/auth/register`).

2. **Navigate** to AI Studio → AI智能体 → 预置AI智能体 tab. The Note Completeness card shows the updated description:
   > "iCoDer 病历完整性 Agent — ... Phase 4-B (2026-07-08): 迁移到 PureLLMProvider (LLM-based)，保留 regex legacy fallback。"

3. **Click** "Chat / Use Agent" on the Note Completeness card. URL: `/agents/{clone_id}/chat?preset=icoder%2Fnote-completeness-agent%401.0.0`.

4. **Paste** a 293-character EMR text (7 sections, no surgery). Click 运行.

5. **Output renders** with 5 sections (Completeness Score / Missing Sections / Present Sections / Supplement Suggestions / Coding-DRG-DIP Impact):
   - Score: 100.0%
   - Conclusion: PASS
   - Manual Review Required: No
   - Surgical Case: No
   - 7 present sections listed (主诉/现病史/既往史/体格检查/辅助检查/诊断/治疗经过)
   - 0 missing sections
   - Run ID: `3f4557ca-d87e-46ac-8062-a34d3c5c9a5b`

6. **Click** "View RunTrace" link. URL: `/runs/3f4557ca-d87e-46ac-8062-a34d3c5c9a5b/trace`. Page shows 9 steps, 10071ms total.

7. **Expand** step "8. 输出生成 (3341.0ms)" — the step containing the `backend_metadata` event. The `BACKEND PROVIDER` panel renders with all 8 fields:

   ```
   BACKEND PROVIDER
   icoder.pure-llm.v1
   pure_llm
   complete
   latency: 3341ms
   deterministic: no
   tools: no
   contract: icoder/PureLLMOutput/v1

   SAFE_METADATA
     "backend_provider": "icoder.pure-llm.v1",
     "backend_type": "pure_llm",
     "provider_latency_ms": 3341,
     "provider_status": "complete",
     "provider_deterministic": false,
     "supports_tool_calling": false,
     "fallback_used": false,
     "output_contract": "icoder/PureLLMOutput/v1",
     "tool_rounds": 0
   ```

All 8 backend metadata fields render correctly in the `BackendProviderSummary`. ✅

**Known UI discrepancy (cosmetic, not a Phase 4-B blocker):** The chat page header shows the old description "纯确定性 regex 检测，无 LLM" (sourced from the A2A agent card at `app/icoder/agent_runtime/a2a/agent_card.py`, NOT the pack description). The Agent Hub card shows the updated description (sourced from the pack). The A2A card description is hardcoded in the card builder and wasn't updated in Phase 4-B. Follow-up: update `agent_card.py` to pull description from the pack, or hardcode the new Phase 4-B description. Tracked as Phase 4-C cleanup.

---

## 9. Acceptance Criteria Check

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `note-completeness` pack loads with `backend_provider="icoder.pure-llm.v1"` and `has_backend_config=True` | ✅ | `test_note_completeness_pack_declares_pure_llm_backend` + `test_note_completeness_pack_summary_shows_pure_llm` |
| 2 | `agent.run()` returns a dict with all `NoteCompletenessOutputSchema` fields populated | ✅ | `test_agent_llm.py` 12 tests + smoke test #2 |
| 3 | RunTrace event has `backend_provider="icoder.pure-llm.v1"`, `backend_type="pure_llm"`, `provider_deterministic=False`, `supports_tool_calling=False` | ✅ | `test_invoke_emits_backend_metadata_event_with_all_fields` + smoke test #3 + browser walkthrough |
| 4 | Legacy regex fallback fires when LLM returns `status="fail"` | ✅ | `test_falls_back_to_legacy_on_llm_fail` + `test_falls_back_on_unparseable_llm_output` + `test_falls_back_to_legacy_on_llm_exception` + smoke test #1 |
| 5 | No regression in the other 3 runnable agents (`compliance-guardrail`, `code-validation`, `medical_coding`) | ✅ | `test_official_pack_loads_without_regression` parametrized test passes for all 4 |
| 6 | tsc 0 errors | ✅ | `npx tsc --noEmit` → 0 errors |
| 7 | Frontend `BackendProviderSummary` renders with real data | ✅ | Browser walkthrough — all 8 fields visible in screenshot `phase4b_walkthrough.png` |

---

## 10. What's NOT Done (Phase 4-C+ scope)

1. **Streaming** — `LLMGatewayAdapter.stream()` raises `NotImplementedError`. `LLMGateway` doesn't expose streaming today (`LLMService.chat_stream()` is deprecated). Phase 4-C adds SSE when the first agent needs it (likely Code Validation, ~12s latency).

2. **Code Validation Agent migration** — Still uses `RuleEngineProvider` (Phase 4-A skeleton). Migration to `LLMWithToolsProvider` is Phase 4-C scope.

3. **Compliance Guardrail Agent migration** — Still uses `RuleEngineProvider`. Phase 4-D scope.

4. **`LLMWithToolsProvider` real tool-calling** — Phase 4-A shipped the skeleton. Phase 4-C wires real tool-call execution (verify/guidelines/explore/search MCP tools).

5. **A2A agent card description update** — The chat page header shows "纯确定性 regex 检测，无 LLM" from `app/icoder/agent_runtime/a2a/agent_card.py`. Should pull from pack description or update the hardcoded string. Tracked as Phase 4-C cleanup.

6. **System prompt extraction** — The Chinese prompt is inlined in `agent.py::SYSTEM_PROMPT`. Phase 4-C can extract to `system_prompt.md` for editing without code changes.

7. **A/B validation** — The legacy regex fallback fires whenever the LLM returns unparseable output. In dev mode (MockLLMProvider), this is always the case. Production A/B validation against real DeepSeek is a separate ops task after Phase 4-B.

8. **`production_ready` flag** — Pack still declares `production_ready: false`. Flipping to `true` requires A/B validation + latency benchmarking + cost analysis. Phase 4-C+ scope.

---

## Appendix A — Files Touched

**Production code (7 files):**
- `backend/icoder_runtime/backends/llm_gateway_adapter.py` (new, 157 LOC)
- `backend/icoder_runtime/backends/pure_llm_provider.py` (edit, +60 LOC)
- `backend/icoder_runtime/backends/registry.py` (edit, +30 LOC)
- `backend/app/main.py` (edit, +3 LOC)
- `backend/official_agents/note_completeness/agent.py` (new, 383 LOC)
- `backend/official_agents/note_completeness/agent_legacy.py` (renamed, 142 LOC)
- `backend/official_agents/note-completeness/agent_pack.json` (edit, +10/-5)

**Test code (5 files):**
- `backend/tests/unit/icoder/backends/test_llm_gateway_adapter.py` (new, 201 LOC)
- `backend/tests/unit/icoder/backends/test_pure_llm_provider_backend_metadata.py` (new, 222 LOC)
- `backend/tests/unit/icoder/note_completeness/test_agent_llm.py` (new, 341 LOC)
- `backend/tests/unit/icoder/note_completeness/__init__.py` (new, 0 LOC)
- `backend/tests/unit/icoder/backends/test_pure_llm_provider.py` (edit, +40 LOC)
- `backend/tests/unit/icoder/backends/test_agent_pack_backend_schema.py` (edit, +30 LOC)

**Documentation (1 file):**
- `docs/architecture/agent_backend/PHASE4B_NOTE_COMPLETENESS_LLM_MIGRATION_REPORT.md` (this file)

**Evidence (1 file):**
- `docs/architecture/agent_backend/phase4b_walkthrough.png` (screenshot)

---

## Appendix B — Implementation Order

1. ✅ Step 1 — `LLMGatewayAdapter` (new file, 157 LOC)
2. ✅ Step 2 — `PureLLMProvider` real-LLM wiring + `emit_backend_metadata_event`
3. ✅ Step 3 — Registry `gateway_lookup` + `app.main.py` wiring
4. ✅ Step 4 — Rename regex `agent.py` → `agent_legacy.py`
5. ✅ Step 5+6 — New LLM `agent.py` + Chinese system prompt (383 LOC)
6. ✅ Step 7 — Update `note-completeness/agent_pack.json`
7. ✅ Step 8 — Tests (3 new + 2 extended, 36 new tests, 213 total pass)
8. ✅ Step 9 — Browser walkthrough (Playwright MCP, screenshot saved)
9. ✅ Step 10 — This report

**Total elapsed:** ~3 hours (single session, including 1 context compaction).
