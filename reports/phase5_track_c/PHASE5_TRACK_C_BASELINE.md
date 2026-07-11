# Phase 5 Track C — Baseline

**Track**: Corti Agent Runtime 复刻、Orchestrator 主链与产品工作台重构
**Start date**: 2026-07-11
**Baseline commit**: `e4a6a30` (Phase 5 Track B-2 Phase 11 final summary)
**Predecessor**: Phase 5 Track B-2 (`PASS_ALL_RUNNABLE_AGENTS_DEEPLY_VALIDATED_WITH_GAPS`)
**Successor target**: Phase 5 Track C verdict `READY_FOR_FORMAL_QUALITY_BENCHMARK` (PDF §17)

---

## 1. 起点 (Per PDF §0 + §1)

Phase 5 Track B-2 完成 9 个 runnable agent 的真实运行实证，verdict `PASS_ALL_RUNNABLE_AGENTS_DEEPLY_VALIDATED_WITH_GAPS`。**WITH_GAPS 限定**：
- 1 P0: CP2 LLMWithToolsProvider SKELETON
- 15 P1: 8× unified API 结构化 gap + 7× orchestrator wiring gap
- 10 P2 + 6 P3

Track C 目标：将 iCoDer 从"一组相互独立、部分只能输出 Markdown 的 Agent"，重构为"底层运行机制与 Corti 一致、由 Orchestrator 动态调度 Expert、Tool 和专业子能力，并具备中国医院安全边界的医疗编码 Agent 系统"。

---

## 2. 工作树状态 (Per PDF §1)

```
Branch: master (ahead of origin/master by 32 commits)
Working tree: clean
HEAD: e4a6a30 docs(phase5-b2): Phase 11 summary — 9 agents deeply validated + 32 gap backlog
```

Recent commits (15):
```
e4a6a30 docs(phase5-b2): Phase 11 summary — 9 agents deeply validated + 32 gap backlog
a72cd2c feat(phase5-b2): CP9 drg-analyzer + Corti compliance/guidelines similar-agents
b61dab7 feat(phase5-b2): CP8 discharge-summary-structuring + Corti CDI similar-agent
4cbb4e4 feat(phase5-b2): CP7 principal-diagnosis-review + Corti similar-agent directive
ee03434 feat(phase5-b2): CP6 evidence-extractor deep walkthrough → READY_FOR_INTERNAL_SHADOW
959841d feat(phase5-b2): CP5 procedure-extractor deep walkthrough → READY_FOR_INTERNAL_SHADOW
dc3e578 feat(phase5-b2): CP4 note-completeness-agent deep walkthrough → READY_FOR_INTERNAL_SHADOW
277ad65 feat(phase5-b2): CP3 compliance-guardrail-agent deep walkthrough → READY_FOR_INTERNAL_SHADOW
0fe5dd3 feat(phase5-b2): CP2 code-validation-agent deep walkthrough → METADATA_ONLY
ea14f0c feat(phase5-b2): CP1 medical-coding-agent deep walkthrough + 11-step validation
d62113f chore(phase5-b2): per-agent run runner + token cache helper
c2bda85 fix(phase5-b2): AUDIT_BLOCKER_FIX #2 — agentRun() normalizes agent_ref to short agent_id
28457b6 fix(phase5-b2): AUDIT_BLOCKER_FIX Hub agent fallback in AgentDetailPage
f03859a fix(phase5-b2): unify new-agent CTA + i18n prebuilt tab
945b467 feat(phase5-b2): baseline + 12 synthetic fixtures + dev env verified
```

---

## 3. 当前代码审计 (Per PDF §1)

### 3.1 Orchestrator code (`backend/app/icoder/agent_runtime/orchestrator/`)

15 modules, ~4100 LOC:
| File | LOC | Role |
|---|---|---|
| `__init__.py` | 169 | Public exports |
| `state_machine.py` | 125 | 5-state machine (received → planning → delegating → aggregating → completed/failed) |
| `planner.py` | 393 | Plan generation (per memory 2026-06-20) |
| `delegator.py` | 271 | Sub-agent dispatch |
| `aggregator.py` | 252 | Result merge |
| `inbound_handler.py` | 577 | A2A inbound + orchestration entry |
| `run_trace.py` | 469 | Trace events |
| `run_context.py` | 67 | Run context object |
| `recorder_adapter.py` | 410 | Recorder wiring |
| `metrics.py` | 279 | Metrics |
| `phi_redactor.py` | 189 | PHI redaction |
| `prompts.py` | 173 | Planner prompts |
| `events.py` | 21 | Event types |
| `errors.py` | 78 | Error types |
| `wiring.py` | 399 | DI wiring |

**Status**: 代码存在但 runtime 没有把 9 个 agent 编排起来（per CP3-CP9 §26a evidence）。

### 3.2 Backend providers (`backend/icoder_runtime/backends/`)

7 modules, ~3200 LOC:
| File | LOC | Status |
|---|---|---|
| `pure_llm_provider.py` | 502 | **Real** (lazy-resolves LLMGateway) |
| `llm_with_tools_provider.py` | 760 | **SKELETON** by default (no `llm_client` wired — see `__init__` line 90-98 + lazy-resolve missing) |
| `rule_engine_provider.py` | 426 | **Real** (MedicalCodingRuleSet 12 rules) |
| `llm_gateway_adapter.py` | 228 | Adapter (LLMGateway ↔ LLMClient interface) |
| `tool_mcp_compat_layer.py` | 441 | MCP tool dispatch |
| `contracts.py` | 407 | Interfaces |
| `registry.py` | 417 | Provider registry + lazy gateway lookup |

**Gate 1 P0**: `LLMWithToolsProvider` constructed in `registry.py:397` with no args, so `llm_client=None`, falls through to `_skeleton_pipeline`. PureLLMProvider has `_resolve_client()` (line 343-364) that lazy-resolves gateway — `LLMWithToolsProvider` lacks this method.

### 3.3 Agent packs (`backend/official_agents/`)

30 packs (15 dash-separated + 15 underscore_separated duplicates). 9 runnable per B-2:
- medical-coding-agent, code-validation-agent, compliance-guardrail-agent, note-completeness-agent, procedure-extractor, evidence-extractor, principal-diagnosis-review, discharge-summary-structuring, drg-analyzer

### 3.4 API surface (audited per PDF §1)

- `backend/app/api/agent_run.py` — POST `/api/v1/agents/{id}/run` (unified facade per Phase 4-F2)
- `backend/app/api/main.py` — FastAPI app
- `backend/app/api/run_trace.py` — Trace endpoints
- `backend/app/api/usage.py` — Usage/cost endpoints

---

## 4. Gate 序列 + 提交计划 (Per PDF §2 + §14)

| Gate | Description | Commit |
|---|---|---|
| 0A | B-2 audit complete (DONE in B-2: CP8 + CP9) | (already committed) |
| 0B | Corti Orchestrator reverse engineering (browser) | `docs(track-c0): complete b2 audit and corti orchestrator reverse engineering` |
| 1 | Runtime contract repair (CP2 + StructuredOutputProjector) | `fix(track-c1): wire real llm and mcp tools into code validation` + `feat(track-c1): add shared structured output projector` |
| 2 | China business gates (Evidence + ICD-10-CN + Procedure Status + Negation + Principal Dx + Note Completeness) | `fix(track-c2): localize icd code validation and procedure evidence gates` |
| 3 | Corti-like Orchestrator kernel | `feat(track-c3): implement corti-compatible orchestrator kernel` |
| 4 | Coding compliance orchestrator mainline (7-stage) | `feat(track-c4): add coding compliance orchestration mainline` |
| 5 | Agent-specific UI workbenches (9) | `feat(track-c5): add agent-specific medical review workbenches` |
| 6 | Trace + A2A + Embedded integration | `feat(track-c6): add parent-child trace a2a discovery and embedded integration` |
| 7 | Browser walkthrough + final verdict | `docs(track-c): final architecture and browser parity report` |

**Total**: 9 commits

---

## 5. Gate rules (Per PDF §2)

- Gate 0 未通过 → 不得凭推测设计 Orchestrator
- Gate 1 未通过 → 不得让 Orchestrator 调用不可信子 Agent
- Gate 2 未通过 → 不得把结果交给合规和 DRG/DIP 链路
- Gate 3 未通过 → 不得宣称复刻了 Corti Runtime
- Gate 4 未通过 → 不得宣称多 Agent 编排完成
- Gate 5 未通过 → 不得宣称产品体验完成
- Gate 6 未通过 → 不得宣称第三方可集成

每个 Gate 通过后才进入下一个。

---

## 6. Dev env state

- Backend: `http://127.0.0.1:8000/api/health` → healthy, provider=deepseek, medcoder_index_ready=true
- Frontend: `http://localhost:3002` → serving
- Chrome: Playwright MCP available
- Corti session: 已登录（per memory 2026-07-05+）

---

## 7. Track C scope summary

| Section | Description |
|---|---|
| **必做** | Gate 0-7 全 8 gates + 9 commits |
| **禁做** (per PDF §13) | 模型训练 / 270 例质量评测 / 准确率 F1 正式裁决 / 大量新 Agent / Marketplace / DAG Builder / 自动生产写回 / 真实患者数据 / npm 正式发布 |
| **裁决目标** | `READY_FOR_FORMAL_QUALITY_BENCHMARK` (PDF §17) |

---

## 8. B-2 → Track C 待补完成项

PDF §3 列出 B-2 应补完的 CP8 + CP9 — **已在 B-2 commit b61dab7 + a72cd2c 完成**：
- `reports/phase5_track_b2/agents/008_discharge_summary_structuring.md` ✓
- `reports/phase5_track_b2/agents/009_drg_analyzer.md` ✓

PDF §3.3 列出的 B-2 最终纠错报告 — **部分已在 Phase 11 commit e4a6a30 完成**：
- `PHASE5_TRACK_B2_FINAL_REPORT.md` ✓
- `PHASE5_TRACK_B2_EXECUTIVE_SUMMARY.md` ✓
- 缺：`PHASE5_TRACK_B1_CORRECTION.md`, `AGENT_CAPABILITY_MATRIX_B2.md`, `AGENT_UX_SCORE_REPORT_B2.md`, `AGENT_INTEGRATION_MATRIX_B2.md` (CSV 已生成但 .md 报告未写)

Track C Gate 0 会补齐这 4 份缺失报告。

---

## 9. 立即执行的下一步

1. **Gate 0A 完成**（B-2 CP8/CP9 已 done）
2. **Gate 0B 启动**：浏览器 Corti Orchestrator 逆向（experiments A-H per PDF §4.3）
3. **Gate 0 commit**：`docs(track-c0): complete b2 audit and corti orchestrator reverse engineering`

下一步在 Gate 0B 报告中执行。
