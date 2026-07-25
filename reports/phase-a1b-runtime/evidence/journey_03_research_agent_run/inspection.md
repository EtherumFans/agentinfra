# Journey 3 — 运行 Agent 产生 Task + Artifact

**Verdict**: HUMAN_WORKFLOW_VERIFIED
**Date**: 2026-07-23
**URL**: http://127.0.0.1:5173/ai-studio/medical-coding
**User**: admin

## Steps

1. 访问 `/ai-studio/medical-coding`(预置 runtime agent medical-coding-agent)
2. 点击 "引导演示" 加载样本病例
3. 点击 "预测编码"
4. 5497 ms 后返回 3 个编码 + run_id + trace_id

## API Calls

- `POST /api/v1/coding/predict` → 200
  - latency_ms: 5497
  - llm_provider: deepseek
  - runtime_mode: corti_like_fast
  - 3 codes: I20.0 / I10.x00x002 / E11.900
  - run_id: `fast-bb9e70f1bea2`
  - trace_id: `trace-a8e5396c0f144667`

## Artifact

RunHistory row created under run_id `fast-bb9e70f1bea2` with:
- 3 diagnoses (primary: I20.0 不稳定型心绞痛 confidence 0.95)
- DRG suggestion: FR1
- DIP suggestion: 不稳定型心绞痛伴高血压、糖尿病
- manual_review_required: false
- 7 trace events (input_received → language_detect → build_prompt → llm_call → parse_json → project_result → return)

## Evidence

- screenshot.png — Medical Coding 页面 + 预测结果表

## Corti 对比

- Corti /medical-coding 等价路径 — 类似(左侧输入,右侧编码 + 证据)
- 差异: iCoDer 加了 DRG/DIP suggestion + 7-stage trace events

## Notes

- A2A Task 状态机(R.1.a)产生 `submitted → working → completed` 状态转换,但 medical-coding-agent 用的是 Phase 4-F1 unified AgentRun API(非 A2A message:send),两者在 backend 都走 task_state_machine 但前端只看 run_id
