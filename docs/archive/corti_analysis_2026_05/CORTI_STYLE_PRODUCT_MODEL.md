# Corti-Style ICD Coding Agent — 产品范式拆解

**日期**: 2026-05-12
**来源**: 公开产品资料 + Corti Embedded Assistant 分析 + iCoDer 逆向工程
**声明**: 本文基于公开可获取的 Corti 产品范式和交互逻辑进行功能级推断，不包含 Corti 私有代码、商标、品牌资产或内部实现细节。

---

## 1. 产品流程图

```
                    ┌─────────────────────────────────────────────┐
                    │            Corti-Style Coding Agent          │
                    └─────────────────────────────────────────────┘

  Case Intake          Evidence Extraction       Timeline/Patient Journey
  ───────────          ───────────────────       ────────────────────────
  病历文本输入    →    结构化事实提取         →    按时间排列临床事件
  (EMR/手动/语音)     (diagnosis + procedure)       (手术→化疗→复查→出院)


  Candidate Generation       Evidence-Grounded Suggestion
  ────────────────────       ────────────────────────────
  ICD-10候选人列表     →    每个编码绑定证据片段
  (含confidence/rule)        点击编码→高亮原文对应位置


  Principal Diagnosis Reasoning          Confidence / Uncertainty
  ─────────────────────────────          ────────────────────────
  主要诊断选择推理                →    高/中/低置信度
  (规则引用+时间线证据)                 低置信→人工必须复核


  Disagreement Handling              Human Coder Review
  ────────────────────              ───────────────────
  AI vs 现有编码不一致       →     编码员 Approve/Reject/Modify
  标记类型+严重度                   支持修改理由+修正编码


  Coding Decision Trace              Report / Audit Export
  ────────────────────              ──────────────────────
  完整决策链路记录            →    JSON/Markdown报告
  (证据→代码→规则→输出)            审计链不可篡改


  Feedback Learning Loop
  ──────────────────────
  修正记录→系统学习→规则权重调整
```

---

## 2. 核心页面/面板逻辑

### 2.1 Coding Workbench (编码工作台)

```
┌──────────────────────────────────────────────────────────────┐
│  [Case Selector]  病历搜索/选择        [Runtime Badge] 状态   │
├──────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Evidence    │  │ Candidates  │  │ Report              │  │
│  │ Panel       │  │ Panel       │  │ Panel               │  │
│  │             │  │             │  │                     │  │
│  │ 📋 证据1   │  │ Z51.102 ★  │  │ Primary Diagnosis   │  │
│  │   来源:主诉 │  │ 化疗  0.92 │  │ Z51.102 (化疗)      │  │
│  │   ⬤ 强证据 │  │ ▸ R013 ✓   │  │ Why: R013 rule      │  │
│  │             │  │ ▸ 证据3条  │  │ Not selected:       │  │
│  │ 📋 证据2   │  │            │  │ C20 (no rule match) │  │
│  │   来源:现病史│  │ C20.x00   │  │                     │  │
│  │   ⬤ 中证据 │  │ 直肠癌0.65│  │ Confidence: MEDIUM  │  │
│  │             │  │ ▸ 证据1条  │  │ Route: REVIEW       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                              │
│  [Run Review]  [Export]  [Human Review →]                   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Case Review (病例复核)

```
┌──────────────────────────────────────────────────────────────┐
│  Case: DEMO-001  肿瘤内科  Z51.102                           │
├──────────────────────────────────────────────────────────────┤
│  Code Candidates:                                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ☑ Z51.102 恶性肿瘤化学治疗  0.92  ✅ Approve       │    │
│  │   Evidence: 3 sources  Rules: R013         [Reject] │    │
│  │   Rationale: 入院目的为化疗...              [Modify]│    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ ☐ C20.x00 直肠恶性肿瘤      0.65  ✅ Approve       │    │
│  │   Evidence: 1 source         ⚠️ Low Evidence        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Decision Summary (Right Panel):                             │
│  ┌──────────────────────────────────────┐                   │
│  │ Total: 5 codes                       │                   │
│  │ ✅ Confirmed: 3                      │                   │
│  │ ❌ Rejected: 1                       │                   │
│  │ ✏️ Modified: 1                       │                   │
│  │                                      │                   │
│  │ Runtime Guard: ALLOW ✓               │                   │
│  │ DUC: confirm_decision ✓              │                   │
│  └──────────────────────────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 用户操作路径

### 编码员典型工作流

```
1. 接收病历 (Case Intake)
   └─ EMR自动推送 / 手动输入 / 语音转录

2. 运行AI审核 (Run Review)
   └─ 点击按钮 → Pipeline 执行 → 结果呈现

3. 审阅证据 (Review Evidence)
   └─ 浏览 Evidence Panel → 点击证据 → 原文高亮

4. 核查编码候选 (Check Candidates)
   └─ 浏览 Candidates Panel → 检查 confidence → 检查 DRG impact

5. 确认/拒绝/修正 (Human Review)
   └─ 逐个候选 Approve/Reject/Modify → Decision Summary

6. 导出/归档 (Export)
   └─ 导出 JSON/Markdown → 写入 HIS/EMR (DUC gated)
```

---

## 4. 编码员体验原则 (Corti-Style)

| 原则 | 含义 | 实现方式 |
|------|------|---------|
| **Evidence-First** | 编码员先看到证据，再看到编码建议 | Evidence Panel 在 Candidates Panel 左侧 |
| **Click-to-Source** | 点击编码→高亮病历原文 | evidence_text → source_text 映射 |
| **Confidence Transparency** | 每个编码显示可信度 | 颜色编码: 绿(高)/黄(中)/红(低) |
| **Rule Explainability** | 引用编码规则编号 | "R013: 肿瘤放化疗主诊断选择规则" |
| **Human-in-the-Loop** | AI建议≠最终决策 | 编码员 Approve/Reject/Modify |
| **Non-Blocking Review** | 不强制顺序 | 可跳过、可返回 |
| **Minimal Clicks** | 减少操作步骤 | 键盘快捷键 + 批量操作 |
| **Clinical Language** | 中文临床术语 | 非技术系统术语 |

---

## 5. Evidence-First 设计原则

```
传统编码审核:
  病历文本 → [编码员大脑] → 编码

Corti-Style:
  病历文本 → [AI 提取证据] → [AI 建议编码] → [编码员验证证据] → [编码员确认编码]
              ↑                                    ↑
         结构化事实                          可追溯+可点击
```

核心差异:
- 编码员**不直接看编码建议**，先看证据是否可靠
- 证据分为强/中/弱/冲突四类，一眼可辨
- 编码必须有至少一条证据绑定，无证据=unsupported

---

## 6. 不能复制/不能声称的边界

| 禁止事项 | 原因 |
|---------|------|
| 复制 Corti UI 视觉设计 | 商标/版权保护 |
| 复制 Corti 品牌元素 | 商标 |
| 声称与 Corti 产品功能对等 | 我们无 Corti 内部实现 |
| 声称达到 Corti 生产级准确率 | 无大规模临床验证 |
| 使用 Corti 的模型/训练数据 | 私有资产 |
| 声称"基于 Corti 逆向工程" | 法律风险 |
| 声称已获得医院/药监局认证 | 未取得任何认证 |
| 声称可替代编码员 | 本系统定位为审核辅助 |
