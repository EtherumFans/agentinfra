# Phase 4-C — Code Validation Agent Testing Report

**Status:** PASS — 301 targeted + 1053 full sweep, 0 regressions
**Date:** 2026-07-08

---

## 1. Test matrix (13 categories per plan §Phase 6)

| # | Category | File | Tests | Status |
|---|----------|------|-------|--------|
| 1 | LLMResponse with tool_calls | `tests/unit/icoder/backends/test_pure_llm_provider.py` (existing, extended) | 11 | ✅ |
| 2 | Adapter threads tools | `tests/unit/icoder/backends/test_llm_gateway_adapter.py` (existing) | — | ✅ |
| 3 | DeepSeek parses tool_calls | `tests/unit/icoder/backends/test_llm_gateway_adapter.py` (existing) | — | ✅ |
| 4 | _real_llm_pipeline basic | `tests/unit/icoder/backends/test_llm_with_tools_provider_real.py` (new) | 6 | ✅ |
| 5 | Multi-round loop | same | (covered in #4) | ✅ |
| 6 | max_tool_rounds triggers fallback | same | (covered in #4) | ✅ |
| 7 | LLM exception fallback | same | (covered in #4) | ✅ |
| 8 | Backend metadata w/ tool_rounds | same | (covered in #4) | ✅ |
| 9 | verify_code extended | `tests/unit/icoder/mcp/test_verify_code_extended.py` (new) | 7 | ✅ |
| 10 | get_guidelines | `tests/unit/icoder/mcp/test_get_guidelines.py` (new) | 6 | ✅ |
| 11 | explore_code | `tests/unit/icoder/mcp/test_explore_code.py` (new) | 7 | ✅ |
| 12 | search_codes | `tests/unit/icoder/mcp/test_search_codes.py` (new) | 6 | ✅ |
| 13 | Code Validation v2 integration + prompt injection refusal | `tests/unit/icoder/agent_runtime/test_code_validation_v2.py` (new) | 6 | ✅ |
| 14 | ToolMCPCompatLayer round_index/caller forwarding (bonus) | `tests/unit/icoder/backends/test_tool_mcp_compat_layer.py` (extended) | +1 | ✅ |
| 15 | Frontend v2 fallback markdown | `frontend/src/utils/__tests__/medicalCodingMarkdown.test.tsx` (new) | 2 | ✅ |

**Total new:** 34 backend + 2 frontend = 36 tests
**Total targeted sweep (Phase 4-C scope):** 301 passed

## 2. Mock strategy

### 2.1 Backend — `_ScriptedLLMClient`

`tests/unit/icoder/backends/test_llm_with_tools_provider_real.py:104-122`

```python
class _ScriptedLLMClient:
    """LLM client that pops items from a script list (LLMResponse or Exception)."""
    def __init__(self, script: list[Any]):
        self.script = list(script)
        self.calls: list[dict] = []

    async def complete_messages(self, *, messages, tools, temperature, max_tokens, timeout_seconds):
        self.calls.append({"messages": messages, "tools": tools, "temperature": temperature})
        if not self.script:
            raise RuntimeError("script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, LLMResponse):
            raise TypeError(...)
        return item
```

Each test case constructs a script of `LLMResponse(text=..., tool_calls=[...])` items (or `Exception` instances) and asserts the pipeline produces the expected `BackendResponse(status, tool_calls, tool_rounds, ...)`.

### 2.2 Backend — `_make_provider` helper

`tests/unit/icoder/backends/test_llm_with_tools_provider_real.py:124-165`

Returns `(provider, llm_client, dispatch_calls, dispatch_kwargs)`:
- `dispatch_calls: list[tuple[str, dict]]` — `(tool_name, arguments)` per dispatch
- `dispatch_kwargs: list[dict]` — `{run_id, round_index, caller}` per dispatch (Phase 5 wiring assertions)

Stub `fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs)` accepts the new `round_index` + `caller` kwargs and captures them for assertions.

### 2.3 Backend — `_LLM_HAPPY_MARKDOWN` canned response

`tests/unit/icoder/agent_runtime/test_code_validation_v2.py`

A pre-baked JSON response with 2 `validated_codes` (one PASS, one WARNING) + 1 `cross_code_issue` (EXCLUDES1_CONFLICT). Used to feed `_make_mock_provider({"message": {"parts": [{"kind":"text","text":_LLM_HAPPY_MARKDOWN}]}})` and verify `agent.run()` parses it into `CodeValidationOutputV2` correctly.

### 2.4 Frontend — markdown fallback

`frontend/src/utils/__tests__/medicalCodingMarkdown.test.tsx` — 2 tests:
- `_fallbackCodeValidationV2` happy path: full v2 JSON (4 fields + 2 validated_codes + 1 cross_code_issue) → assert markdown contains Review Conclusion / Validated Codes table / Cross-Code Issues table
- Empty edge case: only `review_conclusion` + `manual_review_required` → assert no tables rendered

## 3. Test case details (Phase 4-C new tests)

### 3.1 `_real_llm_pipeline` (6 tests)

| Test | Script | Asserts |
|------|--------|---------|
| `test_real_pipeline_one_tool_round` | [tool_call(verify_code, I25.10), final_text("# Status: pass")] | status="pass", 1 tool_call, tool_rounds=1, dispatch_kwargs[0].round_index=0, caller="llm" |
| `test_real_pipeline_multi_round` | [tc(I25.10), tc(R07.9), tc(I25.5), final_text("# Status: warning")] | status="warning", 3 tool_calls, tool_rounds=3, round_index=[0,1,2] |
| `test_real_pipeline_max_rounds_exceeded` | 4× tc + max_tool_rounds=3 | status="incomplete", finish_reason="max_tool_rounds_exceeded:3", 3 tool_calls |
| `test_real_pipeline_llm_exception_fallback` | [RuntimeError("boom")] | status="fail", 0 tool_calls, fallback_used=True |
| `test_real_pipeline_emits_backend_metadata_with_tool_rounds` | [final_text("pass")] | `emit_backend_metadata_event` called with tool_rounds=0 |
| `test_real_pipeline_final_output_parsing` | 8 status keyword cases | "# Status: pass"→"pass", "warning"→"warning", "fail"→"fail", ""→"unknown", etc. |

### 3.2 `verify_code` extended (7 tests)

- `test_verify_code_assignable_leaf_code` — "I50.900" → in_catalog=True, assignable=True, parent_hierarchy=[chapter_no, category_code, "I50.900"]
- `test_verify_code_non_assignable_category` — "I25" → in_catalog=True, assignable=False, children_if_non_assignable non-empty (top 20)
- `test_verify_code_unknown_code_no_children` — "XYZ123" → in_catalog=False, all empty
- `test_verify_code_excludes_and_notes_empty_forward_compat` — excludes1/2 + code_first_notes + use_additional_code_notes are [] (Phase 4-C empty slots)
- `test_verify_code_aliases_top_10_synonyms` — aliases capped at 10
- `test_verify_code_parent_hierarchy_format` — [chapter_no, category_code, code]
- `test_verify_code_children_if_non_assignable_sorted` — children sorted by code for determinism

### 3.3 `get_guidelines` (6 tests)

- `test_get_guidelines_returns_chapter_conventions` — chapter 9 (循环系统疾病) has conventions
- `test_get_guidelines_returns_general_rules` — at least 5 general rules returned
- `test_get_guidelines_unknown_chapter` — unknown chapter → empty chapter_conventions, general_rules still present
- `test_get_guidelines_no_code_arg` — `code=None` → chapter="", general_rules present
- `test_get_guidelines_source_is_internal_kb` — `source="internal_kb"`
- `test_get_guidelines_chapter_conventions_count` — at least 7 chapters in CHAPTER_CONVENTIONS dict

### 3.4 `explore_code` (7 tests)

- `test_explore_code_returns_parent_for_leaf` — "I50.900" → parent.chapter non-empty
- `test_explore_code_returns_siblings_for_category` — "I25" → siblings non-empty (same chapter_no + category_code)
- `test_explore_code_returns_children_for_category` — "I25" → children non-empty
- `test_explore_code_unknown_code` — "XYZ123" → in_catalog=False, all empty
- `test_explore_code_in_catalog_for_leaf` — leaf code → in_catalog=True
- `test_explore_code_in_catalog_for_category` — category code → in_catalog=True
- `test_explore_code_children_sorted` — children sorted by code

### 3.5 `search_codes` (6 tests)

- `test_search_codes_aliases_search_icd_handler` — same handler reference
- `test_search_codes_query_normalized_to_emr_text` — `{"query":"胸痛"}` → handler called with `{"emr_text":"胸痛"}`
- `test_search_codes_emr_text_legacy_param` — `{"emr_text":"胸痛"}` → handler called with same
- `test_search_codes_query_takes_precedence` — `{"query":"q1","emr_text":"e1"}` → `emr_text="q1"`
- `test_search_codes_empty_query` — `{"query":""}` → empty result
- `test_search_codes_top_k_default_5` — `top_k` defaults to 5 if omitted

### 3.6 Code Validation v2 integration (6 tests)

- `test_v2_happy_path` — mock LLM returns `_LLM_HAPPY_MARKDOWN` → `agent.run()` returns `CodeValidationOutputV2` with `review_conclusion="WARNING"`, 2 validated_codes, 1 cross_code_issue
- `test_v2_legacy_fallback_on_llm_fail` — mock LLM raises RuntimeError → fallback to `agent_legacy.run_legacy_with_corti_schema()` → returns v2 shape with `LEGACY_RULE` cross_code_issues
- `test_v2_legacy_fallback_on_unparseable_output` — mock LLM returns "garbage text" → fallback kicks in
- `test_v2_empty_input_returns_fail` — empty coding_set → FAIL + INPUT-001 issue, no LLM call
- `test_v2_prompt_injection_refusal` — coding_set contains "ignore previous instructions" → WARNING + PI-001, manual_review_required=True, no LLM call
- `test_v2_output_matches_pydantic_schema` — happy path result validates against `CodeValidationOutputV2` Pydantic model

### 3.7 Frontend v2 fallback markdown (2 tests)

- `renders validated_codes and cross_code_issues tables` — full v2 JSON → markdown contains 6 sections + 2 tables
- `handles empty validated_codes and cross_code_issues gracefully` — minimal v2 JSON → no tables rendered, no crash

## 4. Regression results

### 4.1 Full backend unit sweep

```bash
$ cd backend && python -m pytest tests/unit/icoder/ -q --tb=line
1053 passed, 90 warnings in 10.72s
```

**0 regressions.** 3 pre-existing failures from earlier in the session (test_agent_card English→Chinese name change) resolved by updating test assertions to expect Chinese names.

### 4.2 Targeted Phase 4-C sweep

```bash
$ python -m pytest tests/unit/icoder/backends/ \
    tests/unit/icoder/mcp/ \
    tests/unit/icoder/agent_runtime/test_code_validation_v2.py \
    tests/unit/icoder/agent_runtime/test_three_runnable_agents.py -v
301 passed, 79 warnings in 4.50s
```

### 4.3 Frontend

```bash
$ cd frontend && npx tsc --noEmit; echo exit=$?
exit=0

$ npx vitest run
Test Files  2 failed | 4 passed (6)
Tests  3 failed | 70 passed (73)
```

**3 frontend test failures are PRE-EXISTING** (not caused by Phase 4-C). Verified by `git stash` → run on master → same 3 failures. The 3 failures are in `src/services/__tests__/agentHubContract.test.ts` and `src/pages/__tests__/agentNavigationSmoke.test.tsx` — about Agent Hub navigation contract, unrelated to Phase 4-C scope.

**Frontend Phase 4-C new tests:**
```bash
$ npx vitest run src/utils/__tests__/medicalCodingMarkdown.test.tsx
Tests  2 passed (2)
```

## 5. Edge cases covered

### 5.1 LLM tool-calling edge cases

- ✅ LLM returns no text + no tool_calls (empty response) → status="unknown", finish_reason="empty_response"
- ✅ LLM raises mid-loop → status="fail", fallback_used=True, no partial tool_calls recorded
- ✅ `max_tool_rounds` hit without final text → status="incomplete", `_build_incomplete_markdown` synthesizes a fallback
- ✅ LLM returns degraded finish_reason (`"degraded_mock"`) → `fallback_used=True` in backend metadata
- ✅ Multi-round loop sees tool results (each `{"role":"tool",...}` message appended before next LLM call)

### 5.2 MCP tool edge cases

- ✅ `verify_code` on category code "I25" → `in_catalog=True, assignable=False, children_if_non_assignable=[top 20 subdivisions]`
- ✅ `verify_code` on unknown code "XYZ123" → `in_catalog=False`, all fields empty
- ✅ `get_guidelines` with no `code` arg → still returns general_rules
- ✅ `explore_code` on leaf code → siblings + children both empty (no subdivisions)
- ✅ `search_codes` with both `query` and `emr_text` → `query` takes precedence
- ✅ `search_codes` with empty `query` → empty result, no crash

### 5.3 Agent v2 edge cases

- ✅ Empty input (`coding_set=None` or no codes) → FAIL + INPUT-001 issue, no LLM call
- ✅ Prompt injection patterns (8 variants English + Chinese) → WARNING + PI-001, manual_review_required=True, no LLM call
- ✅ LLM exception → legacy fallback kicks in, returns v2 shape (lossy)
- ✅ LLM returns unparseable output → legacy fallback kicks in
- ✅ LLM returns valid JSON missing required fields → `_parse_llm_json_to_schema` raises → legacy fallback

### 5.4 PHI / safety edge cases (defense-in-depth, unchanged from prior phases)

- ✅ `dispatch_tool` PHI redaction layer (`test_mcp_log_redaction.py`) — no PHI in dispatch_detail or log
- ✅ `ToolMCPCompatLayer.call` strips secrets before dispatch (`test_call_strips_secrets_before_dispatch`) — `"api_key":"sk-leaked"` → `"[REDACTED]"` before reaching handler
- ✅ `verify_code` / `get_guidelines` / `explore_code` accept only `code` strings (no patient text)
- ✅ `search_codes` accepts `query` (potentially PHI-laden) but routes through `dispatch_tool` PHI redaction + retriever only returns code candidates (no text snippets)

## 6. Test infrastructure notes

### 6.1 Mock dispatch signature change (Phase 5)

Tests that stub `dispatch_tool` must now accept `**kwargs` because `ToolMCPCompatLayer.call` forwards `round_index` + `caller`:

```python
# OLD (broke after Phase 5 wiring):
async def fake_dispatch(tool_name, args, request, *, run_id=None):
    ...

# NEW (works):
async def fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
    ...
```

Updated in 5 test files: `test_llm_with_tools_provider_real.py`, `test_llm_with_tools_provider.py` (3 mocks), `test_tool_mcp_compat_layer.py` (3 mocks).

### 6.2 `DISPATCH_DETAIL_KEYS` set update

`tests/unit/icoder/mcp/test_dispatch_detail.py:110-118` — the expected key set now includes `"round_index"` + `"caller"`:

```python
DISPATCH_DETAIL_KEYS = {
    "tool_name", "dispatch_mode",
    "round_index", "caller",        # ← Phase 4-C new
    "handler_ref",
    "input_schema_validation", "phi_redaction",
    ...
}
```

### 6.3 `TOOL_REGISTRY` count update

`tests/unit/icoder/mcp/test_tool_registry.py:46` — expected count 8 → 11; expected set adds `get_guidelines` / `explore_code` / `search_codes`.

`tests/unit/icoder/mcp/test_server.py` — 3 tests updated: `test_tools_list_returns_5_tools` (8→11), `test_tools_list_accepts_empty_body` (8→11), `test_tools_call_unknown_tool_returns_32601` (used `sorted()` for alphabetical ordering of unstable set iteration).

## 7. Coverage gaps (honest)

### 7.1 Not covered by automated tests

- ❌ **End-to-end v2 A2A dispatch** — the `_handle_simple → validate_codes MCP tool → agent_legacy` path returns v1 shape (per plan decision #6). The v2 LLM path is reachable only via direct `agent.run()` invocation, which is covered by unit tests but NOT by an integration test that exercises the full HTTP path. **Follow-up:** add `tests/integration/icoder/test_code_validation_v2_a2a_dispatch.py` once the v2 dispatch wiring is added (see `PHASE4C_NEXT_OPTIMIZATION_PLAN.md` §1).
- ❌ **Real DeepSeek tool-calling** — all 6 `_real_llm_pipeline` tests use `_ScriptedLLMClient`. Real DeepSeek V4 function-calling reliability across 8 rounds is a runtime concern, not testable without API credits. **Follow-up:** add a `pytest.mark.live_llm` test gated on `ICODER_CREDENTIAL_LLM` env var.
- ❌ **Browser walkthrough screenshots** — Playwright MCP screenshot tool timed out at 5000ms (root cause unclear). **Follow-up:** investigate font-loading or CSS animation; re-run after `Phase 4-D` UI replication so the screenshots also serve as parity evidence.

### 7.2 Covered indirectly

- ✅ `LLMGatewayAdapter.complete_messages()` threads `tools` correctly — covered by existing `test_llm_gateway_adapter.py` tests (unchanged in Phase 4-C; the `tools` param was already accepted by `gateway.generate()`, Phase 4-C only added the response-side `tool_calls` parsing).
- ✅ DeepSeek response parsing — covered by existing `test_deepseek_*` tests in `test_llm_gateway_adapter.py`.
- ✅ `emit_backend_metadata_event` 9-field contract — covered by `test_run_trace_backend_metadata.py` (Phase 4-A, unchanged).

## 8. PASS verdict

- **13/13 categories PASS** (per plan §Phase 6 matrix)
- **1053/1053 backend unit tests pass** (0 regressions)
- **301/301 targeted Phase 4-C tests pass**
- **tsc 0 errors**, **2/2 new frontend tests pass**
- **3 pre-existing frontend failures** confirmed unrelated (Agent Hub navigation contract, not Phase 4-C scope)

Phase 4-C testing: **PASS**.
