# M3-0 病案首页编码审核 Agent — 基础设施预检 (PRECHECK)

**日期**: 2026-06-10
**目的**: 摸清 iCoDer V3.0 现有真实路径, 确保 M3-0/M3-1 改动最小化、不破坏基础设施定位。
**结论**: 5 个文件级改动即可完成样板 Agent 产品化闭环, 不动 AgentRunner / Recorder / runtime_platform。

---

## 1. 当前真实 medical coding API 入口

| 路径 | 文件:行 | 说明 |
|---|---|---|
| **生产入口** | `backend/app/api/runtime_platform.py:549-603` | `medical_coding_test()` — POST `/api/runtime/medical-coding/test` |
| **adapter** | `runtime_platform.py:585-589` | `HybridCodingAdapter(gateway=gateway, mode="hybrid", recorder=app.state.m2a_recorder)` |
| **降级** | `icoder_runtime/providers/medical_coding/{mock_adapter,prompt_llm_adapter,deepseek_coding_adapter}.py` | LLM_PROVIDER=mock 时走 mock_adapter |
| **旁路 (仅查码表)** | `backend/app/api/codes.py` | 不做 inference, 仅 dictionary/rule lookup |

**响应 shape**:
```json
{
  "primary_diagnosis": {...},
  "secondary_diagnoses": [...],
  "run_id": "...",
  "trace_id": "...",
  "trace_url": "/api/m2a/runs/..."
}
```

**唯一入口** (无平行路径): `runtime_platform.py` 是 canonical, 不存在第二条 medical-coding 推理链。

---

## 2. 当前 AgentRunner 实际调用路径

| 步骤 | 文件:行 | 函数 |
|---|---|---|
| PlatformRuntime.run_agent | `backend/icoder_runtime/embedded/platform_runtime.py:120+` | `run_agent(agent_id, input)` |
| Agent 解析 | `icoder_runtime/agents/registry.py` | `RuntimeAgentRegistry.resolve(agent_id)` |
| AgentRunner.run | `backend/icoder_runtime/agent_runner.py:250-293` | `run(agent, user_input, permission_policy, data_policy, delegated_by)` |
| 入口守卫 | `agent_runner.py:317` | `PreExecutionGuard.check()` |
| LLM 调用 | `agent_runner.py:389` | `LLMGateway.generate()` |
| 出口守卫 | `agent_runner.py:444` | `PostExecutionGuard.check()` |
| 安全 spiral | `agent_runner.py:449` | `SafetySpiralDetector.record()` |
| **RepairLoop** | **缺失** | 当前一-shot 调用, M3 需在 L392-L444 之间插入 (~30 行) |

**AgentPackageV1 入口**: `icoder_runtime/agents/agent_package.py` — `.icoder-agent` 包格式 + 校验。

---

## 3. 当前 RunTraceService 接入点

| 接入点 | 文件:行 | 说明 |
|---|---|---|
| M2aRecorder.inference (context manager) | `icoder_runtime/m2a/recorder.py:58-101` | 顶层 run trace 入口 |
| _InferenceContext.stage | `recorder.py:114-136` | 单 tool_call 等价 stage |
| **真实使用样例** | `runtime_platform.py:596-601` | 医疗编码 test 路由从 `m2a_recorder._last_finalized` 读 run_id/trace_id/trace_url |
| **AgentRunner 内部使用** | `agent_runner.py:281-303` | `with self._recorder.inference(agent_ref=...) as _inf_ctx: with _inf_ctx.stage("pre_execution_guard") as _s:` |

**模式**: 任何新 Agent 必须用相同 pattern (recorder.inference → ctx.stage) 才能产出可追溯 run trace。

---

## 4. 当前 M2b 样本路径

```
data/m2b/deidentified/
  m2b_smoke_20.json                      (M2b-0)
  m2b_smoke_eval_20.jsonl               (M2b-1, 20 例 smoke)
  m2b_eval_50.json                       (M2b-0)
  m2b_smoke_eval_50.jsonl                (M2b-1, 50 例 eval)
  m2b_full_candidate_pool_1800.jsonl     (M2b-1, 1800 例)
  m2b_high_risk_coding_points.jsonl      (M2b-1, 62 高风险码)
data/m2b/validated/
  REVIEW_REQUIRED.md                     (M2b-2 状态公开)
  m2b_eval_50_validated.jsonl            (M2b-2 empty placeholder)
  manifest.json                         (M2b-2 gold_evidence_available=false)
```

**4 个核心 M2b 路径已确认**: smoke_20 / eval_50 / full_1800 / high_risk_coding_points。

---

## 5. 当前前端页面入口

| 页面 | 文件 | 用途 |
|---|---|---|
| Medical Coding 推理 | `frontend/src/pages/MedicalCodingPage.tsx` | 主推理 UI |
| Agent 列表 | `frontend/src/pages/AgentsPage.tsx` | Studio 入口 |
| Agent 详情 | `frontend/src/pages/AgentDetailPage.tsx` | 单 Agent 配置 |
| Runtime Console | `frontend/src/pages/RuntimeConsolePage.tsx` | Run Trace 入口 |
| Evaluation | `frontend/src/pages/EvaluationPage.tsx` | 评估指标 |
| Routing | `frontend/src/App.tsx:61/70/78` | 3 个主要 Route |

**CodingReviewWorkbenchPage 不存在** — 需要新增。组件目录 `frontend/src/components/{medical-coding,layout,common,...}` 已存在, 新增 `icoder/` 子目录。

---

## 6. 本轮最小改动方案 (5 个文件)

| # | 路径 | 改动 | 行数 |
|---|---|---|---:|
| 1 | `backend/official_agents/homepage-coding-review/agent_pack.json` | **新增** manifest | ~50 |
| 2 | `backend/official_agents/homepage-coding-review/__init__.py` | **新增** agent 入口 (delegates to existing medical_coding agent + 标记 homepage_review) | ~30 |
| 3 | `backend/app/api/icoder_coding_review.py` | **新增** 3 个 API: `POST /run`, `POST /{run_id}/human-review`, `GET /{run_id}/report` | ~280 |
| 4 | `backend/icoder_runtime/reports/coding_review_report.py` | **新增** 报告生成器 (HTML, 18 节, 含 disclaimer) | ~250 |
| 5 | `backend/app/main.py` | **修改** `app.include_router(icoder_coding_review.router)` 1 行 | +1 |
| 6 | `frontend/src/pages/CodingReviewWorkbenchPage.tsx` | **新增** 三栏布局 Workbench | ~400 |
| 7 | `frontend/src/components/icoder/{EvidenceViewer,HighRiskCodingPointPanel,RunTraceTimeline}.tsx` | **新增** 3 组件 | ~600 |
| 8 | `frontend/src/components/embed/{IcoderReviewPanel,IcoderEvidenceViewer,IcoderTraceViewer}.tsx` | **新增** 3 嵌入式组件 | ~400 |
| 9 | `frontend/src/pages/EmbedDemoCodingReviewPage.tsx` | **新增** embed 演示 | ~80 |
| 10 | `frontend/src/App.tsx` | **修改** +2 Route | +2 |
| 11 | `tests/test_services/test_m3_homepage_coding_review.py` | **新增** 测试 | ~250 |
| 12 | `docs/M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC.md` | **新增** Agent 规格 | ~150 |
| 13 | `docs/ICODER_M3_SECURITY_AND_AUDIT_SPEC.md` | **新增** 权限审计 | ~200 |
| 14 | `docs/M3_HOMEPAGE_CODING_REVIEW_AGENT_DELIVERY_REPORT.md` | **新增** 交付报告 | ~250 |

**总: 14 个文件 (13 新增 + 2 修改)**。**不动**: AgentRunner / M2aRecorder / RuntimePlatform / 现有前端页面。

---

## 7. 关键边界 — 严格遵守

| 红线 | 说明 |
|---|---|
| **不伪造** | 无 prediction file / 无 B0 baseline / 无人工证据 / 无 DRG/DIP 真实分组器 → 必返回 `status=unavailable, degraded=true, manual_review_required=true` |
| **不破坏 iCoDer 定位** | Agent 是**样板**, 不是 iCoDer 的全部产品; iCoDer 仍是 Agent 开发/运行基础设施 |
| **不训练** | 不启 SFT, 不改 B0 训练流程 |
| **不写入生产** | 所有 sample / validation 数据 `production_allowed=false` (硬性) |
| **不冒充模型效果** | pipeline validation 模式 报告 disclaimer 必含 |
| **不破坏 M2a/M2b** | 全量回归 886 passed 不动 |

---

**预检结束**, 进入 M3-0/M3-1 实施。
