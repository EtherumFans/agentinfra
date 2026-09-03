# 可信开发基线复核（2026-08-31）

产品源码候选提交：`a010294f5faf26f49164a78475736c094ed5fc9c`  
起始比较提交：`4fc31b3c012c49d09c6b3b01d3c67e25049efe98`  
状态：**候选基线已冻结，但尚未达到“全部受支持验证可一键复现”的完成标准**

## 执行结论

本轮没有加入新产品能力。工作集中在清理、可复现入口、依赖闭合、
临床码表完整性锚、契约测试夹具、迁移验证和基线证据治理。

从 `4fc31b3c` 到产品源码候选提交的实际差异为 15,842 个路径，而不是最初
工作副本观察到的 1,198 项。原因是首次冻结时将大量未跟踪报告和证据纳入了
Git。当前按路径分类如下：

| 分类 | 路径数 |
|---|---:|
| 产品源码/配置 | 1,045 |
| 数据库迁移 | 33 |
| 测试 | 373 |
| SDK | 116 |
| 文档/归档 | 198 |
| 生成报告/证据 | 14,077 |
| 合计 | 15,842 |

14,077 个报告/证据路径占绝对多数，说明报告治理而非新功能开发是当前仓库
可审查性的主要风险。

## 八项完成标准

| 标准 | 状态 | 证据/阻断 |
|---|---|---|
| 冻结工作副本 | PASS | 本轮没有增加产品能力；源码候选提交已固定 |
| 变更分类 | PASS | 以上 6 类共 15,842 路径 |
| 清理缓存和生成物 | PASS/持续 | 本轮额外清理约 987 MB；连同前轮约 345 MB，共约 1.30 GB |
| 按主题拆分提交 | PARTIAL | 源码与证据分开，但 `f5a91ca3` 仍包含 14,262 个文件，不满足易审查要求；未授权历史重写 |
| 标签和完整清单 | PARTIAL | 旧标签仍是初始冻结点；待本报告提交及 clean manifest 后创建 v2 标签 |
| 干净 checkout 重建环境 | PARTIAL | Python 依赖从零安装成功；Node 缺 npm 且 Registry 超时；.NET 仅有 Runtime、无 SDK |
| PR CI/集成/迁移/SDK/前端 | FAIL | 迁移、Python SDK、OpenAPI 通过；后端、Node/.NET、Docker 集成仍有阻断 |
| 报告源码哈希闭合 | PASS_WITH_POLICY | 26 个唯一 Git 哈希全部可解析；历史报告保留原始来源，当前基线报告绑定本候选提交 |

## 干净 checkout 验证结果

在系统临时目录中以 detached HEAD 检出 `a010294f` 后执行：

| 验证 | 结果 |
|---|---|
| 基线 manifest 自校验 | PASS，`DEVELOPMENT_BASELINE_VERIFIED paths=0` |
| 临床码表 Git 规范化字节完整性 | PASS，39,756 个诊断、28,394 个操作编码 |
| 必需 Corti 契约夹具存在 | PASS |
| Python requirements 从零安装 | PASS（本机 Python 3.12；CI 定义使用 3.11） |
| 基线/发布治理测试 | PASS，8 项 |
| SQLite 迁移与 schema drift | PASS，10 项 |
| Python SDK | PASS，104 项并成功构建 wheel |
| SDK 跨语言版本 | PASS，`1.0.0-beta.50` |
| OpenAPI 快照 | PASS，重新导出后 `--check` 通过 |
| 后端 PR 单测 | FAIL：5,015 pass、53 skip、105 fail、27 error；补齐契约夹具后失败子集剩余 104 项 |
| 前端干净安装/构建 | BLOCKED：主机无 npm，临时获取 npm 时 Registry 超时；原工作副本构建曾通过，不等于干净复现 |
| JavaScript/Web SDK | BLOCKED：同上 |
| .NET SDK | BLOCKED：只有 .NET 8 Runtime；临时安装 8/10 SDK 时网络安装长期无进展 |
| Docker/PostgreSQL 集成/E2E | BLOCKED：本机无 Docker |
| 部署预检 | FAIL：临床码表镜像所有权检查、ML 资产版本/哈希检查未通过 |

后端剩余失败主要归为四类：

1. 测试依赖仓库外 `ICODER_DATA_ASSET_DIR` 临床资产，CI 当前没有供应机制；
2. FAISS、Torch、sentence-transformers 等 ML 测试与默认 API requirements 的隔离策略冲突；
3. 音频流测试依赖可用解码器/运行时配置；
4. 由上述资产缺失连锁触发的 Agent readiness、治理 provider 和部署预检失败。

## 已修复的确定性问题

- detached checkout 不再因为分支名不同而误报基线漂移；
- 临床码表信任锚绑定 Git LF 规范化后的真实字节，而非提交前 CRLF 字节；
- 默认 requirements 和 runtime 包声明补齐 `filelock==3.32.4`；
- 只纳入干净测试必须的紧凑 Corti 契约文件，继续忽略 26 MB 原始抓取物；
- `.venv/` 纳入忽略规则；
- 新增 `scripts/release/verify_development_baseline.ps1`，在完整工具链主机上可一键重放 PR 门禁，并以 `-Full` 追加 Docker 集成/E2E；
- OpenAPI 快照重新生成并通过漂移检查。

## 后续开发顺序

在恢复产品功能开发前，依次完成：

1. 明确外部临床资产的 CI 供应方式；没有许可和来源证明时不得直接提交资产；
2. 将 ML 测试从 API 单测门禁中隔离为明确的 ML worker gate，或提供 hermetic fake；
3. 在具备 npm、Node 22、.NET 8/10 SDK 和 Docker 的 runner 上执行一键脚本；
4. 修复剩余后端失败并取得完整 PR CI 绿色结果；
5. 对 14,077 个证据路径建立 canonical/历史/中间产物分层，再决定是否重写候选分支历史；
6. 全部门禁通过后创建最终而非候选的开发基线标签。

