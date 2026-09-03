# User Directive — Corti Similar Agent + Orchestrator Architecture

**Issued**: 2026-07-11 (mid-CP6 commit)
**Affects**: CP7, CP8, CP9 (and retrospectively notes CP1-CP6)
**Source**: User directive during Phase 5 Track B-2

## 用户原话

> 对于corti没有完全与之对应的Agent，请对标corti的相似agent，复刻其设计理念、处理流程、LLM调用、工具调用或者skill调用等等。另外，iCoDer的Agent底层也要采用orchestrator调度其他Agent的架构。

## 1. 两条新约束

### 约束 A — Corti 相似 agent 对标（适用于 ICODER_ONLY agents）

对于 Corti 没有完全对应 agent 的 checkpoint（CP7/CP8/CP9 per B-1 mapping），不得只标 `ICODER_ONLY` / `NO_CORTI_EQUIVALENT` 了事。必须：

1. 从 Corti 20 个 agent 中识别**最相似的 1 个**（按 design philosophy / processing flow / output shape 三维度）
2. 复刻其**设计理念**（产品定位、目标用户、使用场景）
3. 复刻其**处理流程**（输入 → LLM call → tool call → 输出 schema）
4. 复刻其 **LLM 调用模式**（system prompt 结构、few-shot、JSON mode）
5. 复刻其**工具调用 / skill 调用**（MCP tools / sub-experts / sub-agents）

### 约束 B — Orchestrator 调度其他 Agent 架构

iCoDer 当前架构（pre-directive）：
```
unified API → ProviderRegistry → PureLLMProvider / LLMWithToolsProvider / RuleEngineProvider
```

每个 agent 独立、扁平、不互调。

iCoDer 目标架构（post-directive）：
```
unified API → Orchestrator (state machine)
              ↓ plan
              delegate to sub-agents (medical-coding / evidence-extractor / compliance-guardrail / ...)
              ↓ aggregate
              return unified result
```

orchestrator 代码已存在 (`backend/app/icoder/agent_runtime/orchestrator/`，5 态状态机 + planner + delegator + aggregator per memory 2026-06-20 拍板)，但 **runtime 没有把 medical-coding / compliance / evidence 等 agent 编排起来**。

## 2. CP7/CP8/CP9 Corti 相似 agent 映射

基于 B-1 inventory (`outputs/phase5_track_b/agent_mapping.json`) + Corti prompt 库 (`outputs/phase5_track_b/corti_prompts/`)：

| CP | iCoDer Agent | B-1 标签 | **Corti 相似 agent（本 directive 起）** | 相似维度 |
|---|---|---|---|---|
| CP7 | principal-diagnosis-review | ICODER_ONLY | **medical-coding-icd-10-cpt-agent** (Corti 把 principal dx logic 内嵌) | design + processing flow + LLM call |
| CP8 | discharge-summary-structuring | ICODER_ONLY | **clinical-documentation-improvement-cdi-agent** (Corti CDI 最接近) | design + LLM call + structure output |
| CP9 | drg-analyzer | ICODER_ONLY | **compliance-guardrail-agent** (Corti rule-based compliance 最接近 DRG 规则) + **clinical-guidelines-agent** (decision-tree style) | design (rule-based) + tool/skill calls |

每个 CP 报告必须新增 **§4a. Corti 相似 agent 复刻分析**字段（在原 §4 Corti 映射后），覆盖 5 维度：
- 设计理念对照
- 处理流程对照（步骤 by 步骤）
- LLM 调用对照（system prompt / few-shot / json mode）
- 工具调用对照（MCP tools / sub-experts）
- 复刻优先级清单（哪些 iCoDer 应该补）

## 3. Orchestrator 架构落地路线（per CP）

### 现状（CP1-CP6 验证）

每个 agent 独立 invoke，无 agent 间编排：

```
User → POST /api/v1/agents/{X}/run → ProviderRegistry → Provider.invoke → envelope
```

证据：CP3 compliance-guardrail 需要 medical-coding 输出作输入，必须用专用 chained runner (`phase5_track_b2_cp3_coding_output_runner.py`) 串联——**手工串联**而非 orchestrator 自动调度。

### 目标（Phase 5+）

medical-coding orchestrator 自动调度：

```
User → POST /api/v1/agents/medical-coding-agent/run
       → Orchestrator.invoke
       → Planner: plan stages [coding, evidence, compliance, completeness]
       → Delegator:
           stage 1: medical-coding-agent (ICD-10-CN 分配)
           stage 2: evidence-extractor (per-code evidence) — uses stage 1 output
           stage 3: compliance-guardrail (rule validation) — uses stage 1 output
           stage 4: note-completeness (documentation gaps) — parallel
       → Aggregator: merge all stage outputs
       → return unified envelope
```

### Phase 5 Track B-2 范围（不修代码，只标 gap）

每个 CP 报告新增 **§26a. Orchestrator wiring gap**字段：
- 该 agent 是否应作为 orchestrator 子 agent？（yes/no + rationale）
- 当前是否 wired？（全部 no）
- 推荐 orchestrator 入口（哪个 agent 应该是 orchestrator 主入口？）

### Phase 5 Track C（接下来的工作 — 不在本 B-2 范围）

实际 wire orchestrator：
1. 选 medical-coding-agent 作 orchestrator 主入口（其他 4 个作 sub-agents）
2. 写 Planner prompt（决定调度哪些 sub-agents）
3. 写 Delegator dispatch（A2A message send between agents）
4. 写 Aggregator merge logic（合并 sub-agent envelopes）
5. 验证 end-to-end 编排（input → multi-agent → unified output）

## 4. 影响 CP7/CP8/CP9 报告模板

32 字段 → **34 字段**（新增 §4a + §26a）。CP1-CP6 不补写（保持原 32 字段），但在 Phase 11 汇总报告统一标注 "post-CP6 用户 directive 新增约束"。

## 5. 立即执行

继续 CP7 principal-diagnosis-review，按 34 字段模板写。Corti 相似 agent = `medical-coding-icd-10-cpt-agent`，复刻分析见 CP7 报告 §4a。
