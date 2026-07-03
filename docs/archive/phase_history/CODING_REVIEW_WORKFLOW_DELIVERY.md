# Coding Review Workflow — 最终交付文档

**日期**: 2026-05-12
**范围**: 审计摘要、复核决策摘要、Runtime↔UI 映射、WebSocket 进度、导出、E2E

---

## 1. 新 Workflow 图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CODING REVIEW WORKFLOW (完整闭环)                     │
│                                                                              │
│  CodingWorkbenchPage                              CaseReviewPage             │
│  ────────────────────                              ──────────────             │
│                                                                              │
│  ┌──────────────┐    Search encounters     ┌──────────────────┐             │
│  │ Review Queue │◄─────────────────────    │ Encounter List   │             │
│  │  (搜索病历)   │                         │ (待审核病历列表)   │             │
│  └──────┬───────┘                         └──────────────────┘             │
│         │ Select encounter                                                  │
│         ▼                                                                   │
│  ┌──────────────┐    [Async+WS] checkbox                                    │
│  │ Workbench    │───□ Async+WS                                              │
│  │ Header       │                                                           │
│  │              │                                                           │
│  │ [Run Review] │──── POST /api/reviews ────► Orchestrator.run_pipeline()   │
│  │              │          │                    │                            │
│  │              │          │ sync mode          │ Runtime + Audit            │
│  │              │          │ ◄── result ────────┘                            │
│  │              │          │                                                │
│  │              │          │ async mode         ┌─────────────────┐         │
│  │              │          │ WS /ws/reviews/    │ TaskManager      │         │
│  │              │          │ ◄── progress ──────│ (background)     │         │
│  └──────┬───────┘          │                    └─────────────────┘         │
│         │                  │                                                │
│  ┌──────┴────────────────┐ │                                                │
│  │ Tab Bar               │ │                                                │
│  │ [Evidence][Candidates] │ │                                                │
│  │ [Report] [DRG] [Audit]│ │                                                │
│  └──────┬────────────────┘ │                                                │
│         │                  │                                                │
│  ┌──────┴──────┐           │                                                │
│  │ Audit Tab   │◄── GET /api/runtime/summary/{review_id}                   │
│  │             │           │                                                │
│  │ • State     │           │                                                │
│  │   Timeline  │           │                                                │
│  │ • Guard     │           │                                                │
│  │   Outcomes  │           │                                                │
│  │ • Event     │           │                                                │
│  │   Counts    │           │                                                │
│  │ • Warnings  │           │                                                │
│  └─────────────┘           │                                                │
│                            │                                                │
│  ┌──────────────┐          │         ┌──────────────────────┐              │
│  │ [Export] btn │──────────┼────────►│ Download review.json │              │
│  └──────────────┘          │         └──────────────────────┘              │
│                            │                                                │
│  ┌──────────────┐          │                                                │
│  │[Human Review]│──────────┼────────► /review/{id}                          │
│  └──────┬───────┘          │              │                                 │
│         │                  │              ▼                                 │
│         │                  │    ┌──────────────────────┐                   │
│         │                  │    │ CaseReviewPage       │                   │
│         │                  │    │                      │                   │
│         │                  │    │ • Code candidate     │                   │
│         │                  │    │   review (confirmed/ │                   │
│         │                  │    │   rejected/modified) │                   │
│         │                  │    │                      │                   │
│         │                  │    │ • Decision Summary   │── GET /api/runtime/│
│         │                  │    │   (Shield panel)     │   summary/{id}    │
│         │                  │    │   • Guard outcomes   │                   │
│         │                  │    │   • DUC decisions    │                   │
│         │                  │    │   • Reviewer log     │                   │
│         │                  │    └──────────────────────┘                   │
│         │                  │                                                │
│  ┌──────┴──────┐           │                                                │
│  │ Runtime     │           │    Legend:                                     │
│  │ State Badge │           │    ───────                                     │
│  │ [已归档]    │           │    ───► API call                               │
│  └─────────────┘           │    ····► Navigation                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. 修改页面

| 页面 | 改动 | 说明 |
|------|------|------|
| **CodingWorkbenchPage** | +Runtime state badge | Header 区域显示当前 Runtime 状态 (如"已归档"/"待人工复核") |
| | +Async+WS checkbox | 切换同步/异步模式，异步模式通过 WebSocket 接收进度 |
| | +Progress display | 异步模式蓝色进度条，逐步显示 pipeline 步骤 |
| | +Export 按钮 (onClick) | 导出 review 为 JSON 文件 (含 audit summary) |
| | +审计追踪 tab | 5 面板 (摘要/状态流转/警告/事件分布/决策) |
| | +Review queue | 搜索病历 + 选择进入工作台 |
| **CaseReviewPage** | +复核决策摘要 | Shield 面板: 总决策/通过/拒绝 + 护栏结果 |
| | +runtimeApi import | 加载 audit summary |
| **api.ts** | +runtimeApi | 9 个 Runtime API 端点客户端 (status/audit/summary/review/duc/stale/active/states) |
| | +9 TypeScript interfaces | RuntimeStatus, AuditSummary, DecisionSummary, etc. |

## 3. Runtime ↔ UI 状态映射

| Runtime State | UI Badge 颜色 | UI 中文标签 | 出现位置 |
|--------------|-------------|-----------|---------|
| INGESTED | gray | 已接收 | Workbench header |
| CONTEXT_READY | blue | 上下文就绪 | Workbench header |
| FACTS_EXTRACTED | indigo | 事实已提取 | Workbench header |
| CANDIDATES_READY | purple | 候选编码就绪 | Workbench header |
| RULES_VALIDATED | teal | 规则已验证 | Workbench header |
| REVIEW_REQUIRED | amber | 待人工复核 | Workbench + CaseReview |
| DECISION_CONFIRMED | emerald | 决策已确认 | Workbench + CaseReview |
| ARCHIVED | green | 已归档 | Workbench header |
| FAILED | red | 失败 | Workbench header |
| ESCALATED | orange | 已升级 | Workbench header |

## 4. 新增测试

| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `phase4-review-workflow.spec.ts` | 8 | E2E: review queue, run review, runtime badge, audit tab, export button, human review, decision summary, async+WS |

## 5. 全量后端测试

**149 passed, 0 failed, 0 warnings**

## 6. 当前剩余 P1/P2 技术债

### P1 — 阻塞 V1.0

| # | 项目 |
|---|------|
| P1-1 | WebSocket STT 不可用 (nginx proxy 缺 WebSocket upgrade) |
| P1-2 | 4/11 Expert 未在固定 pipeline (CDI/Denial/Audit/HCC) |
| P1-3 | 前端单元测试 0 (vitest 已配置但无组件测试) |
| P1-4 | CI/CD 不存在 (无 GitHub Actions) |
| P1-5 | E2E 测试需要运行中的后端 + 前端 (当前仅验证页面渲染不崩溃) |

### P2 — 可延后

| # | 项目 |
|---|------|
| P2-1 | A2A coordinate/chain 从未被业务调用 |
| P2-2 | guard_post 在 stream 路径无法做结构化验证 |
| P2-3 | runtime_state_sync 仅在 flush 时同步 (非实时) |
| P2-4 | Recovery 不恢复 in-memory AuditChain |
| P2-5 | Alembic 迁移未在 CI 中自动执行 |
| P2-6 | 导出仅 JSON，不支持 Markdown 文件下载 |
