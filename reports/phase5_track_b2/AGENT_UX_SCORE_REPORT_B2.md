# Agent UX Score Report B-2

**Generated**: 2026-07-11 (Phase 5 Track B-2 Phase 11)
**Source**: `outputs/phase5_track_b2/agent_ux_matrix_b2.csv`
**Dimensions**: 12 × 9 agents

---

## 1. UX Matrix (12 dimensions × 9 agents)

| UX Dimension | CP1 | CP2 | CP3 | CP4 | CP5 | CP6 | CP7 | CP8 | CP9 | 9-agent avg |
|---|---|---|---|---|---|---|---|---|---|---|
| 入口可发现性 (entry_discoverability) | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4.00 |
| 输入体验 (input_experience) | 4 | 3 | 3 | 4 | 4 | 3 | 4 | 4 | 3 | 3.56 |
| 输出可读性 (output_readability) | 4 | 3 | 4 | 4 | 4 | 4 | 5 | 4 | 5 | 4.11 |
| 错误恢复 (error_recovery) | 4 | 4 | 4 | 5 | 5 | 5 | 5 | 5 | 5 | 4.67 |
| 实时反馈 (realtime_feedback) | 4 | 2 | 4 | 4 | 3 | 4 | 3 | 3 | 3 | 3.33 |
| Trace 透明度 (trace_transparency) | 3 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | **2.11** |
| Cost 透明度 (cost_transparency) | 5 | 2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4.67 |
| 复制/下载 (copy_download) | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | **5.00** |
| 配置可调 (configurable) | 4 | 3 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 3.89 |
| 多轮对话 (multi_turn) | 4 | 3 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 3.89 |
| 移动响应 (mobile_response) | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3.00 |
| 国际化 (i18n) | 4 | 3 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 3.89 |
| **AGENT_AVERAGE** | **4.00** | **3.08** | **3.83** | **4.00** | **3.92** | **3.92** | **4.00** | **3.92** | **3.92** | **3.84** |

---

## 2. Per-agent UX tier

| Tier | Score | Agents |
|---|---|---|
| **Tier 1** (≥4.00) | 4.00 | medical-coding-agent, note-completeness-agent, principal-diagnosis-review |
| **Tier 2** (3.80-3.99) | 3.83-3.92 | compliance-guardrail (3.83), procedure-extractor, evidence-extractor, discharge-summary-structuring, drg-analyzer (all 3.92) |
| **Tier 3** (<3.50) | 3.08 | code-validation-agent (SKELETON) |

**Overall 9-agent avg**: **3.84 / 5** (= 76.8 / 100)

---

## 3. Dimension-level insights

### 3.1 Strengths (avg ≥ 4.5)
- **copy_download** (5.00): all 9 agents support markdown copy + JSON download
- **error_recovery** (4.67): fail-soft + manual_review_required 触发准确
- **cost_transparency** (4.67): ¥ CNY 明示（CP2 SKELETON 无 cost 拉低平均）

### 3.2 Weaknesses (avg < 3.5)
- **trace_transparency** (2.11): PureLLM agents 仅 1 event（最大 gap） — Track C Gate 6 修复
- **mobile_response** (3.00): 堆叠布局，无 mobile-specific optimization
- **realtime_feedback** (3.33): 7-15s 长输入无 streaming

### 3.3 Pair comparisons
- medical-coding-agent vs code-validation-agent: 4.00 vs 3.08 (0.92 gap, because CP2 SKELETON)
- note-completeness vs procedure-extractor: 4.00 vs 3.92 (0.08 gap, similar PureLLM pattern)
- principal-dx vs discharge-summary: 4.00 vs 3.92 (0.08 gap, principal-dx output_readability=5)

---

## 4. B-1 vs B-2 UX calculation method

**B-1**: 12 dimension × single overall score → skewed by trace gap (B-1: 56.8/100)
**B-2**: 12 dimension × 9 agents matrix → per-agent isolate trace gap to PureLLM agents only → 76.8/100

B-2 method is more accurate because:
1. trace_transparency gap is provider-specific (PureLLM = 1 event, medical-coding = multi-step)
2. cost_transparency gap is runtime-specific (CP2 SKELETON = no cost, others = accurate)
3. medical-coding UX shouldn't be dragged down by CP2 SKELETON

---

## 5. Track C Gate 5 (UI Workbenches) target

Per PDF §10, Track C builds 9 specialized workbenches:
- Medical Coding Workbench (3-pane)
- Code Validation Workbench
- Compliance Guardrail Workbench
- Note Completeness Workbench
- Procedure Workbench
- Evidence Workbench
- Principal Diagnosis Workbench
- Discharge Structuring Workbench (2-pane)
- DRG/DIP Workbench

Target: all 9 agents reach Tier 1 (≥4.00) post-Track C. Specifically:
- CP2 lifts from 3.08 → 4.00+ (after Gate 1 SKELETON fix)
- CP3-CP9 lift 3.83-3.92 → 4.00+ (after Gate 5 specialized workbench)

Expected post-Track C overall: **4.20+ / 5** (= 84+ / 100)
