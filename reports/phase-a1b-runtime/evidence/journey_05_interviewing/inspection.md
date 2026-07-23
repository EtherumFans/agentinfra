# Journey 5 — Interviewing Expert (serialize/deserialize 多轮状态恢复)

**Verdict**: HUMAN_WORKFLOW_VERIFIED (MULTI_TURN_STATE_PERSISTENCE)
**Date**: 2026-07-23
**Entry**: Python module `app.agents.experts.interviewing_expert`
**User**: admin

## Steps

1. 构建 3-question questionnaire (`chest_pain_v1`):
   - `chest_pain_duration` — "胸痛持续时间?"
   - `radiation` — "疼痛放射到哪里?"
   - `ecg_st` — "心电图 ST 段有抬高吗?"
2. `start_interview()` 初始化 state(cursor=0)
3. 3 次 `advance()` + `record_answer()`,逐步推进
4. `serialize_state(state)` → JSON-able dict(`ask_if` predicates dropped,因为 lambda 不能 JSON-encode)
5. `deserialize_state(blob, fresh_questions=fresh_specs)` 恢复 state(用 fresh QuestionSpec 重新填充 ask_if)
6. `transcript(restored)` 输出问答历史

## 状态转换

```
cursor=0 (未开始)
  → advance() → cursor=1 (chest_pain_duration answered "3 小时")
  → advance() → cursor=2 (radiation answered "左肩")
  → advance() → cursor=3 (ecg_st answered "是,II/III/aVF")
```

## Serialized State Blob(JSON-able)

```json
{
  "version": 1,
  "questionnaire_key": "chest_pain_v1",
  "answers": {
    "chest_pain_duration": "3 小时",
    "radiation": "左肩",
    "ecg_st": "是,II/III/aVF"
  },
  "cursor": 3,
  "notes": "",
  "question_keys": ["chest_pain_duration", "radiation", "ecg_st"]
}
```

## Deserialized State(Resume)

- `topic=chest_pain_v1, cursor=3, answered=3`
- `ask_if` predicates restored from fresh QuestionSpec list
- 校验机制: 如果 `question_keys` 与 fresh_questions 不匹配,`deserialize_state` 抛 ValueError

## Transcript Output

```json
{
  "questionnaire_key": "chest_pain_v1",
  "answers": {
    "chest_pain_duration": "3 小时",
    "radiation": "左肩",
    "ecg_st": "是,II/III/aVF"
  },
  "question_count": 3,
  "answered_count": 3
}
```

## 持久化路径(R.4.c 新增)

- `save_to_context(state, context_id, session)` → 写入 `contexts.metadata_json["interview_state"]`
- `load_from_context(context_id, fresh_questions, session)` → 从 `contexts.metadata_json` 读取并 deserialize

## API Calls

- 无 HTTP 路由 — Interviewing Expert 通过 Agent 内嵌调用或 MCP tool composition
- A2A/AgentRunner 路径: Agent → ExpertRunner → InterviewingExpert
- Context 持久化通过 ContextLifecycle 调用 `save_to_context`

## Evidence

- screenshot.png — 终端运行 log(serialize/deserialize round-trip)

## Corti 对比

- Corti /interview — 类似(schema-driven 多轮问答)
- 差异: iCoDer 显式 `serialize_state` / `deserialize_state` 持久化 API + 基于 cursor 的 resume 机制
- Corti 的 interviewing 通常基于 LLM 自由生成,iCoDer 是 schema-driven(确定性 prompt)

## Notes

- `ask_if` lambda 不能 JSON-encode,serialize 时丢弃,deserialize 时用 fresh QuestionSpec 重建
- `question_keys` sanity check 防止 schema drift(问卷修改后旧 state 不能 deserialize)
- R.4 commit `48cae71` 引入持久化 helper,9 个新 test 覆盖 save/load 往返
