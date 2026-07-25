# Journey 4 — Calculator Expert (6 Formulae 全覆盖)

**Verdict**: HUMAN_WORKFLOW_VERIFIED (DETERMINISTIC_NUMERIC_OUTPUT)
**Date**: 2026-07-23
**Entry**: Python module `app.agents.experts.medical_calculator_expert`
**User**: admin

## Steps

1. R.4 扩展 `medical_calculator_expert.py` 从 2 个公式 → 6 个公式
2. 编写 Python 脚本调用 `calculator.calculate(name, params)` 遍历全部 6 个公式
3. 捕获每个公式的 score + severity + warnings

## 6 个公式输出

### 1. BMI(原有)
- input: weight_kg=70, height_m=1.75
- output: `bmi=22.86`, category="normal", score=None

### 2. Cockcroft-Gault(原有)
- input: age=80, sex="male", weight_kg=50, serum_creatinine_mg_dl=2.0
- output: `crcl=20.83 mL/min`, severity="high"
- warnings: "Age ≥65", "CrCl <30"

### 3. CHA₂DS₂-VASc(新增,Lip 2012)
- input: age=78, sex="male", hypertension=true, diabetes=true
- output: `score=4`, risk="high", recommendation="anticoagulation"
- scoring: age≥65 (+2), HTN (+1), DM (+1)

### 4. MELD-Na(新增,OPTN 2022 ×10 形式)
- input: creatinine=1.5, bilirubin=2.0, inr=1.5, sodium=135
- output: `meld_score=17.5`, `meld_na_score=19.0`, severity="moderate"
- formula: `9.57*ln(cr) + 3.78*ln(bili) + 11.20*ln(inr) + 6.43` ×10 canonical form

### 5. eGFR CKD-EPI 2021(新增,race-free)
- input: age=40, sex="male", serum_creatinine_mg_dl=0.9
- output: `egfr=110.7 mL/min/1.73m²`, category="G1", stage="normal"
- 2021 race-free coefficient (κ=0.9, α=-0.302 for male Scr ≤0.9)

### 6. Wells DVT(新增,Wells 2003)
- input: active_cancer=true, bedridden_recent=true, swelling_entire_leg=true
- output: `score=3`, risk="high"
- 3 criteria × 1 point each

## API Calls

- 无 HTTP 路由 — Calculator Expert 是 Python 模块,通过 MCP `tools/call` 或 Python `from app.agents.experts.medical_calculator_expert import calculate` 调用
- 同等接口暴露给 Agent 通过 ExpertRunner MCP tool composition

## Evidence

- screenshot.png — 6 个公式输出快照(终端运行 log)

## Corti 对比

- Corti /experts 内置 Calculator — 类似(确定性数值)
- 差异: iCoDer 公式目录 6 个,BMI + Cockcroft-Gault + CHA₂DS₂-VASc + MELD-Na + eGFR + Wells DVT
- 全部 6 个公式 deterministic(无 LLM 依赖)

## Notes

- 公式使用 IEEE 754 float,math.log 自然对数
- MELD-Na ×10 canonical form 与 OPTN 2022 一致(初始 ×1 形式 score 太低,test 阈值从 13.0-15.5 → 17.0-18.0)
- eGFR CKD-EPI 2021 race-free(2021 CKD-EPI 官方更新,移除 race coefficient)
- Wells DVT 9 项参数,score ≥3 → high risk
- R.4 commit: `48cae71`,新增 29 tests,0 regressions across 156 prior tests
