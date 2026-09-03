# 目录清理审计（2026-08-31）

绑定产品源码候选：`a010294f5faf26f49164a78475736c094ed5fc9c`

## 已执行的安全清理

本轮删除约 987 MB 可再生产物，包括 Node 依赖目录、Python 缓存、.NET
`bin/obj/artifacts`、SDK 构建包、运行日志、临时数据库证据和 runtime 报告。
这些目标均在删除前确认未被 Git 跟踪。连同前一轮约 345 MB，累计清理约
1.30 GB。删除不可直接恢复，但都应由依赖安装、构建或测试重新生成。

## 顶层目录结论

| 目录 | 当前约占用 | 结论 | 后续可删除内容 |
|---|---:|---|---|
| `.github/` | <1 MB | 保留 | 无 |
| `.claude/` | <1 MB | 本地状态 | `settings.local.json` 含本地配置，确认不再使用后可删 |
| `.icoder/` | 1.93 MB | 先备份 | registry 及备份可能是用户运行状态，不自动删除 |
| `backend/` | 4.70 GB | 保留源码 | 见下方 backend 专项 |
| `frontend/` | 1.58 MB | 保留 | `node_modules` 已删；后续只清理新生成的 `dist/test-results/playwright-report` |
| `packages/` | 1.67 MB | 保留 | Node、Python、.NET 构建输出已删；以后由 CI 生成 |
| `reports/` | 231.12 MB | 保留但需治理 | 85 组重复内容、452 个文件，约 10.57 MB 冗余；先做引用闭合再删 |
| `docs/` | 103.46 MB | 保留正文 | 约 26.63 MB 原始 Corti 抓取、34.18 MB 早期归档、9.30 MB parity 截图可条件删除 |
| `archive/` | 1.11 MB | 历史 | 确认不再需要对照实现后可整体迁出主仓库 |
| `outputs/` | 2.92 MB | 历史证据 | 禁止新增；引用迁入 canonical reports 后可删 |
| `gate4r_diff/` | 2.33 MB | 历史证据 | 最终摘要保留，nodeid/中间差分可在引用审计后删 |
| `data/` | 4.91 MB | 本地运行数据 | `test.db`、`icoder.db` 先备份或确认无业务数据后可删 |
| `tools/` | <1 MB | 保留源码 | Playwright `node_modules` 已删 |
| `phase7-external-consumer/` | <1 MB | 保留测试夹具 | `node_modules` 已删 |
| `web-components/` | <1 MB | 过渡模块 | 完成 `packages/icoder-web` 迁移后可删除整个旧目录 |
| `examples/` | <1 MB | 保留 | 两个示例 `.env` 需轮换凭据并确认后删除，不应入库 |

## backend 专项

| 路径 | 约占用 | 建议 |
|---|---:|---|
| `backend/data/medcoder/models/` | 4.35 GB | 可重下但成本高；确认下载来源、版本和缓存策略后删除 |
| `backend/data/medcoder/faiss*.index` | 201 MB | 可由构建脚本重建；先让 CI/文档证明重建成功再删 |
| `backend/data/medcoder/metadata*.pkl` | 8.8 MB | 必须与索引成组处理，不单独删除 |
| `backend/data/*.db` | 约 31 MB | 测试/本地数据库；确认无唯一迁移证据后删除 |
| `backend/.icoder/` | 21.42 MB | Agent registry/runtime 状态；先导出或备份 |
| `backend/.env` | <1 MB | 不入库；凭据已迁入安全存储且完成轮换后删除 |
| `backend/docs/corti_parity/` | 6.05 MB | 未跟踪历史资料；确认 canonical 文档已覆盖后删除 |

## docs/reports 条件删除清单

- `docs/corti-reverse-engineered/`：已提交测试需要的紧凑 Markdown/JSON；其余
  约 26.63 MB HTML、截图和抓取 JSON 可删除或移出仓库目录。
- `docs/archive/corti_reference_early/`：约 34.18 MB；确认无审计/许可保留义务后删除。
- `docs/corti_parity/**/screenshots/`：约 9.30 MB；canonical 报告已有截图哈希后删除。
- `docs/reverse_engineering/corti/`：约 1.55 MB；与新契约夹具去重后删除。
- `reports/phase-a1b/agent-expert-reverification/evidence/journeys/`：重复内容最集中；
  保留每个 journey 的最小成功/失败样本及 manifest，其余重复运行可删除。
- `reports/agent_hub/`：重复 replay 和阶段性响应可按“最终报告引用到的最小证据集”收缩。

以上条件删除项本轮未自动删除，因为其中可能存在唯一审计证据、授权不明的
外部资料或用户运行状态。删除前必须先生成引用清单和备份/迁移记录。

