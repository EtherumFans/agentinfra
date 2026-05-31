# Corti-Style Remediation Roadmap

**日期**: 2026-05-12
**基于**: CORTI_STYLE_GAP_ANALYSIS.md (10 维度评分)
**目标**: 4 个 Sprint，将 iCoDer 产品体验从 2.8/5 提升到接近 4.0/5

---

## Sprint A: Coding Workbench Ergonomics (P0)

**目标**: 让 CodingWorkbench 更像真实编码员工作台

### 前端改动

| 改动 | 说明 | 影响维度 |
|------|------|---------|
| **Evidence Panel 三区布局** | 强证据/弱证据/冲突证据 分区展示，颜色区分 | #2 Evidence-First |
| **Evidence → Code 连线** | 每个证据下展示关联的候选编码，点击跳转 | #2 Evidence-First |
| **Candidate Code Cards** | 从表格改为卡片，展示 confidence 颜色条 + evidence count + DRG impact badge + routing tier badge | #4 Candidate |
| **Confidence 颜色编码** | 绿(高≥0.80)/黄(中0.50-0.79)/红(低<0.50) | #4 Candidate |
| **Routing Tier Badge** | 每个候选旁显示 AUTO/REVIEW/ESCALATE 标签 | #7 Confidence |
| **Clinical Timeline 展示** | 时间轴组件，展示关键事件时间线 | #3 Reasoning |
| **Primary Diagnosis Reasoning Card** | 展示 why_selected/why_not_selected + rule_basis 引用 | #3 Reasoning |
| **Human Readable Summary** | 在 Report tab 或 Overview 区域展示 CaseReasoningReport 的中文摘要 | #10 Product Feel |

### 不做事项
- 不新增 Agent
- 不新增后端 cognitive module
- 不改 Pipeline 逻辑
- 不新增 API 端点

### 验收标准
- Evidence Panel 展示 top_supporting / weak / conflicting 三区
- Candidate Cards 替代表格，含 confidence 颜色 + routing badge
- Timeline 组件在前端渲染
- Primary Diagnosis Reasoning 以卡片形式展示
- Human Readable Summary 可见

---

## Sprint B: Human Review Cockpit (P1)

**目标**: 让 CaseReviewPage 达到 Corti-style 复核效率

### 前端改动

| 改动 | 说明 |
|------|------|
| **键盘快捷键** | A=Approve, R=Reject, M=Modify, Tab=下一个, Shift+Tab=上一个 |
| **批量操作** | 全选 checkbox + "全部确认"/"全部拒绝"按钮 |
| **Review Notes** | 文本输入框，支持保存到 human_reason |
| **修正原因标准化** | 下拉选项：编码错误/特异性不足(.9)/规则违反/证据不足/其他 |
| **AI vs Gold 对比面板** | 当 gold code 存在时展示分歧 |
| **Disagreement Type Badge** | 展示 8-type taxonomy 标签 |
| **"下一个未审核"跳转** | 快速导航到下一个未处理的候选 |
| **Decision Progress Bar** | 可视化复核进度 (N/M confirmed) |

### 不做事项
- 不新增 Agent
- 不新增后端 logic（Disagreement 已在后端）
- 不新增页面

### 验收标准
- 键盘快捷键可操作 Approve/Reject/Modify
- 批量操作可执行
- AI vs Gold 对比面板可见
- Disagreement type badge 可见

---

## Sprint C: Audit & Export Polish (P1)

**目标**: 让审计和导出真正可交付

### 改动

| 改动 | 说明 |
|------|------|
| **Export Markdown 格式** | 除 JSON 外增加 Markdown 报告导出 |
| **Export 包含 CaseReasoningReport** | 导出时整合 case_reasoning_report |
| **Audit Tab 编码员视图** | 增加"编码员摘要"视图（中文、非技术） |
| **Case Intake 增强** | 科室筛选 + 日期范围 + "最近处理"快速入口 |
| **Gold Case Import 前端入口** | GoldCasesPage 增加 CSV/JSON 上传按钮 |
| **Pilot Runbook 集成** | CodingWorkbench 增加"试点模式"toggle（简化界面） |

### 不做事项
- 不新增后端 API（已有 batch evaluation）
- 不新增 Agent
- 不新增 cognitive module

### 验收标准
- Export 产生 Markdown 文件
- Audit tab 有"编码员摘要"子面板
- GoldCasesPage 支持文件上传导入

---

## Sprint D: Clinical Cockpit Feel (P2, 可延后)

**目标**: 统一 visual language，减少"技术系统感"

### 改动

| 改动 | 说明 |
|------|------|
| **Clinical 色调统一** | 蓝/白/灰主色调，替换当前的混杂色板 |
| **中文术语替换** | confidence→可信度, candidate→编码建议, unsupported→证据不足, hallucination→异常编码 |
| **编码员引导文案** | 每个面板增加 1 行中文引导（"请核查以下证据是否支持编码建议"） |
| **Loading 状态优化** | Pipeline 运行时展示进度卡而非 spinner |
| **Error 状态优化** | 中文错误提示 + 建议操作 |
| **Empty 状态设计** | 无数据时的友好提示 |
| **Responsive 微调** | 确保 1366×768 以上可用 |
| **Notification 增强** | Review 完成通知 + 可直接跳转 |

### 不做事项
- 不改变页面结构
- 不新增功能

### 验收标准
- 中文术语统一
- Loading/Error/Empty 状态完善
- 引导文案到位

---

## 优先级矩阵

```
重要度 ↑
  P0  │  Sprint A (现在做)     │  Sprint B (下个 Sprint)
      │  Evidence-First UX     │  Human Review Cockpit
      │  Candidate Cards       │  Disagreement Display
      │  Timeline UI           │  Keyboard Shortcuts
      │  Reasoning Display     │
      │  Product Feel 基础     │
      ─────────────────────────┼──────────────────────────
  P2  │  Sprint D (延后)       │  Sprint C (随后)
      │  Visual Polish         │  Audit/Export Polish
      │  Clinical Tuning       │  Case Intake增强
      │  Copy/UX微调           │  Gold Import前端
      │                        │
      └────────────────────────┴──────────────────────────
        前端改动量小               前端改动量中
                            紧迫度 →
```

---

## 不做事项总览

以下能力明确不在本路线图中：

| 能力 | 原因 |
|------|------|
| 实时语音编码 (STT) | WebSocket 通道未打通，依赖外部 ASR |
| A2A Agent 协同 | 仅注册，无业务调用，需求不明确 |
| Billing / 收费校验 | 不在产品范围 |
| Runtime Dashboard (实时监控) | 属于运维平台，非编码员工具 |
| Workflow Builder | 属于配置平台，非编码员工具 |
| Agent Marketplace | 属于平台生态，非当前阶段 |
| Multi-tenant SaaS | 架构未支持 |
| Full Autonomous Coding | 安全设计不允许 |
| 医保拒付预测 (生产可用) | 无真实数据校准 |
| 多院泛化 | 样本不足 |

---

## 总体评估

### iCoDer 最接近 Corti 的地方
1. **Backend 推理引擎深度** — 5 条认知链 (Timeline/Reasoning/Evidence/Disagreement/Confidence) 是显著优势
2. **Runtime Safety** — 5 层安全框架 (State Machine/Duc/Audit/HITL) 可能超越 Corti 的公开水平
3. **Gold Case Validation** — 模板→导入→校验→仲裁→一致性→评估的完整闭环
4. **Pilot Documentation** — 演示脚本/验收清单/已知限制/问题模板/数据申请模板齐备

### 最大 10 个差距
1. Evidence-First UX 前端未实现
2. Coding Candidate 展示粗糙（表格化）
3. Product Feel 偏开发者工具
4. Clinical Timeline 前端不可见
5. Clinical Reasoning 展示不足
6. Routing Decisions 前端未消费
7. Disagreement Analysis 前端未展示
8. 无键盘快捷键
9. Export 仅 JSON
10. Human Readable Summary 未在前端渲染

### 下一轮最应该先做的 Sprint
**Sprint A: Coding Workbench Ergonomics** — 这是 P0 中最密集、影响最大的 Sprint，直接解决 Top 10 差距中的 #1, #2, #3, #4, #5, #7, #10。

### 哪些能力不应该现在做
- A2A / Billing / Dashboard / Workflow Builder / Agent Marketplace — 不在产品范围
- Full Autonomous Coding — 安全设计不允许，准确率不足
- Multi-tenant SaaS — 架构不匹配
- STT 实时编码 — 依赖未解决
