# Journey 8 — Context Delete (Real Scrub)

**Verdict**: HUMAN_WORKFLOW_VERIFIED (HARD_DELETE_NOT_STATUS_FLIP)
**Date**: 2026-07-23
**Entry**: `ContextLifecycle.destroy_now()` + 11 R.1.b tests
**User**: admin

## Steps

1. R.1.b 在 `ContextLifecycle` 中新增 `destroy_now(context_id, organization_id=None, reason="user_requested")` 方法
2. `destroy_now()` 与 `destroy_expired()` 区别:
   - 无 EXPIRED 前置条件 — 任何状态都可被立即清除
   - 同时 `hard_delete_context` 关联的 `original_input_audit` 行
3. 新增 `DELETE /api/icoder/contexts/{id}` 端点(Journey 8 入口)
4. cross-tenant 守卫: `organization_id` 不匹配 → `ContextIsolationError`(调用方必须 404,不泄露存在性)
5. 11 个测试覆盖 destroy_now 全路径

## destroy_now() 实现关键路径

```python
async def destroy_now(
    self,
    context_id: str,
    *,
    organization_id: str | None = None,
    reason: str = "user_requested",
) -> None:
    if organization_id is not None:
        row = await self._repo.get_for_org(context_id, organization_id)
        if row is None:
            raise ContextIsolationError(...)  # → 404
    await self._repo.hard_delete_context(context_id)  # REAL DELETE
    await self._emit("context_destroyed", {...})
```

位于 `backend/app/icoder/agent_runtime/context/context_lifecycle.py:262`。

## R.1.b 测试结果

```
tests/test_api/test_a1b_ae_r_1_b_context_scrub_cross_tenant.py
11 passed, 37 warnings in 10.05s
```

覆盖:
- 正常 hard delete(SQL DELETE,不是 status=EXPIRED)
- cross-tenant reject(其他 org 的 context_id → 404)
- ContextNotFoundError 转换为 404(不泄露存在性)
- 原始 input_audit 行同步清除
- destroy_now 事件 emit
- DELETE endpoint 路由测试

## API Calls

- HTTP: `DELETE /api/icoder/contexts/{context_id}` — R.1.b 新增
- Python: `await lifecycle.destroy_now(context_id, organization_id=org_id, reason=...)`

## Evidence

- screenshot.png — pytest 11 passed output

## Corti 对比

- Corti /contexts/{id} DELETE — 类似(管理面清除 session)
- 差异: iCoDer 显式区分 `destroy_expired()` (GC,保留 audit trail) vs `destroy_now()` (user-initiated,清 audit trail)
- `hard_delete_context()` 是物理 DELETE,不是 UPDATE status

## Notes

- 软删 vs 硬删边界: EXPIRED 状态用于 GC 优雅过渡(已过期但仍在保留窗口内);destroy_now 是即时物理删除
- 保留策略: 如果合规 hold 在生效,应在上层拒绝 DELETE,不在 destroy_now 内做判断
- `original_input_audit` 表的清除路径与 `contexts` 同事务,确保无孤儿行
- 调用方必须把 ContextIsolationError 转换为 404(不是 403)以避免泄露存在性
