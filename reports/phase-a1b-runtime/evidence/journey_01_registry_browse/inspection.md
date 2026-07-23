# Journey 1 — 浏览专家注册表

**Verdict**: HUMAN_WORKFLOW_VERIFIED
**Date**: 2026-07-23
**URL**: http://127.0.0.1:5173/ai-studio/experts
**User**: admin (admin@icoder.ai, 系统管理员)

## Steps

1. 登录 admin / admin123 — 成功跳转 `/`
2. 导航 `/ai-studio/experts` — 新页面加载
3. 显示 30 Experts + 5 Presets(9 Corti §3.2 Expert + 21 ICODER 独有 Experts)
4. Preset 目录展示 5 个 Preset,标注"已物化"(delegates_to_pack 非 null)

## Evidence

- screenshot.png — 全页面截图,含侧边栏 + 主内容

## API Calls

- `GET /api/v1/experts` → 200,30 Experts(包含 canonical_key / origin / corti_alignment)
- `GET /api/v1/presets` → 200,5 Presets(包含 delegates_to_pack)
- `GET /api/v1/experts/external-gate/evaluate?expert_key=...` × 5 → 每个 gated Expert 1 次

## Corti 对比

- Corti /experts 列表 — 类似(分卡片+搜索)
- 差异: iCoDer 加了 "外部出口" 决策展示(放行/需许可证/区域受限),Corti 无此 UI

## Notes

- ExpertsPage 是 R.5 新建的页面
- TypeScript 编译通过(tsc --noEmit 无错误)
- Vite HMR 热重载无报错
