# iCoDer Evaluation Citation Policy — CN/EN Asymmetry Rule

> **Scope**: 用户可见表面（UI / README / Marketing / 文档 / Sales 物料）引用 iCoDer F1 / Accuracy / 性能数字时必须遵守的规则。
> **Source risk**: `docs/governance/RELEASE_ROADMAP.md` §3 R2 — *CN/EN 评测不对称*（A1D-DEV.8 Corti head-to-head 已 DEFERRED 到 pilot gate）。
> **Created**: 2026-08-06（R2.1 交付）
> **Authority**: 本文档是策略文档，不替代任何 charter verdict。Charter §22 的 8 个禁用 verdict 在此文档中同样禁用。

---

## 1. 背景 — 为什么需要这条策略

iCoDer 的评测基线（CCL 2026 train set, 1800 cases, 中文）与 Corti 公开数字（英文临床场景，不同 ICD 编码集）在以下维度不可直接比较：

| 维度 | iCoDer 评测 | Corti 公开 |
|---|---|---|
| 语言 | 中文 | 英文 |
| 编码集 | ICD-10-CN（国标，37,897 码）| ICD-10-CM（美国版，~70,000 码）|
| 病历风格 | 中国医院出院小结（D&B 风格）| 美国急诊/住院 note（Blogger / SOAP）|
| LLM | DeepSeek V4（中文优化）| 自家模型（英文优化）|
| Gold 来源 | CCL 2026 公开评测集 | 自家 retrospective audit |
| F1 @K 定义 | subdivision-tolerant（I50.900 ≡ I50.9）| 字符串匹配 / strict equality |

**结论**: 即使两个 F1 数字相同，也不代表两个系统在同一任务上的表现可比。

A1D-DEV.8 阶段（2026-07-26）的 20-case MedCodER live benchmark 显示：full=0.109/0.190/0.187，prompt=0.119/0.164/0.173。这些数字仅适用于"iCoDer 自身管线在不同 ablation 下的相对增益"这一对比，**不可**用于"Corti 对比"。

---

## 2. 强制规则

### 规则 1 — 禁止跨厂商 F1 比较

任何用户可见表面**禁止**直接引用形如 "F1 = X vs Corti F1 = Y" 的比较。

允许的替代表述：
- "iCoDer MedCodER full-pipeline F1@2 = 0.190 on CCL 2026 (Chinese medical coding gold standard, 1800 cases)"
- "Corti head-to-head comparison DEFERRED to pilot gate — Chinese-language vs English-language F1 numbers are not directly comparable"

### 规则 2 — 中文场景声明

任何精度数字必须附带语言/数据集声明，例如：
- "(Chinese-language eval, CCL 2026 train set)"
- "(中文评测，CCL 2026 训练集 1800 例)"

不允许的表述：
- "F1 = 0.81"（无上下文）— 暗示跨场景可比
- "State-of-the-art medical coding F1"（未声明语言/数据集）

### 规则 3 — Corti 比较延迟到 pilot gate

任何 Corti 对比性 claim（包括 "outperforms Corti by X%" / "matches Corti accuracy"）在以下条件**全部**满足前禁止出现：

1. **双语评测集就绪** — `backend/tests/fixtures/held_out_bilingual_v1.json` 扩展到 ≥ 100 cases（参见 `docs/governance/HELD_OUT_BILINGUAL_EVALUATION_STRATEGY.md`）
2. **双语 gold 标注完成** — 每个 case 同时有 zh + en 平行病历 + 双向 ICD-10-CN/CM 映射
3. **同一 LLM 在双语上跑同 prompt** — 排除 LLM 路径差异
4. **独立 reviewer 签字** — 不允许工程团队自证
5. **Pilot 客户接受性反馈** — 至少 1 家 design-partner 医院反馈

在以上条件未满足时（当前状态：1/5 — 仅初始 seed），所有 Corti 对比 claim 在用户可见表面为**禁用**。

### 规则 4 — 内部研发材料允许的范围

**允许**（内部研发 / `reports/` / `docs/corti_parity/` / audit 文档）：
- 引用 Corti 公开数字作为参照点（必须附 URL + 日期 + 截图证据）
- 引用 iCoDer 自身数字与 Corti 公开数字的差距分析（必须标 "NOT for external use")
- 战略讨论 "Corti-parity 架构" / "Corti-style workflow"

**禁止**（即使用于内部）：
- 任何暗示 `CORTI_PARITY_VERIFIED` 的表述（charter §22 禁用 verdict）
- 任何暗示 `CORTI_AGENTIC_PARITY_VERIFIED` 的表述（同上）
- 任何 F1 等价的绝对 claim（"F1 已达到 Corti 水平"）

### 规则 5 — 销售与 Marketing 物料

Sales / Marketing / Pricing 页 / `README.md` / `docs/product/PRODUCT_DIRECTION.md`：
- **不引用** Corti 性能数字
- **不引用** iCoDer F1 数字用于和 Corti 比较
- **可以引用** iCoDer F1 数字用于"内部基线 / 改进幅度"展示（必须声明 "Chinese-language eval"）

---

## 3. 评测基础设施现状

### 当前评测资产（中文为主，monoculture 风险）

| 资产 | 类型 | 用途 | 风险 |
|---|---|---|---|
| `ccl2026_train_gold.json` (1800 cases) | 中文 | iCoDer 主基线 | CCL 2026 monoculture |
| `ccl2026_val_100.json` (100 cases) | 中文 | CI smoke | CCL 2026 monoculture |
| `icoder_201.json` (201 cases) | 中文 | A1D-DEV.8 20-case benchmark 来源 | CCL 2026 monoculture |
| `cdi_gap8_smoke10.json` (10 cases) | 中文 | CDI smoke | 小样本 |
| `cdi_gate8_40cases.json` (40 cases) | 中文 | CDI gate 评测 | 小样本 |
| `cdi_gate8_corti3.json` (3 cases) | **双语** | 唯一双语 seed | 仅 CDI 任务，非 coding |
| `held_out_bilingual_v1.json` (本策略 seed) | **双语** | R2.2 交付 | coding 任务，初始 5 cases |

### 评测 Runner（不修改）

- `backend/scripts/e2e_medcoder_validation.py` — 4-variant F1 ablation（full/prompt/retrieve/prompt+retrieve），CCL 2026 only
- `backend/scripts/e2e_runtime_validation.py` — iCoDer 201 baseline，CCL 2026 only
- `backend/scripts/build_icoder_201_fixture.py` — 从 CCL 2026 sample 出 201 cases

**所有现有 runner 仅支持中文。** 双语 runner 见 §4。

---

## 4. 双语 held-out 评测集路线图

详见 `docs/governance/HELD_OUT_BILINGUAL_EVALUATION_STRATEGY.md`。

**当前状态**（2026-08-06）：
- 5-case seed 已交付（`held_out_bilingual_v1.json`）
- 覆盖 5 个常见科室（骨科 / 普外 / 呼吸 / 内分泌 / 心内）
- 每例含 zh + en 平行病历 + ICD-10-CN 编码 + 证据 span
- **明确 NOT derived from CCL 2026** — 由 iCoDer 团队从公开临床指南 + 合成模板构造

**扩展到 100 cases 的路径**（不在本策略文档详细展开，见 sourcing strategy 文档）：
1. Phase A — 合成扩展（5 → 30 cases，2-3 周）
2. Phase B — 公开英文数据集翻译对齐（30 → 60 cases，4-6 周）— MIMIC-IV / MIMIC-IV-Note 选样
3. Phase C — Design-partner 医院提供真实脱敏 case（60 → 100+ cases，pilot 期）

---

## 5. 触发评审条件

本策略文档**只在以下事件发生时**评审：
- 双语 held-out 集 ≥ 100 cases
- Pilot 阶段客户接受性反馈到达
- 等保2.0 三级证书获得
- Corti 公开数字发生重大变化（例如新模型发布）
- A1D Phase 关闭时

**不在子门粒度评审** — 子门追踪在各 phase 的 `FINAL_VERDICT.md`。

---

## 6. 引用

- `docs/governance/RELEASE_ROADMAP.md` §3 R2（策略来源）
- `docs/governance/HELD_OUT_BILINGUAL_EVALUATION_STRATEGY.md`（执行计划）
- `backend/tests/fixtures/held_out_bilingual_v1.json`（R2.2 seed）
- A1D-DEV.8 verdict（Corti head-to-head DEFERRED to pilot gate）
- Charter §22 禁用 verdict 列表

---

**文档版本**: 1.0（2026-08-06 初始创建）
**R2 状态**: PARTIAL_R2_CITATION_POLICY_FILED_BILINGUAL_SET_SEEDED_5_CASES
