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
- 每个 case 由 2 名团队成员独立构造，第 3 名仲裁
- 编码必须通过 `icd10cn_code_catalog.json` (37,897 码) 验证
- 平行 zh+en 翻译必须由医学英语背景者审核
- 显式标注 `construction_method: synthetic` + `phi_status: phi-free`

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
| HOBV1-001 | 骨科 | S22.000 T12 骨折 | 81.01 切开复位内固定 | 3 |
| HOBV1-002 | 普外 | K35.900 急性阑尾炎 | 47.01 腹腔镜阑尾切除 | 0 |
| HOBV1-003 | 呼吸 | J18.900 CAP | (无) | 2 |
| HOBV1-004 | 内分泌 | E11.100 T2DM DKA | (无) | 0 |
| HOBV1-005 | 心内 | I21.100 下壁 STEMI | 36.06 PCI+DES | 3 |

**覆盖评估**:
- ✅ 4 类任务: dx + procedure + chronic comorbidity + acute complication
- ✅ 5 个 MDC（MDC 8 / 7 / 4 / 3 / 5）
- ❌ 25 MDC 覆盖率 5/25 = 20%
- ❌ 不含 CDI gap case（需 Phase A 补充）
- ❌ 不含 negated / historical / family history（需 Phase A 补充）

---

## 4. Runner 支持计划

当前 runner **仅支持中文 + ccl2026_train_gold.json 结构**:

| Runner | 输入结构 | 是否支持双语 |
|---|---|---|
| `e2e_medcoder_validation.py` | CCL 2026 gold_cases | ❌ |
| `e2e_runtime_validation.py` | CCL 2026 gold_cases | ❌ |

**改造选项**（不在 R2 范围内）:

**Option A** — 新建 `e2e_bilingual_validation.py`
- 读取 `held_out_bilingual_v1.json`
- 对 zh / en 分别跑 MedCodER full pipeline
- 输出 per-language F1@1/2/5 + cross-language consistency metric
- 可加 `--cases` flag 指定文件路径

**Option B** — 扩展现有 runner 支持 fixture format flag
- `e2e_medcoder_validation.py --fixture held_out_bilingual_v1.json --lang zh`
- 优点: 复用 4-variant ablation 逻辑
- 缺点: 双语并跑需求无法表达

**推荐 Option A**，理由: 双语评测本质上是不同任务（不同语言不同 LLM 路径），分开 runner 更清晰。在 R2 后续 sub-gate（R2.4 / R2.5）实现。

---

## 5. 不做的事 — 显式排除

为避免范围蔓延，以下**明确不在 R2 范围内**:

1. **不实现 R2.4 runner 脚本** — 当前 5 cases 无需 runner（手工跑 + 目检即可）。≥30 cases 时再实现。
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

**文档版本**: 1.0（2026-08-06 初始创建）
**R2 状态**: PARTIAL_R2_HOLD_OUT_STRATEGY_FILED_5_OF_100_CASES_PHASE_A_NOT_STARTED
