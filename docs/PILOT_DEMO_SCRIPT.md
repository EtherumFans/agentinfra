# Pilot Demo Script — 10-Minute Coding Review Walkthrough

**版本**: v1.0-pilot
**日期**: 2026-05-12
**目的**: 医院试点演示标准化脚本
**时长**: 10 分钟 (±2 分钟缓冲)

---

## 演示前置条件

- [ ] 后端服务已启动 (`cd backend && uvicorn app.main:app --reload`)
- [ ] 前端服务已启动 (`cd frontend && npm run dev`)
- [ ] Demo cases + gold cases 已导入 (`cd backend && python -m app.seed`)
- [ ] 浏览器已打开 `http://localhost:5173`
- [ ] 已登录 (任意 demo 账号)
- [ ] Console 无红色报错

---

## 流程总览

```
[0:00-1:00]  场景说明 + 导入 demo case
[1:00-2:30]  运行 Coding Review
[2:30-4:00]  查看 Runtime State + Audit Trail
[4:00-5:30]  查看 Evidence 证据链
[5:30-7:00]  查看 Coding Candidates 候选编码
[7:00-8:30]  Human Review 人工复核
[8:30-9:30]  Audit / Export 审计与导出
[9:30-10:00] 演示能力 vs 未上线能力说明
```

---

## Step 1: 场景说明 + 导入 Demo Case (0:00–1:00)

**演示者口述**:

> "今天演示的是 iCoDer 智能编码审核系统。我们使用一个真实的出院病例
> (DEMO-001，肿瘤内科，诊断为 Z51.102 恶性肿瘤化疗) 来展示完整的编码审核闭环。"

**操作**:

1. 打开终端，执行:
   ```bash
   cd backend && python -m app.seed
   ```
2. 确认输出: `Demo cases: 10 encounters, 10 gold cases seeded`
3. 说明: "系统已预置 10 个试点病历，覆盖 4 个科室。"

**屏幕展示**: 终端输出 (5 秒)

---

## Step 2: 运行 Coding Review (1:00–2:30)

**演示者口述**:

> "现在我们对 DEMO-001 运行完整的 9 步编码审核 Pipeline。
> Pipeline 会依次调用 Evidence Extraction → ICD Diagnosis →
> Procedure Coding → Homepage → DRG → Report 等专家 Agent。"

**操作**:

1. 导航到 `CodingWorkbenchPage` (点击侧边栏 "编码工作台")
2. 在 Review Queue 搜索框输入 "DEMO-001"
3. 选择 DEMO-001 进入 Workbench
4. 点击 **"Run Review"** 按钮

**屏幕展示**:

- 进度条显示 Pipeline 各步骤 (Evidence → Diagnosis → Procedure → Homepage → Verify → DRG → Report)
- 约 10–15 秒后显示完成状态
- Runtime State Badge 显示绿色 "已归档"

---

## Step 3: 查看 Runtime State (2:30–4:00)

**演示者口述**:

> "每次 Coding Review 都由 Deterministic Runtime 管控。
> Runtime 是 5 层安全框架的核心，记录完整的状态流转和护栏决策。"

**操作**:

1. 点击 **Audit** tab
2. 依次展示 5 个子面板:

| 子面板 | 展示内容 | 说明 |
|--------|---------|------|
| 摘要 | `event_counts`: 各类型审计事件数量 | 展示事件总量 |
| 状态流转 | INGESTED → CONTEXT_READY → … → ARCHIVED | 完整状态路径 |
| 警告 | `warnings` 列表 (通常为空时说明无异常) | 展示无高危警告 |
| 事件分布 | `guard_outcomes`: ALLOW / REVIEW / DENY 各几条 | 展示护栏工作状态 |
| 决策 | `human_confirmations`: DUC 项确认/拒绝 | 展示人机协同 |

**屏幕展示**: Audit tab 5 个子面板 (1.5 分钟)

---

## Step 4: 查看 Evidence 证据链 (4:00–5:30)

**演示者口述**:

> "iCoDer 为每个编码建议提供证据链绑定 —— 不是黑盒输出，
> 而是把证据片段直接标注在病历原文上，编码员可以追溯验证。"

**操作**:

1. 点击 **Evidence** tab
2. 展示 `diagnosis_facts` 列表:
   - 每个 fact 包含: `term`, `code`, `source_text`, `confidence`
3. 展示 `procedure_facts` 列表
4. 点击某个 fact 的 source_text，高亮对应病历原文位置

**屏幕展示**: Evidence tab，重点展示证据可追溯 (1.5 分钟)

---

## Step 5: 查看 Coding Candidates 候选编码 (5:30–7:00)

**演示者口述**:

> "Pipeline 输出诊断编码和手术编码候选列表，每个候选都带有置信度、
> 规则校验结果和 DRG 影响分析。"

**操作**:

1. 点击 **Candidates** tab
2. 展示诊断编码候选列表:
   - 列: 编码 / 名称 / 置信度 / 规则校验 / 证据计数
   - 高亮主要诊断 (金色边框)
3. 展示手术编码候选列表
4. 点击 **DRG** tab，展示 DRG 入组影响分析

**屏幕展示**: Candidates tab + DRG tab (1.5 分钟)

---

## Step 6: Human Review 人工复核 (7:00–8:30)

**演示者口述**:

> "AI 输出的编码建议必须经过编码员复核确认。这是 Human-in-the-Loop 环节，
> 编码员可以确认、拒绝或修正 AI 建议。"

**操作**:

1. 点击 **"Human Review"** 按钮，跳转到 `CaseReviewPage`
2. 展示编码候选列表，每个编码前面有 Accept/Reject/Modify 按钮
3. 对一个编码点击 "Modify"，输入修正后的编码
4. 点击 "Confirm Decision"
5. 展示 Decision Summary shield 面板:
   - 总决策数 / 通过数 / 拒绝数
   - Guard outcomes (确认哪些 DUC 操作)
   - Runtime 强制二次确认的 DUC 项 (如 `confirm_decision`)

**屏幕展示**: CaseReviewPage + Decision Summary (1.5 分钟)

---

## Step 7: Audit / Export 审计与导出 (8:30–9:30)

**演示者口述**:

> "复核完成后，完整审核记录可以导出为 JSON，供质控部门归档。
> 审计链不可篡改，满足医保核查要求。"

**操作**:

1. 返回 CodingWorkbenchPage
2. 点击 **Export** 按钮
3. 下载 `review-{id}.json` 文件
4. 打开文件，展示包含内容:
   - `pipeline_id`, `encounter_id`
   - `diagnosis_candidates`, `procedure_candidates`
   - `evidence` (全部事实 + source_text)
   - `audit_trail` (事件时间线)
   - `decision_summary` (复核决策)
   - `drg_impact` (DRG 影响)

**屏幕展示**: 下载的 JSON 文件结构 (1 分钟)

---

## Step 8: 能力说明 (9:30–10:00)

**演示者口述**:

> "以上是 iCoDer 当前已完成并可直接演示的能力。下面说明哪些能力在当前版本中
> 尚未上线，这些将在后续批次迭代中交付。"

### 当前可演示能力

| 能力 | 状态 | 说明 |
|------|------|------|
| 9 步 Coding Review Pipeline | ✅ 可用 | Evidence → Diagnosis → Procedure → Homepage → DRG → Report → Human Review |
| Deterministic Runtime + 5 层安全框架 | ✅ 可用 | State Machine + Tool Gates + DUC + Audit Chain + HITL |
| Evidence 证据链绑定 | ✅ 可用 | 编码建议→病历原文可追溯 |
| Code Dictionary 查询 (33K+ 编码) | ✅ 可用 | ICD-10-CN + ICD-9-CM-3 |
| Coding Rule Engine | ✅ 可用 | 诊断/手术编码规则校验 |
| DRG/DIP 分组 | ✅ 可用 | 基于 OpenDRG CHS-DRG 1.1 |
| Human Review + Decision Summary | ✅ 可用 | 编码员复核 + 决策记录 |
| Audit Chain + Export | ✅ 可用 | 不可篡改审计链 + JSON 导出 |

### 未上线能力 (后续批次)

| 能力 | 状态 | 计划 |
|------|------|------|
| 自动编码替代编码员 | ❌ 不可用 | 本系统定位为 **审核辅助**，不替代编码员 |
| 医保拒付预测 (生产可用) | ❌ 不可用 | 模型已集成，但无真实赔付数据校准 |
| 真实 DRG 收益量化 | ❌ 不可用 | 需积累 ≥ 500 份真实 DRG 住院病例 |
| 临床诊断建议 | ❌ 不可用 | 系统不提供诊断决策 |
| 多院泛化 | ❌ 不可用 | 当前仅单院试点验证 |
| 语音实时编码 (STT) | ❌ 技术预览 | WebSocket 通道未打通 |
| 实时 Runtime Dashboard | ❌ 不可用 | 仅后端 API，无前端监控面板 |
| A2A Agent 协同 | ❌ 不可用 | 仅后端注册，无业务调用 |
| Billing / 收费项校验 | ❌ 不可用 | 未在本期范围 |
| CI/CD 自动化部署 | ❌ 不可用 | 无 GitHub Actions |
| 前端单元测试 / E2E | ❌ 不可用 | 测试框架已装，测试用例待补充 |

---

## 演示结束

**预计总时长**: 10 分钟
**缓冲**: ±2 分钟用于操作延迟或深入提问
**关键信息**: 审核辅助 → 证据可追溯 → 人机协同 → 审计合规
