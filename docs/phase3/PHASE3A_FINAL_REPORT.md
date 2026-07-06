# Phase 3-A — Medical Coding Agent MVP Productization & Tech Debt Burn-down

**Date**: 2026-07-04
**Branch**: master
**Spec source**: `C:\Users\huawei\Downloads\deepseek_markdown_20260704_a593a0.md`
**Verdict**: **PASS**

## PHASE 3-A VERDICT: PASS — 7 sections complete, 1235 pytest passing, 7/7 health_check, 0 tsc errors, build OK, 54/54 vitest, MCP 5-tool smoke 200, Corti-style 8-field output contract wired end-to-end

## 1. Sections completed

| Section | Topic | Status | Spec doc |
|---|---|---|---|
| A | Baseline 只读审计 | ✅ COMPLETE | `docs/phase3/PHASE3A_BASELINE_AUDIT.md` |
| B | Tech Debt Burn-down (TD-001/002/004/005) | ✅ COMPLETE | `docs/phase3/PHASE3A_TECH_DEBT.md` |
| C | Medical Coding Agent 产品化 | ✅ COMPLETE | `docs/phase3/PHASE3A_MEDICAL_CODING_AGENT_SPEC.md` |
| D | Product UI/UX (MVP + AI-assisted banners + Review Summary) | ✅ COMPLETE | `docs/phase3/PHASE3A_PRODUCT_UI_UX_SPEC.md` |
| E | Runtime Integration (v1 → v2 projection) | ✅ COMPLETE | `docs/phase3/PHASE3A_RUNTIME_INTEGRATION_SPEC.md` |
| F | 4 Verification Rounds | ✅ COMPLETE | (this report) |
| G | Final Report | ✅ COMPLETE | (this report) |

## 2. Verification Round results (Section F)

| Round | Command | Result |
|---|---|---|
| 1 | `python -m pytest tests/test_api/ tests/unit/ tests/regression/ tests/e2e/icoder/ -q --tb=line` | **1235 passed, 1 skipped, 0 failed** in 107.83s (baseline 1230 + 5 new v2 projection tests) |
| 2 | `python scripts/health_check.py` | **7/7 PASS** — alembic_head, schema_drift (0 divergences / 33 tables / 473 cols), agents_installed (28), runtime_started, registry_sync, auth_register, auth_login |
| 3a | `cd frontend && npx tsc --noEmit` | **0 errors** |
| 3b | `cd frontend && npm run build` | **✓ built in 6.01s** |
| 4 | `cd frontend && npx vitest run src/` | **54/54 PASS** (apiContract 45 + locales 9) |
| (smoke) | MCP `/mcp/v1/tools/list` | **200 OK, 5 tools** (search_icd, verify_code, get_differentiation_hint, ...) |

No new failures. No regressions. No skips/xfails added. No assertions lowered.

## 3. What shipped

### 3.1 Tech Debt Burn-down (Section B)

- **TD-001**: Auth bypass fixture unified — `get_current_user` + `get_current_organization` both overridden via `_install_auth_bypass` autouse fixture under `ICODER_DISABLE_AUTH_FOR_TESTS=1`.
- **TD-002**: A2A idempotency guards — `mount_a2a` no-op on re-entry (TestClient lifespan re-runs across sessions). `app.state._a2a_mounted` flag.
- **TD-004**: InboundHandler redirect message updated to point at A2A mainline (Phase 2.1-A).
- **TD-005**: RuntimeAgentRegistry dual-lock (threading.Lock + filelock.FileLock) — cycle 25 locked in.

### 3.2 Medical Coding Agent productization (Section C)

- **Agent Pack rewrite** (`official_agents/medical_coding/agent_pack.json`):
  - `agent_ref: "icoder/medical-coding-agent@2.0.0"` (was @1.0.0)
  - Corti-style category slug `medical-coding` + display "Coding and Revenue Cycle / 编码与收入周期"
  - `maturity: mvp`, `production_ready: false`, `human_review: required`
  - 9 红线 in `permissions`: no_upcoding, no_inference, evidence_required, ...
  - Corti-style 7-step workflow in `system_prompt` (Synthesize Encounter → Extract Clinical Evidence → Search Coding Candidates → Assign Codes → Validate Coding → Identify Documentation Gaps → Generate Review Summary)
  - `output_contract.schema_ref: "icoder/MedicalCodingAgentOutputV2/v1"` with 8 required_fields
  - Internal engine reference: `icoder/medcoder-coding-review-agent@1.0.0` (5-stage MedCodER pipeline — implementation detail, not user-facing)
- **MedCodER pack downgrade** (`official_agents/medcoder-coding-review/agent_pack.json`):
  - `agent_type: "internal_engine"` (was `reference`) — new agent_type added to `LEGAL_AGENT_TYPES_V12` + `_classify()` in `agent_pack_loader.py`
  - `hidden_from_hub: true` — disappears from Hub UI
  - `category_display: "Internal Engine"`, `maturity: internal`
- **Schema v2** (`official_agents/medical_coding/schema.py` +270 lines):
  - 8 Corti-style dataclasses: `TraceRefs`, `EncounterSummary`, `DocumentationAnalysis`, `CodeAssignment`, `DocumentationGap`, `UncodableItem`, `ValidationSummary`, `HumanReview`
  - `MedicalCodingAgentOutputV2` class with `to_dict()` + `from_legacy_v1(legacy, run_id=...)` classmethod
  - `from_legacy_v1` projects v1 MedicalCodingOutputSchema → v2: gathers evidence from `extracted_diagnoses`, projects `issues_found` + `manual_review_required` → `ValidationSummary`, always sets `review_required=True` (MVP), passes through primary_diagnosis/secondary_diagnoses/procedures, builds `trace_refs` from `method_stage_trace` + `rule_fired`

### 3.3 Product UI/UX (Section D)

- **MVP + AI-assisted banners** (`MedicalCodingPage.tsx`):
  - Amber backdrop `bg-amber-50/60` for MVP banner — signals "not yet production-ready"
  - Blue backdrop `bg-blue-50` for AI-assisted banner — signals "human-in-the-loop"
  - Both `data-testid` attributes for e2e asserts
  - Corti red lines enforced: no "fully automated" language; no F1 / model effect display
- **Corti-style Review Summary panel** (8-field rendering):
  - Inserted at bottom of middle column (after DiagnosisCard section)
  - Renders all 8 Corti-style fields with severity color + placeholders when empty
  - v1 → Corti-style projection in the UI when v2 fields absent (back-compat until Section E wired)
- **i18n keys** (`frontend/src/i18n/locales.ts` +36 lines zh+en, +18 type def):
  - 16 new keys: mvpBanner, aiAssistedBanner, reviewSummary, reviewConclusion(+Pass/Warning/Fail), manualReviewRequired, uncodableItems, encounterSummary, traceRefs, noDocumentationGaps, noUncodableItems, rulesPassed, rulesFired, runId
  - 3 deprecated alias keys kept (medcoderPipeline/medcoderMode/enableMedcoder)
- **Type additions** (`frontend/src/types/runtime.ts` +45 lines):
  - 8 v2 fields on `RuntimeRunResult`: review_conclusion, manual_review_required, encounter_summary, documentation_gaps, uncodable_items, corti_validation_summary, human_review, trace_refs
  - `corti_validation_summary` (not `validation_summary`) to avoid TS2717 conflict with existing legacy field

### 3.4 Runtime Integration (Section E)

- **`/api/runtime/agents/{agent_ref:path}/run` restored for medical-coding-agent** (`runtime_platform.py` +90 lines):
  - `agent_ref == "icoder/medical-coding-agent@2.0.0"` → run `HybridCodingAdapter.infer_async` directly (bypassing `PlatformRuntime.run_agent` which raises NotImplementedError per Phase 2.1-A)
  - Project v1 → v2 via `MedicalCodingAgentOutputV2.from_legacy_v1()`
  - Return `RuntimeRunResult`-shaped response with v2 fields hoisted to top level
  - Other agent_refs → 410 Gone (Phase 2.1-A deprecation preserved)
  - `:path` modifier on `{agent_ref}` matches URL-encoded slashes from frontend `encodeURIComponent(agentRef)`
- **`/api/runtime/medical-coding/test` consistency**: also projects v1 → v2 (best-effort, never breaks v1 response)
- **5 new tests** (`tests/unit/app/api/test_runtime_platform_v2_projection.py` +185 lines):
  - `test_medical_coding_agent_run_returns_v2_fields`
  - `test_other_agents_still_410`
  - `test_empty_input_400`
  - `test_medical_coding_test_returns_v2_fields`
  - `test_v2_fields_always_present` (Corti contract — every field present with correct sub-shape)

### 3.5 Docstring refresh

- `official_agents/medical_coding/__init__.py` docstring updated: `@1.0.0` → `@2.0.0`, 4-step → 8-step Corti-style workflow, MVP maturity + 4 red lines documented
- `app/icoder/mcp/server.py` docstring: 5 tools back the Medical Coding Agent (icoder/medical-coding-agent@2.0.0, Corti-style); MedCodER 5-stage is the Agent's internal_engine

## 4. Files changed (Phase 3-A cumulative)

```
backend/official_agents/medical_coding/agent_pack.json          (Corti-style rewrite, ~190 LOC)
backend/official_agents/medical_coding/__init__.py              (+20 lines docstring)
backend/official_agents/medical_coding/schema.py                (+270 lines v2 schema)
backend/official_agents/medcoder-coding-review/agent_pack.json  (downgrade to internal_engine)
backend/icoder_runtime/core/agent_pack_schema.py                (+1 line: "internal_engine" in LEGAL_AGENT_TYPES_V12)
backend/icoder_runtime/core/agent_pack_loader.py                (+11 lines: internal_engine branch in _classify)
backend/tests/unit/icoder_runtime/test_agent_pack_loader.py     (5 lines: assert internal_engine branch)
backend/app/api/runtime_platform.py                             (+90 lines: /run restore + v2 projection + :path + /medical-coding/test v2 projection)
backend/app/icoder/mcp/server.py                                (docstring refresh)
backend/tests/unit/app/api/test_runtime_platform_v2_projection.py  (+185 lines, 5 new tests)

frontend/src/i18n/locales.ts                                    (+36 lines zh+en, +18 type)
frontend/src/types/runtime.ts                                   (+45 lines v2 fields)
frontend/src/pages/MedicalCodingPage.tsx                        (+104 lines: banners + Review Summary panel)
frontend/src/components/medical-coding/DiagnosisCard.tsx        (comment refresh)
frontend/src/components/medical-coding/EvidenceHighlighter.tsx  (comment refresh)

docs/phase3/PHASE3A_BASELINE_AUDIT.md                            (Section A spec)
docs/phase3/PHASE3A_TECH_DEBT.md                                 (Section B spec)
docs/phase3/PHASE3A_MEDICAL_CODING_AGENT_SPEC.md                 (Section C spec)
docs/phase3/PHASE3A_PRODUCT_UI_UX_SPEC.md                       (Section D spec)
docs/phase3/PHASE3A_RUNTIME_INTEGRATION_SPEC.md                 (Section E spec)
docs/phase3/PHASE3A_FINAL_REPORT.md                             (this report — Section G)
```

## 5. Constraints honored

- ✅ No skip/xfail/test deletion/assertion lowering — all 1235 tests passing on their own merits
- ✅ No model training / F1 optimization / Stage 1 / Stage 4 / rerank / few-shot
- ✅ MedCodER appears only in implementation details / `internal_engine` / technical note (not as product main name)
- ✅ Final verdict is PASS or FAIL with required format

## 6. Out of scope (deferred to Phase 3-B+)

- `encounter_summary` field is empty (runtime doesn't synthesize chief_complaint/treatment_course/key_findings yet — needs LLM synthesis step or EncounterSynthesizer expert)
- `documentation_gaps` and `uncodable_items` are empty lists (runtime doesn't classify gaps yet — needs Stage 5 enhancement)
- A2A InboundHandler response shaping (currently A2A returns v1-shaped parts; v2 projection can be lifted into shared helper if needed)
- 17 Pre-built Agents (Phase 3-C+)
- Real A2A task flow between Agents (Phase 2.2+)

## 7. Corti red lines enforced

1. ✅ No "fully automated" language — system_prompt + UI banners explicit about MVP / human_review=required
2. ✅ No F1 / model effect display — UI does not show confidence as F1; banners do not claim model accuracy
3. ✅ No upcoding — `permissions.no_upcoding: true` in agent_pack.json
4. ✅ No inference — `permissions.no_inference: true`; every code requires evidence span
5. ✅ No field omitted — Corti contract: all 8 v2 fields always present in API response (placeholders render when empty)
6. ✅ No back-compat breakage — v1 fields preserved unchanged; v2 is pure addition
7. ✅ No deprecation reversed — Phase 2.1-A's 410 Gone preserved for non-Medical-Coding agents
8. ✅ No auth bypass in production — `ICODER_DISABLE_AUTH_FOR_TESTS=1` only honors conftest, not middleware (cycle 25 audit locked in)
9. ✅ MedCodER as implementation detail — never the product name; only "Medical Coding Agent" faces users

## 8. Verdict

**PHASE 3-A VERDICT: PASS** — 7/7 sections complete. 1235/1/0 backend tests. 7/7 health_check. 0 tsc errors. Build OK. 54/54 vitest. MCP 5-tool smoke 200. Corti-style 8-field output contract wired end-to-end (v1 schema → v2 projection → API response → frontend Review Summary panel). No new features added beyond spec scope. No regressions. No constraints violated.
