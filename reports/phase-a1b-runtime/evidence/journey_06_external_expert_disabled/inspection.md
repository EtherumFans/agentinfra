# Journey 6 — External Expert 禁用(0 网络出口验证)

**Verdict**: HUMAN_WORKFLOW_VERIFIED (GATE_DENY_0_EGRESS)
**Date**: 2026-07-23
**Entry**: Python module `app.agents.experts.external_expert_gate`
**User**: admin

## Steps

1. 调用 `evaluate(expert_key='pubmed', egress_enabled=False, ...)` — 必须返回 `permitted=False reason=EGRESS_DISABLED`
2. 调用 `evaluate(expert_key='drugbank', egress_enabled=True, provider_opt_in=True, tenant_opt_in=True, ...)` — 必须返回 `permitted=False reason=LICENCE_REQUIRED`(无许可证)
3. 调用 `evaluate(expert_key='posos', ...)` — 必须 `LICENCE_REQUIRED`
4. `is_gated('pubmed') = True`,`is_gated('drugbank') = True`,`is_gated('calculator') = False`

## Gate Decision Matrix

| Expert | egress_enabled | region | reason | permitted |
|--------|---------------|--------|--------|-----------|
| pubmed | False | cn | EGRESS_DISABLED | False |
| pubmed | False | eu | EGRESS_DISABLED | False |
| pubmed | False | us | EGRESS_DISABLED | False |
| drugbank | True | cn/us/eu | LICENCE_REQUIRED | False |
| posos | True | cn/us/eu | LICENCE_REQUIRED | False |

## 0 Egress 保证

- Gate decision 在 ExpertRunner 调用真正 HTTP 前同步返回
- Gate 是纯本地逻辑(no DNS lookup, no TCP connect)
- ExpertRunner 在 gate.permitted=False 时不调用 `httpx.AsyncClient.get(...)`
- `app/services/mcp_wrapper.py` 有独立 SSRF allowlist,即使 gate 绕过也会在 `169.254.169.254` 等内部 IP 上 400 BLOCKED

## API Calls

- HTTP 路径: `GET /api/v1/experts/external-gate/evaluate?expert_key=...&egress_enabled=false&...`
- Python 路径: `from app.agents.experts.external_expert_gate import evaluate`

## Evidence

- screenshot.png — 6 条 gate decision 输出

## Corti 对比

- Corti /experts — 无显式 gate 决策 UI
- 差异: iCoDer 加了 "外部出口" 决策展示(放行/需许可证/区域受限),Corti 无此 UI
- R.3.a 新增的 SSRF allowlist 是 iCoDer 独有的额外防御层

## Notes

- `pubmed` 有 EGRESS_DISABLED 路径;`clinical_trials` 似乎无 gate 限制(always OK)— 这可能是一个 bug,但不在 R.5.c 范围内,留作 backlog
- `drugbank` / `posos` 走 LICENCE_REQUIRED 路径,需要授权才能启用
- Gate 逻辑位于 `app/agents/experts/external_expert_gate.py:72 evaluate()`
- Forbidden: DrugBank/POSOS live runs without licence — 本 journey 仅验证 deny 路径
