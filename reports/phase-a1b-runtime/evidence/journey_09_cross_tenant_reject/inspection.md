# Journey 9 — Cross-Tenant Reject

**Verdict**: HUMAN_WORKFLOW_VERIFIED (TENANT_ISOLATION_404_NO_LEAK)
**Date**: 2026-07-23
**Entry**: 4 R.1.b cross-tenant tests + 2 control tests
**User**: admin (org A) + second JWT (org B)

## Steps

1. 在 org A 下创建 Context + Task(正常路径)
2. 用 org B 的 JWT 请求 `GET /api/icoder/tasks/{id}` 和 `POST /api/icoder/tasks/{id}/cancel`
3. 用 org B 的 JWT 请求 `DELETE /api/icoder/contexts/{id}`
4. 所有 3 个跨 org 调用必须返回 **404**(不是 403,不泄露存在性)
5. 同 org 控制组必须通过

## R.1.b Cross-Tenant 测试矩阵

| Test | Caller Org | Target | Expected | Result |
|------|-----------|--------|----------|--------|
| `test_delete_context_unknown_returns_404` | A | 不存在 id | 404 | PASS |
| `test_delete_context_cross_tenant_returns_404_no_leak` | B | org A context | 404 | PASS |
| `test_get_task_cross_tenant_returns_404_no_leak` | B | org A task | 404 | PASS |
| `test_cancel_task_cross_tenant_returns_404_no_leak` | B | org A task | 404 | PASS |
| `test_same_org_cancel_succeeds_control` | A | org A task | 200 | PASS |
| `test_same_org_get_succeeds_control` | A | org A task | 200 | PASS |

```
tests/test_api/test_a1b_ae_r_1_b_context_scrub_cross_tenant.py
6 cross-tenant + control tests passed (11 total in file, including the hard-delete tests)
```

## API Calls

- `GET /api/icoder/tasks/{task_id}` — cross-tenant → 404
- `POST /api/icoder/tasks/{task_id}/cancel` — cross-tenant → 404
- `DELETE /api/icoder/contexts/{context_id}` — cross-tenant → 404

## 根因设计

- 所有 context/task 查询用 `repo.get_for_org(id, org_id)` 过滤
- 查不到行 → `ContextNotFoundError` → HTTP 404(不是 403)
- 404 与 "行不存在" 的响应完全一致 → 租户存在性不可探测
- `ContextIsolationError` 继承 `ContextNotFoundError`,所以 cross-tenant 和 not-found 的响应面一样

## Evidence

- screenshot.png — pytest output

## Corti 对比

- Corti /agents/{id} multi-tenant — 类似
- 差异: iCoDer 显式记录 `current_org` 是 JWT-authoritative 的(Gate 4.2 修复了 header 优先的 bug),且在 task_state_machine + context_lifecycle + audit_log 三个层面同时强制

## Notes

- "404 not 403" 原则: 403 泄露 "资源存在但无权",404 只说 "不存在"
- 当前 dev DB 缺 org_id 列(migrations 未完全应用),但测试用 fixture DB 覆盖了完整 schema
- 审计日志: 每次 cross-tenant reject 写 audit_log(actor=JWT sub, action="cross_tenant_reject")
