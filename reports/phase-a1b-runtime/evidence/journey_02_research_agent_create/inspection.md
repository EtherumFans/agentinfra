# Journey 2 — 创建 Agent (从零开始)

**Verdict**: HUMAN_WORKFLOW_VERIFIED
**Date**: 2026-07-23
**URL**: http://127.0.0.1:5173/ai-studio/agents/new → /ai-studio/agents/a9d39844d0ee
**User**: admin

## Steps

1. 访问 `/ai-studio/agents/new`
2. 点击 "创建AI智能体"(从零开始创建区块)
3. 输入框出现,输入 `Journey2-Research-Agent`
4. 再次点击 "创建AI智能体"
5. 跳转到 `/ai-studio/agents/a9d39844d0ee`(新 Agent ID)

## API Calls

- `POST /rest/v1/agent_definitions` body=`{name: "Journey2-Research-Agent", ...}` → 200

## Evidence

- screenshot.png — 创建后跳转到 Agent 详情页

## Corti 对比

- Corti /agents/new 流程一致(name-only → 详情页定制)
- 差异: iCoDer 没有 Corti 的 "Customize agent" 模态,直接跳转

## Notes

- 创建的 Agent 在后续 Journey 中复用
- Agent ID: `a9d39844d0ee`
