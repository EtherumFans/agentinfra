# Journey 10 — Logout Storage Cleanup

**Verdict**: HUMAN_WORKFLOW_VERIFIED (ALL_ICODER_KEYS_SWEPT)
**Date**: 2026-07-23
**Entry**: `frontend/src/store/index.ts` `clearAllIcoderBrowserStorage()`
**User**: admin → logout

## Steps

1. 用户登录 → localStorage 写入 10 个 key:
   - `access_token`,`refresh_token`(JWT)
   - `icoder-auth`(zustand 持久化 blob)
   - `icoder-textgen-templates`(用户保存的模板,可能含粘贴的 PHI)
   - `icoder-project-name`,`icoder-billing-alerts`,`icoder-billing-autotopup`
   - `icoder-settings`,`icoder-agent-runtime-mode`,`icoder-theme`
2. 用户点击 Logout 按钮
3. `useAuthStore.logout()` 调用 `clearAllIcoderBrowserStorage()` → 10 个 key 全部 `removeItem`
4. 同时 set 状态清空 user/accessToken/organizations/currentOrgId
5. sessionStorage 由 clearPatientContext / clearSession 在 PatientContext组件卸载时清理(Gate 11)

## 代码路径

`frontend/src/store/index.ts:81-90`
```typescript
logout: () => {
  // Phase A1A Gate 4.6 — clear ALL icoder-* localStorage + auth tokens.
  clearAllIcoderBrowserStorage();
  set({ user: null, accessToken: null, refreshToken: null,
        isAuthenticated: false, organizations: [], currentOrgId: null });
},
```

`frontend/src/store/index.ts:29-34`
```typescript
export function clearAllIcoderBrowserStorage(): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  for (const key of ICODER_LOCALSTORAGE_KEYS) {
    try { window.localStorage.removeItem(key); } catch { /* ignore */ }
  }
}
```

## API Calls

- 无 HTTP 调用 — logout 是纯前端清理
- 可选: 调用 `POST /api/auth/revoke-tokens` 服务端吊销 refresh_token(如果用户主动选择)

## Evidence

- screenshot.png — 10 localStorage keys 列表 + logout 后 `localStorage.length=0`(icoder-* 部分)

## Corti 对比

- Corti /logout — 类似
- 差异:
  - iCoDer 显式维护 canonical key 列表 (`ICODER_LOCALSTORAGE_KEYS`) 并暴露 `listIcoderBrowserStorageKeys()` audit helper
  - Gate 4.6 新增的 `clearAllIcoderBrowserStorage` 比 Corti 多覆盖 6 个偏好键,防止 shared machine 上继承前任用户设置
  - Phase 6 Gate 2 补充 `clearPatientContext` / `clearSession` 在组件卸载时清 sessionStorage

## Notes

- 关键陷阱(Phase A1A Gate 4.6 修复前): 旧版 logout 只删 `access_token` + `refresh_token`,留 `icoder-textgen-templates` 可能含 PHI 在磁盘上
- 浏览器隐私模式 + 本地开发场景特别需要这种 sweep — 共享机器的次位用户不会继承前位用户的模板
- `partialize` 中 zustand 只持久化 user/organizations 等,token 单独走 `localStorage.setItem` 不进 zustand blob
- 未来新增 localStorage key 必须加入 `ICODER_LOCALSTORAGE_KEYS` 否则不会被 sweep(测试 `tests/browser/storage-audit.test.ts` 计划强制这点,但还在 TODO)
