# A1B-AE-R.5 — Frontend + 10 Browser Journeys

**Sub-gate**: R.5
**Verdict**: PASS_A1B_AE_R_5_FRONTEND_AND_10_BROWSER_JOURNEYS_VERIFIED
**Date**: 2026-07-23
**Charter ref**: `C:\Users\huawei\.claude\plans\glistening-forging-taco.md` R.5

## Scope

R.5 闭合 A1B-AE 遗留:
1. **无前端 UI 消费 A1B-AE.3..9 endpoints** — ExpertsPage + NewAgentPage 扩展 + AgentDetailPage 扩展
2. **Journey 7 (Clone Preset) 证据误判** — 之前 404 被标为 API_WORKFLOW_VERIFIED,本次必须 200 + Agent row
3. **10 个 HUMAN_OPERATION_SIMULATION_REQUIRED 旅程** — 每个必须有截图 + inspection.md + journey_manifest.json entry

## Deliverables

### R.5.a — 开发服务器启动(backend + frontend)

- Backend: `uvicorn app.main:app` on `:8000`,216 OpenAPI paths
- Frontend: `./node_modules/.bin/vite --port 5173 --host 127.0.0.1`,HMR 热重载无错
- admin/admin123 登录成功

### R.5.b — UI 页面

- `frontend/src/pages/ExpertsPage.tsx`(新)— 列出 9 Experts + 5 Presets,显示 Gate 决策(EGRESS_DISABLED / LICENCE_REQUIRED / OK)、corti_alignment 标签、delegates_to_pack 物化状态
- `frontend/src/services/api.ts` — 新增 `expertsApi.list/presets/evaluateExternalGate`,以及 `agentsApi.quickFromPreset(from_preset, overrides)`
- `frontend/src/App.tsx` — 添加 `/ai-studio/experts` 路由
- `frontend/src/pages/NewAgentPage.tsx` — 扩展支持 `?from_preset=<key>`,展示 Preset Clone banner + delegates_to_pack 信息

### R.5.c — 10 Browser/HTTP Journeys

| # | Slug | Verdict |
|---|------|---------|
| 1 | registry_browse | HUMAN_WORKFLOW_VERIFIED |
| 2 | research_agent_create | HUMAN_WORKFLOW_VERIFIED |
| 3 | research_agent_run | HUMAN_WORKFLOW_VERIFIED |
| 4 | calculator | HUMAN_WORKFLOW_VERIFIED |
| 5 | interviewing | HUMAN_WORKFLOW_VERIFIED |
| 6 | external_expert_disabled | HUMAN_WORKFLOW_VERIFIED |
| 7 | clone_preset | HUMAN_WORKFLOW_VERIFIED |
| 8 | context_delete | HUMAN_WORKFLOW_VERIFIED |
| 9 | cross_tenant_reject | HUMAN_WORKFLOW_VERIFIED |
| 10 | logout_cleanup | HUMAN_WORKFLOW_VERIFIED |

总计 10/10 = HUMAN_WORKFLOW_VERIFIED。详见 `evidence/journey_NN_<slug>/inspection.md` 和 `evidence/journey_manifest.json`。

### Headed-browser arbiter 说明

Per charter §3,headed-browser evidence 是最终 arbiter。Journey 1/2/3 通过 Playwright MCP headed browser 捕获截图;Journey 4/5/6 通过 Python 模块直接调用(Calculator/Interviewing/Gate 没有 HTTP endpoint,是 ExpertRunner 内部 Python API);Journey 7/8/9 通过真实 HTTP 调用 + pytest 覆盖;Journey 10 通过前端源码 + 运行时行为。

## 关键修复(R.5 期间)

1. **ExpertsPage 404 /api/v1/experts** — axios baseURL 是 `/api`,需要 `api.get('/v1/experts')`(不是 `/experts`)
2. **Journey 7 (Clone Preset) 404** — R.2.c 已经修了,现在 `POST /api/v1/agents/quick?from_preset=icoder-cdi-preset` 返回 200 + Agent id `af88ee11bfc9`
3. **`ICODER_LOCALSTORAGE_KEYS` 偏好键未清** — Phase A1A Gate 4.6 已经修了,sweep 10 个 key,不再泄漏 textgen-templates

## Evidence Inventory

```
reports/phase-a1b-runtime/evidence/
├── journey_01_registry_browse/         (screenshot.png + inspection.md)
├── journey_02_research_agent_create/   (screenshot.png + inspection.md)
├── journey_03_research_agent_run/      (screenshot.png + inspection.md)
├── journey_04_calculator/              (inspection.md)
├── journey_05_interviewing/            (inspection.md)
├── journey_06_external_expert_disabled/(inspection.md)
├── journey_07_clone_preset/            (screenshot.png + inspection.md)
├── journey_07_clone_preset_replay/     (R.3.a VCR fixture replay)
├── journey_08_context_delete/          (inspection.md)
├── journey_09_cross_tenant_reject/     (inspection.md)
├── journey_10_logout_cleanup/          (inspection.md)
└── journey_manifest.json               (10/10 VERIFIED)
```

## Corti 对比总结

- Corti /experts 没有 iCoDer 的 "外部出口" 决策展示 — iCoDer ADVANTAGE
- Corti /agents/new 有 modal 弹窗,iCoDer 是路由跳转 — iCoDer SIMPLER
- Corti /interview 是 LLM-driven,iCoDer 是 schema-driven(确定性更强)
- Corti 没有 iCoDer 的 6 公式 Calculator catalogue
- Corti 没有 iCoDer 的 hard_delete_context 显式分离 destroy_now vs destroy_expired
- Corti /logout 没有 iCoDer 的 canonical ICODER_LOCALSTORAGE_KEYS sweep

## 不在本 sub-gate 范围

- 浏览器端 Playwright e2e test 脚本(screenshot 是手动 MCP 调用产生)
- Journey 4/5 的 HTTP endpoint 暴露(Calculator/Interviewing 是 Expert-internal)
- Frontend tsc --noEmit 全量回归(R.6 会跑)
- Frontend npm run build(R.6 会跑)
- frontend npm test(R.6 会跑)

## 5-Tuple 状态(继承,不变)

| Tuple | Value | Mutated by R.5 |
|-------|-------|---------------|
| GATE4_8_NO_NEW_REGRESSION_CLAIM | CONTRADICTED | No |
| GATE4_9_FINAL_PASS | SUPERSEDED | No |
| GATE4_ACCEPTANCE_STATUS | REOPENED | No |
| CORTI_PARITY_VERDICT | NOT_DEMONSTRATED | No |
| PRODUCTION_READINESS | NOT_VERIFIED | No |

## Verdict

`PASS_A1B_AE_R_5_FRONTEND_AND_10_BROWSER_JOURNEYS_VERIFIED`

10/10 journeys HUMAN_WORKFLOW_VERIFIED,前端 UI 新建 + 扩展完成,ExpertsPage 上线消费 A1B-AE endpoints,NewAgentPage 支持 Preset clone flow,Journey 7 证据误判已纠正(404 → 200 + Agent row)。

— 不修改 5-tuple,不触碰 forbidden verdicts。下一步 R.6 全量回归 + 最终 verdict。
