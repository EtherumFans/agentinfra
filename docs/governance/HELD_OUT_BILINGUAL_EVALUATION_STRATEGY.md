# Held-out Bilingual Evaluation Strategy — Road to 100 Cases

> **Scope**: 把 `backend/tests/fixtures/held_out_bilingual_v1.json` 从当前 5 cases 扩展到 ≥ 100 cases 的执行计划。
> **Source risk**: `docs/governance/RELEASE_ROADMAP.md` §3 R2 + `docs/governance/EVALUATION_CITATION_POLICY.md` §2 rule 3。
> **Created**: 2026-08-06（R2.3 交付）
> **Authority**: 本文档是执行计划，不替代任何 charter verdict。Charter §22 的 8 个禁用 verdict 在此文档中同样禁用。

---

## 1. 目标 — 为什么需要 100 cases

`EVALUATION_CITATION_POLICY.md` §2 rule 3 列出 5 个条件才能解禁 Corti 对比 claim。条件 1 是"双语评测集就绪 ≥ 100 cases"。当前仅 5 cases，因此 Corti 对比 claim 在用户可见表面**全部禁用**。

100 cases 的选择依据：
- **统计学意义**: per-case F1 在 100 cases 上 95% CI 半宽 ≈ 0.05（Wilson 区间，假设 F1 ≈ 0.5）— 足以发现 5%+ 差距
- **科室覆盖**: 中国 DRG 核心 25 个 MDC（Major Diagnosis Category），每 MDC 至少 4 cases
- **任务覆盖**: principal dx / secondary dx / principal procedure / CDI gap 共 4 类，每类至少 20 cases
- **运维可行性**: 100 cases × 2 语言 × MedCodER 5-stage ≈ 1000 LLM calls，约 ¥500 / 月 — 可承受

---

## 2. 三阶段扩展路径

### Phase A — 合成扩展（5 → 30 cases）⏱ 2-3 周

**方法**: 由 iCoDer 工程团队从公开临床指南构造合成 case。

**素材来源**（按优先级）：
1. **UpToDate** (英文) + **默沙东诊疗手册** (中英双语) — 公开临床指南，可引用
2. **中国国家卫健委临床路径** (公开 PDF，中文) — 25 个常见病种路径
3. **国家临床重点专科病例模板** (公开教学用，中文)

**质控**:
- 工程团队只负责构造 PHI-free 平行病历，不得直接把自身 expected code 提升为独立 gold
- 每个 case 使用不含 `expected_*`、旧 evidence、notes 或模型输出的盲化包，由至少 2 名独立合格编码 reviewer 分别标注；任何分歧由第 3 名独立合格 adjudicator 裁决
- reviewer/adjudicator 身份、资质、签字、机构独立性和利益冲突必须由外部临床治理 owner 核验
- 所有诊断和术式必须通过当前固定哈希 ICD-10-CN / ICD-9-CM-3 目录成员校验，并分别绑定中英文病历中的逐字 evidence span
- 平行 zh+en 翻译必须由医学英语背景者审核
- 显式标注 `construction_method: synthetic` + `phi_status: phi-free`

当前可执行工作流为 `backend/scripts/corti_parity/bilingual_coding_gold_review.py`；2026-08-27 已生成首份 5-case reviewer readiness bundle，但尚无外部 reviewer 提交，因此 `independent_gold_ready=false`。

**Phase A 出口**: 30 cases 覆盖 10 个科室 + 4 类任务。

### Phase B — 公开数据集翻译对齐（30 → 60 cases）⏱ 4-6 周

**方法**: 从公开英文 EHR 数据集翻译对齐。

**候选数据集**（按合规性排序）:
1. **MIMIC-IV-Note** (PhysioNet, MIT 公开) — 已脱敏，需要 credentialed access
2. **MTSamples** (公开样本) — 已脱敏，但编码不严
3. **CASI** (公开评测集) — 已脱敏，编码可信
4. **n2c2** (i2b2 legacy) — 部分公开，需要 DUA

**MIMIC-IV-Note 流程**:
- 申请 credentialed access (1-2 周)
- 选 30 个 case 覆盖常见 ICD-10-CM 码
- 英文原文 + 中文翻译（团队医学翻译 + 母语审核）
- ICD-10-CM 码 → ICD-10-CN 码映射（用 `coding_differentiation_kb.json` 辅助）
- 显式标注 `construction_method: mimic_iv_note_translated` + `phi_status: de-identified-per-hipaa-safe-harbor`

**Phase B 出口**: 60 cases 覆盖 15 个科室 + 4 类任务 + 真实 EHR 风格。

### Phase C — Design-partner 医院（60 → 100+ cases）⏱ Pilot 期

**方法**: Pilot 医院提供真实脱敏 case。

**合规要求**:
- 医院伦理委员会审批
- 患者/家属知情同意
- 18 项 HIPAA Safe Harbor PHI 字段全部脱敏
- 中国《个人信息保护法》合规（敏感个人信息处理规则）
- 医院信息科签字

**这是 pilot gate 阶段才能做的事** — Layer 1 / Layer 2 完成前不可启动。

**Phase C 出口**: 100+ cases 覆盖真实中国医院场景。**这是 Corti 对比解禁的必要条件 1**。

---

## 3. 当前 5-case seed 的科室覆盖

| Case ID | 科室 | Primary Dx | Primary Proc | Secondary Count |
|---|---|---|---|---|
| HOBV1-001 | 骨科 | S22.000 T12 骨折（待独立裁决父/子码） | 03.5301 脊椎骨折切开复位内固定 | 3 |
| HOBV1-002 | 普外 | K35.800x001 急性单纯性阑尾炎 | 47.0100 腹腔镜阑尾切除 | 0 |
| HOBV1-003 | 呼吸 | J18.900 CAP | (无) | 1 |
| HOBV1-004 | 内分泌 | E11.100 T2DM DKA | (无) | 0 |
| HOBV1-005 | 心内 | I21.100 下壁 STEMI | 36.0601 药物涂层支架植入 | 2 |

**覆盖评估**:
- ✅ 4 类任务: dx + procedure + chronic comorbidity + acute complication
- ✅ 5 个 MDC（MDC 8 / 7 / 4 / 3 / 5）
- ❌ 25 MDC 覆盖率 5/25 = 20%
- ❌ 不含 CDI gap case（需 Phase A 补充）
- ❌ 不含 negated / historical / family history（需 Phase A 补充）

---

## 4. Runner 与 reviewer 工作流现状

当前开发校准 runner 已支持双语 5×2，但仍必须区分工程校准与独立 gold：

| Runner | 输入结构 | 是否支持双语 |
|---|---|---|
| `e2e_medcoder_validation.py` | CCL 2026 gold_cases | ❌ |
| `e2e_runtime_validation.py` | CCL 2026 gold_cases | ❌ |
| `run_agent_hub_clinical_calibration_e2e.py` | 40 CDI + 5 coding × zh/en | ✅，串行 50 次、真实 Trace/签名门；当前 coding expected 仍为工程校准标签 |
| `bilingual_coding_gold_review.py` | 盲化 5-case packet + reviewer/adjudication artifacts | ✅，不调用模型；外部 reviewer 尚未完成 |

双语 runner 已输出 principal exact、secondary set F1、procedure exact、evidence anchor、跨语言代码集合一致性和人工复核门。任何 accuracy/Corti claim 仍必须等待 reviewer workflow 的完整外部提交与身份核验，并在 100+ 合法病例上重跑；5-case 工程标签通过不构成解禁。

---

## 5. 不做的事 — 显式排除

为避免范围蔓延，以下**明确不在 R2 范围内**:

1. **不把 5-case runner 结果外推为准确率** — runner 与 reviewer 工具已实现，但样本规模、独立性和医院分布均未满足。
2. **不修改现有 CCL 2026 fixture** — 现有 runner 依赖原结构，不动。
3. **不修改 MedCodER / HybridCodingAdapter** — R2 是评测策略，不动产品代码。
4. **不在 marketing / README 引用新 fixture 的 F1 数字** — `EVALUATION_CITATION_POLICY.md` §2 rule 5 明确禁止。
5. **不做跨厂商对比 claim** — 即便有了双语集，也要等 5 个条件全满足。
6. **不在 Phase A 之前对接 MIMIC-IV** — Phase A 用合成 case 跑通流程，Phase B 才引入 DUA 合规负担。

---

## 6. 触发评审条件

本策略文档**只在以下事件发生时**评审:
- 双语 held-out 集 ≥ 30 cases（Phase A 完成）
- 双语 held-out 集 ≥ 60 cases（Phase B 完成）
- Pilot 医院签约（Phase C 启动条件）
- 双语集 ≥ 100 cases（Corti 对比解禁触发）
- Charter 重裁（R2 verdict 升级触发）

**不在子门粒度评审** — 子门追踪在各 phase 的 `FINAL_VERDICT.md`。

---

## 7. 引用

- `docs/governance/EVALUATION_CITATION_POLICY.md`（策略来源）
- `backend/tests/fixtures/held_out_bilingual_v1.json`（5-case seed）
- `docs/governance/RELEASE_ROADMAP.md` §3 R2（风险定义）
- A1D-DEV.8 verdict（Corti head-to-head DEFERRED to pilot gate）
- Charter §22 禁用 verdict 列表
- MIMIC-IV (Johnson et al., 2023, Sci Data) — Phase B 候选数据集
- 默沙东诊疗手册 (Merck Manual, Consumer/Professional versions) — Phase A 素材
- 中国国家卫健委临床路径 — Phase A 素材

---

**文档版本**: 1.1（2026-08-27 更新 runner、目录和独立 reviewer 工作流现状）
**R2 状态**: PARTIAL_R2_5_OF_100_REVIEW_WORKFLOW_READY_EXTERNAL_REVIEWS_NOT_STARTED
