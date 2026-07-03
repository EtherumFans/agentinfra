# iCoDer Embed 契约 (`<icoder-embedded>`)

本契约规定嵌入组件与宿主应用、与 iCoDer 院内服务之间的接口。它是 Corti
`<corti-embedded>` 契约在**私有化部署 + 中国编码体系**下的对应物。

## 1. 角色与边界

```
宿主应用 (HIS/EMR 门户)            iCoDer 院内服务 (uvicorn, 单进程)
  ├─ 持有鉴权, 注入短时令牌            ├─ /api/coding-review/*   (Runtime + 合规门禁)
  ├─ 持有品牌与输入 UI                ├─ /agents/* (A2A 发现/Agent Card)
  └─ 挂载 <icoder-embedded> ───CORS──→ └─ /icoder-embedded.js, /index.html, /llms.txt (静态)
        (只渲染结果, 不持凭据)
```

- **数据不出院**：组件 `base-url` 指向院内服务；病历文本只在院内服务端处理与脱敏。
- **无状态令牌**：宿主签发并通过 `configureSession({ token })` 注入；组件不持久化、不写入 DOM 属性。

## 2. 生命周期

| 阶段 | 触发者 | 动作 |
|------|--------|------|
| ready | 组件 | `connectedCallback` 完成，派发 `ready` |
| auth | 宿主 | `configureSession({ token })` → 派发 `auth` |
| configure | 宿主 | `configure({ agentId, codingSystem })` → 派发 `configured` |
| show | 宿主 | `run(text)` → 服务端运行 → 渲染 → 派发 `run.completed` |

## 3. 方法

| 方法 | 说明 |
|------|------|
| `configureSession({ token })` | 注入鉴权令牌（host-issued, stateless） |
| `configure({ agentId, codingSystem })` | 设定使用的薄 Agent 与编码体系 |
| `run(text)` | `POST {base-url}/api/coding-review/run`，渲染结果 |

## 4. 事件 (`embedded-event`, detail = `{ type, payload }`)

`ready` · `auth` · `configured` · `run.started` · `run.completed` ·
`rule-gate-triggered` · `evidence-clicked` · `code-overridden` ·
`human-review-submitted` · `error.triggered`

（各 payload 见 `.well-known/agent-skills/icoder-coding-review/SKILL.md`）

## 5. 渲染不变量

1. 证据高亮按 `redaction.text[start:end]`（start 含 / end 不含）渲染，不重新检索定位。
2. `codes` 与 `candidates` 分区展示，不合并；`codes` 不重排（保留临床顺序）。
3. 门禁 `hits` 按 severity（Critical/Moderate/Informational）展示；`human_review_required` 时暴露复核入口。
4. 报告/嵌入只渲染服务端返回的去标识化文本，永不展示原始 PHI。

## 6. RunResult 形状（节选）

```jsonc
{
  "run_id": "run_…",
  "redaction": { "redacted": true, "spans": 3, "text": "…去标识化文本…" },
  "codes":      [ { "code": "I50.900", "is_primary": true, "evidences": [{"start":5,"end":11,"text":"慢性心力衰竭"}], "notes": [], "alternatives": [] } ],
  "candidates": [ { "code": "M80.900", "high_risk": true, "status": "candidate", "evidences": [ … ] } ],
  "compliance": { "passed": true, "human_review_required": true, "hits": [ { "rule_id": "MC-R-M80-001", "severity": "Moderate", "message": "…" } ] },
  "drg_route":  { "adrg": "FT2", "drg": "FT23", "group_name": "心力衰竭、休克" },
  "versions":   { "runtime_version": "…", "ruleset_version": "…", "catalog_version": "…", "model_version": "…", "agent_version": "…" },
  "production_writeback_blocked": true
}
```

## 7. 服务端不变量（非集成方可配置）

- `production_writeback_blocked` 恒为 `true`（样板阶段禁止写回 EMR）。
- 合规规则集缺省 → 服务端拒绝执行（HTTP 409 `ruleset_missing`）。
- 人工复核 `reviewer_role` 从令牌注入，忽略请求体；角色须 ∈ {coder, admin}，否则 403。
