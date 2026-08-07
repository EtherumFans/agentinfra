# iCoDer 文档站 (docs-site)

基于 **Docusaurus 3** 的开发者文档站。本目录是 **Sprint 1 脚手架** —— 站点结构、i18n
配置、导航就位, 但内容迁移与发布部署在 Sprint 2 完成。

## 当前状态 (Sprint 1)

- ✅ Docusaurus 3.5.2 + classic preset + TypeScript 配置
- ✅ zh-CN 默认 locale (i18n 框架)
- ✅ Sidebar 结构 (`sidebars.ts`) + 3 个占位页
- ✅ Intro 页 (`docs/intro.md`) 指向 CLAUDE.md + ADR
- ✅ `.gitignore` (node_modules / build / .docusaurus)
- ⏳ `npm install` + `npm run build` 验证 (Sprint 2)
- ⏳ DNS `docs.icoder.cloud` + TLS 证书 (Sprint 2, R6 ADR 条件)
- ⏳ 部署到 Vercel / Netlify / Cloudflare Pages (Sprint 2)
- ⏳ 5-10 篇核心文档从 `docs/` 迁移 (Sprint 2)

## 本地预览 (Sprint 2 之后才可用)

```bash
cd docs-site
npm install      # 需要先执行 (不在 Sprint 1 范围)
npm run start    # http://localhost:3000
npm run build    # 生产构建 (输出 build/)
```

## 已知限制

1. **GitHub editUrl 指向占位 repo** — `icoder-cloud/icoder-docs` 仓尚未公开创建。
   Sprint 2 任务: 创建 monorepo 子目录 or 独立 docs repo。
2. **logo.svg / favicon.ico 缺失** — 当前 `static/img/` 目录不存在。
   Sprint 2 任务: 设计 logo + 复制到 `static/img/`。
3. **依赖未安装** — Sprint 1 故意不跑 `npm install`, 避免 node_modules 体积膨胀。
4. **部署未启动** — 见 [DEPLOYMENT_PATH_ADR](../docs/governance/DEPLOYMENT_PATH_ADR.md) R6 cloud-only 决策。

## Charter 合规性

- **5-tuple**: 不与本 scaffold 交互 (GATE4_8 / GATE4_9 / GATE4_ACCEPTANCE /
  CORTI_PARITY / PRODUCTION_READINESS 全部不变)
- **8 个禁用 verdict**: 本 scaffold 不宣称任何 charter verdict
- **12 个禁用 git ops**: 无 push, 无 master, 无 amend, 无 `-A`, 无 force
- **货币约定**: 所有金额引用使用 CNY (¥) — Phase 5 A2

## Sprint 2 迁移清单 (待执行)

从 `docs/` 目录迁移到 `docs-site/docs/`:

| 源文件 | 目标位置 | 优先级 |
|--------|---------|--------|
| `docs/QUICKSTART.md` | `docs-site/docs/quickstart.md` | P0 |
| `docs/SDK-TUTORIAL.md` | `docs-site/docs/sdk/tutorial.md` | P0 |
| `docs/sdk/*.md` | `docs-site/docs/sdk/*.md` | P0 |
| `docs/cloud/CLOUD_DEPLOYMENT.md` | `docs-site/docs/deploy/cloud.md` | P1 |
| `docs/agent-pack.md` | `docs-site/docs/agent-pack/format.md` | P1 |
| `docs/ICODER_V1_A2A_SPEC.md` | `docs-site/docs/protocol/a2a.md` | P2 |
| `docs/ICODER_V1_MCP_SPEC.md` | `docs-site/docs/protocol/mcp.md` | P2 |
| `docs/ICODER_V1_AGENT_CARD_SPEC.md` | `docs-site/docs/protocol/agent-card.md` | P2 |
| `docs/architecture/*.md` | `docs-site/docs/architecture/*.md` | P3 |
| `docs/governance/*.md` | `docs-site/docs/governance/*.md` | P3 |
