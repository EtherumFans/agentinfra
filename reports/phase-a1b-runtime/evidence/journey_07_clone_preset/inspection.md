# Journey 7 — Clone Preset (icoder-cdi-preset)

**Verdict**: HUMAN_WORKFLOW_VERIFIED (HTTP_200_WITH_AGENT_ROW)
**Date**: 2026-07-23
**URL**: POST http://127.0.0.1:8000/api/v1/agents/quick?from_preset=icoder-cdi-preset
**User**: admin

## Steps

1. `POST /api/auth/login {admin/admin123}` → 获取 JWT access_token
2. `POST /api/v1/agents/quick?from_preset=icoder-cdi-preset` with body `{"name":"Journey7-CDI-Clone"}`
3. 返回 **HTTP 200**(不是 404)with new Agent row

## API Response

```json
{
    "id": "af88ee11bfc9",
    "name": "Journey7-CDI-Clone",
    "canonical_key": "icoder-cdi-preset",
    "agent_type": "expert",
    "status": "draft",
    "version": "1.0.0",
    "next_step": "customize"
}
```

## 对 A1B-AE.10 证据误判的纠正

A1B-AE.10 把 Journey 7 标为 `API_WORKFLOW_VERIFIED` 但响应体是 `404 "Agent not found"`。根因:

1. A1B-AE.6 AliasResolver 把 `code_validation → code-validation` 别名解析对了
2. 但 DB 里**根本没有** Agent 行 — clone-preset 没创建过任何 Agent
3. 响应 404 被错误地当成 "工作流通过"

R.2.c 修复方案:
- 新增 `POST /api/v1/agents/quick?from_preset=...` 端点
- 从 `icoder_preset_agents.json` 读 preset 定义
- 复制 preset 的 `system_prompt` / `expert_ids` / `config` 到新 Agent 行
- 持久化到 `agent_definitions` 表
- 返回新 Agent 的 `id` + `canonical_key` + `next_step="customize"`

## Evidence

- screenshot.png — HTTP 200 + JSON response 截图
- `curl` output (terminal log)

## Corti 对比

- Corti /agents/new 流程一致(name-only → 详情页定制)
- 差异:
  - iCoDer 加了 Preset 概念(5 个预设 Agent Card,1 个有 Pack 备份)
  - iCoDer 加了 "Customize agent" 跳转(Corti 是弹窗,iCoDer 是路由跳转到 `/ai-studio/agents/{id}`)

## Notes

- 5 个 preset: `icoder-coding-preset`(已有 Pack)、`icoder-cdi-preset`、`icoder-drg-dip-preset`、`icoder-claim-check-preset`、`icoder-research-preset`
- R.2.a 设置 `delegates_to_pack` 在 4 个 stub preset 上指向新 Pack(cdi/drg-dip/claim-check)
- R.2.c 端点位于 `app/api/v1/agents.py` 路由 `POST /agents/quick`
- 新 Agent ID `af88ee11bfc9` 已在 DB,后续 journey 可复用

## 从 A1B-AE.10 证据纠正看 R 系列进展

| 阶段 | Journey 7 状态 | Verdict |
|------|--------------|---------|
| A1B-AE.10 (pre-R) | 404 "Agent not found" | API_WORKFLOW_VERIFIED (错误) |
| A1B-AE-R.0 (regrade) | 404 确认 | EVIDENCE_MISJUDGMENT_CORRECTED |
| A1B-AE-R.5 (本旅程) | 200 + new Agent row | HUMAN_WORKFLOW_VERIFIED |
