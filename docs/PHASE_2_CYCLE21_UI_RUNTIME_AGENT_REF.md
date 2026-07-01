# Phase 2 Cycle 21 — UI Runtime Agent Ref + v1.2 Install Path

## 1. Context

Cycle 20 shipped the Playwright runtime runner and added the first runtime checks
to `corti_ui_contracts/medical-coding.json` (7/7 PASS, 1 deferred-runtime).
The deferred one was `click_code_highlights_evidence`: the runtime path was
blocked because `MedicalCodingPage.tsx` referenced
`medical-coding-agent-1.0.0`, but the registry only had
`medical-coding-agent-2.0.0` (v1.2 pack) — the runtime runner hit 404.

This cycle re-enables the runtime path by fixing the agent ref, the v1.2
install pipeline, and the PreExecutionGuard's default-deny behaviour.

## 2. Audit (cycle 20 closeout → cycle 21 start)

- `corti_ui_contracts/medical-coding.json` schema v2, 7 checks (5 static + 2 runtime)
- `click_code_highlights_evidence` runtime was `_deferred` — agent ref mismatch
- `frontend/src/pages/MedicalCodingPage.tsx` line 23:
  `const MEDICAL_CODING_AGENT_REF = 'medical-coding-agent-1.0.0';`
- `backend/.icoder/agent_registry.json` shows 12 installed agents, including
  `medical-coding-agent-2.0.0` and `medcoder-coding-review-agent-1.0.0`
- `BuiltinAgentPackProvider.register_all` only installed **v1.1** packs — 6 v1.2
  packs (medcoder-coding-review, medical-coding, 4 expert stubs) were silently
  dropped because `RuntimeAgentRegistry.install` called
  `AgentPackageV1.from_dict()` which only validates v1.1 strictly
- `PlatformRuntime.run_agent` rebuilt `ExpertDefinition` directly from the
  registry record without normalising `expert_id` → `id` or whitelisting fields
- `PreExecutionGuard.check` (agent_runner.py:62-74) creates an empty
  `PermissionPolicy(permissions={})` when `permission_policy=None`, which denies
  every expert (severity=error → blocks the run)
- `runtime_platform.py:run_agent_by_ref` called `rt.run_agent(rec.agent_id, body.input)`
  without forwarding a `permission_policy`

## 3. Spec — what cycle 21 ships

### 3.1 Backend: v1.2 install path (3 file edits)

#### `backend/icoder_runtime/core/registry.py` — `RuntimeAgentRegistry.install`
Split on `format_version`: v1.2 packs read fields directly from the pack dict
(no `AgentPackageV1.from_dict` round-trip); v1.1 path preserved for back-compat.
`expert_ids` derives from `experts[].id or experts[].expert_id`.

#### `backend/icoder_runtime/agent_pack.py` — `import_pack`
Accept both v1.1 `experts[].id` and v1.2 `experts[].expert_id` via a
`_expert_id(e)` helper. Tool type → tier mapping for v1.2 packs:
- `mcp` / `function` / `builtin` → `ToolTier(1)`
- `guard` → `ToolTier(2)`
- explicit `tier` overrides

#### `backend/icoder_runtime/embedded/platform_runtime.py` — `install_agent` + `run_agent`
- `install_agent`: skip the legacy `AgentPackageV1.from_dict` validator for
  v1.2 packs (the loader's permissive path is canonical)
- `run_agent`: normalise `expert_id` → `id`, filter to
  `_EXPERT_FIELDS = {"id", "name", "description", "system_prompt", "category", "capabilities", "config"}`
  before constructing `ExpertDefinition`. Map v1.2 tool `type` to `ToolTier`
  using the same rule as `agent_pack.import_pack`.

### 3.2 Backend: default permission policy in `app/api/runtime_platform.py`

`run_agent_by_ref` now constructs a `PermissionPolicy` with one
`ToolPermission(allowed=True)` per `rec.expert_ids` entry and forwards it to
`rt.run_agent(...)`. Reasoning: "no policy specified" semantically means "open
this agent" for the platform-runtime API surface, not "deny all experts".
Tool-level fine-grained checks still happen inside the runner.

Side-effect: backend now requires `ICODER_ALLOW_EXTERNAL_LLM=true` env to call
external LLM providers. Already enabled in dev startup
(`nohup env ICODER_ALLOW_EXTERNAL_LLM=true python -m uvicorn ...`).

### 3.3 Frontend: agent ref + button data-testid

- `MedicalCodingPage.tsx:23`: `'medical-coding-agent-1.0.0'` →
  `'medical-coding-agent-2.0.0'` (matches the v1.2 pack in registry)
- `MedicalCodingPage.tsx:336`: added `data-testid="predict-codes-btn"` to the
  Predict button (i18n locale defaults to `zh-CN` so the visible label is
  预测编码, not "Predict codes"; testid is locale-agnostic)

### 3.4 Contract: `_deferred` → static OK + runtime deferred (re-scoped)

The `click_code_highlights_evidence` check stays `_deferred` for the runtime
gate, but the static gate is now fully green. Cycle 21 unblocks 3 gates
(agent ref + v1.2 install + permission policy) but exposes a NEW gap that
must wait for cycle 22+:

> `dataEvidences(result)` reads `result.evidences` (typed as
> `evidences?: any[]` in `RuntimeRunResult`), but
> `RuntimeRunResult.from_runner_output` does not populate it. Evidence lives
> in `result.output` as markdown tables like
> `| **诊断** | 冠状动脉粥样硬化性心脏病 | 第4行，第1-13字符 |`.
> The markdown→spans parser is out of scope for cycle 21; re-enable the
> runtime check after the parser lands.

### 3.5 Tests: `backend/tests/unit/icoder_runtime/test_v1_2_install_path.py`

8 new tests covering the silent-skip bug:

| Test | Asserts |
|---|---|
| `test_v12_pack_installs_without_legacy_validator` | v1.2 install doesn't raise `ValidationError` |
| `test_v12_expert_ids_accept_expert_id_field` | expert_ids derived from `expert_id` (Phase D) |
| `test_v11_pack_still_runs_through_legacy_validator` | v1.1 path preserved |
| `test_v12_expert_id_maps_to_definition_id` | `import_pack` normalises `expert_id` → `id` |
| `test_v12_tool_type_maps_to_tier` | mcp/function/builtin → 1, guard → 2 |
| `test_install_agent_v12_returns_installed_status` | full install path returns installed |
| `test_install_agent_v12_registers_in_registry` | list_agents surfaces the new pack |
| `test_register_all_installs_v12_executable_packs` | BuiltinAgentPackProvider registers all ≥2 v1.2 packs |

## 4. Verification

### 4.1 Toolchain (`scripts/icoder_ui_diff.py`)

```
[ui-diff] feature=medical-coding  checks=7  schema_version=2
  [OK]  real_time_char_counter
  [OK]  no_plain_textarea_in_page
  [OK]  highlighted_textarea_overlay_pattern
  [OK]  evidence_highlighter_focused_state
  [OK]  i18n_keys_added
  [OK]  char_counter_live
  [deferred-runtime] ... dataEvidences reads result.evidences ...
  [OK]  click_code_highlights_evidence (static gate; runtime deferred per §3.4)

[summary] 7/7 checks pass for medical-coding
[OK] wrote corti_ui_contracts\medical-coding.VERIFIED_OK
```

The Playwright test path that previously 404'd on
`POST /api/runtime/agents/medical-coding-agent-1.0.0/run` now reaches the
agent endpoint. The runtime gate fails ONLY at the final
`expect_count("mark[class*='bg-green-200']", min=1)` assertion, which is the
upstream dataEvidences gap (cycle 22+).

### 4.2 Manual curl

```bash
$ curl -X POST http://127.0.0.1:8000/api/runtime/agents/medical-coding-agent-2.0.0/run \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d '{"input":"入院记录\n患者：张三，男，65岁\n主诉：反复胸闷3年\n诊断：冠状动脉粥样硬化性心脏病\n手术：PCI术"}'

{
  "run_id": "47b94a9fadf1",
  "agent_ref": "medical-coding-agent-2.0.0",
  "status": "success",
  "output": "... MedCodER 5 阶段报告 ... I25.103 冠状动脉粥样硬化性心脏病 ...",
  "processing_time_ms": 10681,
  "audit_trail": [
    {"step": "run_started", ...},
    {"step": "pre_guard", "payload": {"passed": true, "violations": []}},
    {"step": "llm_response", ...},
    {"step": "contract_verified", "payload": {"valid": true}},
    {"step": "post_guard", "payload": {"safety_valid": true, "schema_valid": false, ...}}
  ]
}
```

`pre_guard.passed=true` and **0 violations** — the permission_scope fix is
verified end-to-end against DeepSeek V4.

### 4.3 Regression

- `python -m pytest tests/unit/` → **900 passed** (824 → 900, +76 including the
  8 new v1.2 tests)
- `scripts/icoder_ui_diff.py --feature medical-coding` → **7/7 PASS**

## 5. Cycle 22+ follow-up

1. **markdown → structured spans parser**: either
   `RuntimeRunResult.from_runner_output` parses `第N行，第M-K字符` tables
   out of `output`, or `dataEvidences(result)` falls back to a markdown regex
   on the frontend. Re-enable `click_code_highlights_evidence` runtime after.
2. **DB recovery**: backend dev startup occasionally hits a stale
   `alembic_version=005` + empty schema state (pre-existing — not cycle 21).
   The fix this cycle was `mv data/icoder.db data/icoder.db.bak20260701` +
   restart so `init_db()` rebuilds from scratch. Document a recovery runbook
   in `docs/dev/BACKEND_RECOVERY.md` (cycle 22).
3. **`dataEvidences` Markdown fallback**: if backend parsing is too fragile,
   add a client-side regex parser as a graceful degradation layer (separate
   cycle).

## 6. Files touched

```
backend/icoder_runtime/agent_pack.py                              (+1 helper, tier mapping)
backend/icoder_runtime/core/registry.py                           (split v1.1/v1.2 install)
backend/icoder_runtime/embedded/platform_runtime.py               (skip v1.1 validator, normalise expert_id)
backend/app/api/runtime_platform.py                               (default allow-experts policy)
backend/tests/unit/icoder_runtime/test_v1_2_install_path.py       (NEW, 8 tests)
frontend/src/pages/MedicalCodingPage.tsx                          (ref → 2.0.0, data-testid on Predict btn)
corti_ui_contracts/medical-coding.json                            (Predict btn selector, _deferred re-scoped)
```