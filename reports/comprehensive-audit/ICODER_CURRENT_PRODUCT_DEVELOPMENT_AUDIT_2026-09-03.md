# iCoDer Agent 当前产品开发状态全量审查

审查日期：2026-09-03（Asia/Shanghai）

审查基线：`eecfb4eab58d199669b7b14804df190aaeff9be0`

可见分支：`codex/p1-security-multitenant-gates` 指向同一提交；审查 worktree 为 detached HEAD

最近候选标签：`p1-wave5-phase7-1-candidate-20260902` 指向 `e52aa16c`，当前基线比该标签多 2 个提交

范围：代码、测试、迁移、配置、CI、部署文档、生成物和提交历史。未开发新产品能力。

## 1. 结论

当前基线**不具备发布候选资格**。主要原因不是功能覆盖不足，而是两个确定性的发布阻断问题：

1. **P0：OAuth Authorization Code 端点可匿名签发授权码并换取 client owner 身份令牌。**
2. **P0：Alembic head 已是 `073`，生产启动校验仍只接受 `072`，干净迁移后的云应用必然拒绝启动。**

此外还有一个 P1 凭证卫生问题（已提交 admin JWT 响应）、一个 P1 灾备证据缺口（没有可执行 PostgreSQL 备份/PITR/恢复体系或真实恢复证据），以及多个 P2 可维护性和证据治理问题。最近两次安全提交完善了可选高级不可抵赖归档的默认关闭和 JWT issuer/audience 校验，但不能抵消上述阻断项。

推荐下一项开发任务是一个单一、可审查的 **“OAuth Authorization Code fail-closed 与 schema head 一致性发布修复”** 安全批次；先修复 P0 并补齐 PR 门禁，再恢复其他迭代。阿里云 WORM 适配按明确决策继续暂缓，不进入近期实施计划。

## 2. 证据方法与限制

### 2.1 本次实际执行

- `git status --porcelain=v2 --branch`：工作树起始干净，HEAD 为 detached。
- `git log`、`git branch --contains`、`git merge-base`、`git fsck --no-dangling`：确认提交关系；当前基线比 `e52aa16c` 多 2 个提交。
- 全仓 `rg` 盘点技术栈、迁移、SQLite/PostgreSQL、RLS、PHI、HSM、审计、OAuth/JWT、备份恢复和 CI。
- 逐文件核对关键代码：`database.py`、`config.py`、认证/租户中间件、OAuth、RLS 迁移、PHI 加密和软件 HSM、审计归档、管理员接口、CI workflow、部署与轮换文档。
- 使用 Python 3.12 对 `backend/app`、`backend/scripts` 和 Python SDK 执行 `compileall`：通过。
- 统计到 557 个后端测试文件，其中 unit 255、integration 71、e2e 5、e2e_product 2、regression 10。

### 2.2 未能执行，不能算作通过

本地环境没有项目 Python 依赖、`node_modules`、Docker 和 .NET SDK；因此本次未执行 pytest、前端/Node SDK 构建、Python SDK 测试、.NET 构建、PostgreSQL 干净重建及 RLS 攻击测试。工作区运行时仅提供裸 Python 3.12 和 Node 24；`alembic`/`pytest` 不可运行。该限制属于**本次审查环境限制**，不是产品测试失败。

仓库中的旧 JUnit、报告、截图和压缩包仅作为历史材料，不被计为当前 `eecfb4ea` 的重跑证据。GitHub Actions 的最新远端执行状态和真实云环境状态也未在本次本地审查中取得。

## 3. 严重性与状态定义

- P0：可直接造成认证绕过、跨租户/高权限访问或确定性发布失败。
- P1：严重安全、数据保护、灾备或运营风险，发布前必须闭环。
- P2：可靠性、维护性、证据质量或供应链缺口，应进入近期迭代。
- P3：整洁度和长期工程效率问题。
- 已完成：代码与对应门禁/证据均足以支持结论。
- 部分完成：主路径存在，但存在缺口或只在模拟环境证明。
- 未验证：实现看似存在，但本次未得到可执行或外部证据。
- 阻塞：存在确定性缺陷或缺少必要环境/权限，无法宣称就绪。

## 4. 发现清单

### F-001 — P0 / 阻塞：OAuth Authorization Code 流程允许匿名冒用 client owner

证据：

- `backend/app/api/oauth.py:372-410` 的 `/api/oauth/authorize` 没有 `get_current_user`、客户端查询、redirect URI 注册校验、授权同意或服务端用户会话；它直接生成授权码并在 JSON 中返回。
- `backend/app/middleware/tenant_extractor.py:40-55` 将整个 `/api/oauth/` 前缀排除在云租户认证之外。
- `backend/app/api/oauth.py:256-287` 接受该授权码，随后用 `client.owner_id` 生成访问令牌；授权码没有绑定已认证 resource owner。
- 授权码保存在进程内字典，只有 `created_at` 文本，没有兑换时的 TTL 校验；redirect URI 在兑换时也没有与签发时比较。
- 代码返回随机 `refresh_token`，但未发现对应持久化、轮换或 refresh grant 实现。
- 测试检索未发现对此真实授权边界的负面测试。

影响：知道或猜到 `client_id` 的匿名调用方可获取授权码，并按该客户端 owner 身份换取 API token。这是直接身份冒用；若 owner 为管理员或跨租户资源持有者，影响随之扩大。

处置：在修复前禁用 `authorization_code` 和 `/authorize`，或完整实现认证用户、registered redirect URI 精确匹配、PKCE 强制、短 TTL/单次原子消费、state/nonce、客户端类型和用户同意；不得把 client owner 当作自动授权用户。

### F-002 — P0 / 阻塞：生产 schema revision 与 Alembic head 错配

证据：

- `backend/alembic/versions/073_verified_membership_bootstrap.py` 声明 `revision = "073"`、`down_revision = "072"`。
- CI 执行 `python -m alembic upgrade head`，集成测试和 PHI 轮换文档也以 `073` 为当前 revision。
- `backend/app/database.py:15` 仍设置 `PRODUCTION_SCHEMA_REVISION = "072"`。
- `verify_production_database()` 在云启动时要求 revision 精确等于该常量；`backend/app/main.py:129-131` 必定执行它。

影响：任何迁移到最新 head `073` 的 PostgreSQL 都会被应用以“expected 072”拒绝启动。当前 PR 安全 job 只迁移和跑测试，没有执行真实 cloud lifespan/生产启动校验，因此没有捕获该矛盾。

处置：使应用期望 revision 与唯一 Alembic head 自动一致；增加“干净 PostgreSQL迁移 → 最小权限 app role → cloud lifespan 启动”PR 阻断测试，避免手工常量再次漂移。

### F-003 — P1 / 部分完成：仓库提交了 admin 认证响应

证据：`backend/login_resp.json` 包含完整 access token、refresh token、admin 用户名、邮箱、部门和用户 ID。JWT 的 `exp` 已早于本次审查日期，因此当前已过期；无法从本次证据证明其仍可验签。

影响：即使已失效，它仍是敏感认证产物和用户信息进入 Git 历史的事实，表明扫描/清理策略存在路径盲区，并形成错误示范。

处置：从当前树删除；确认签发密钥是否仍存在，必要时轮换；对 Git 对象执行一次当前规则的秘密扫描；在 `.gitignore` 和 CI 中禁止 `*login*resp*`、JWT 结构和认证响应字段组合。

### F-004 — P1 / 未验证：PostgreSQL 备份恢复、WAL/PITR 与升级回滚没有可执行闭环

证据：

- 主仓可见的灾备脚本只有软件 HSM 自包含演练和 PHI artifact scanner。
- `PHI_HSM_ROTATION_AND_ROLLBACK.md` 明确要求在 disposable PostgreSQL 恢复库做真实恢复，但仓库没有通用 `pg_dump/pg_restore`、base backup、WAL archive/restore、PITR 目标时间恢复或校验自动化。
- 云部署文档明确说明备份、调度、告警和执行证据由部署方负责，仓库不声称生产任务正在运行。
- 本次无云账号、托管 PostgreSQL 或对象存储证据。

影响：RPO/RTO、加密备份可读性、WAL 连续性、密钥与数据一致恢复、073→旧版本回退均未获得真实证据。

处置：近期必须完成供应商无关的恢复验收合同和一次真实托管 PostgreSQL 恢复演练。阿里云 WORM 不在此任务内；普通备份/PITR 不能因 WORM 暂缓而延期。

### F-005 — P1 / 部分完成：软件 HSM 是加固模拟，不是硬件安全边界

已完成部分：加密 keystore、独立 bootstrap key、generation floor、防回滚、密钥轮换、DEK rewrap、操作审计链和自包含灾备脚本均存在，云模式有 fail-closed 配置。

剩余风险：密钥材料和解密运算仍在应用主机/进程安全域；文件 ACL、备份、bootstrap key 与 monotonic floor 的外部持久化依赖部署方；本次未执行真实恢复或轮换。

结论：可作为明确接受残余风险的过渡方案，不能标记为“生产 HSM 已完成”。迁移到真实 KMS/HSM 是后续依赖，但不应与当前 P0 修复混合。

### F-006 — P1 / 部分完成：PHI live-path 控制较强，但端到端和 artifact 证据未在当前基线重跑

已完成部分：云配置强制 `edge` redaction，禁止 bypass，PostgreSQL 启动强制加密 provider；revision 069-072 覆盖临床表 RLS 和 71 个 PHI plaintext-clearance 约束；A2A artifact、审计 detail 和 connector egress 有专门控制。

未验证部分：真实 LLM/connector/日志/异常/SSE/备份/WAL 路径未在本次执行；71 个约束为硬编码计数，新增 PHI 列若未更新库存存在漂移风险；SQLite local 明确允许明文，不得用于真实 PHI。

### F-007 — P1 / 部分完成：多租户 RLS 主体完整，但最新 bootstrap 函数与攻击面需当前实跑

已完成部分：revision 064-069 逐域安装并 FORCE RLS；生产启动拒绝 superuser/BYPASSRLS；应用事务绑定租户并重置；存在最小权限角色 provisioning、RLS attack、verified membership PostgreSQL 测试。

未验证部分：本次无法启动 PostgreSQL；revision 073 引入两个 `SECURITY DEFINER` 函数，虽固定 `search_path` 且返回最小布尔/租户值，但必须在非 owner、非 BYPASSRLS app role 下实跑跨租户、异常恢复和并发事务测试。F-002 当前还会阻断这个最新 schema 的生产启动。

### F-008 — P1 / 部分完成：标准审计存在，高级不可抵赖/WORM 默认关闭符合产品决策

已完成部分：标准 `audit_logs`、租户 RLS、detail redaction、保留策略和 signed software-HSM operations journal 仍保留；`ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED` 默认 `false`；关闭时生产启动不再要求高级 signer/archive。高级模式有 PostgreSQL append-only archive、签名链、checkpoint、local WORM simulator 和 AWS S3 Object Lock 适配/策略验证。

边界：local WORM 是模拟证据，AWS S3 测试是控制面/适配合同证据，不是实际 bucket retention、legal hold、IAM 和灾备证据。阿里云 WORM 明确暂缓，不列入近期任务。

### F-009 — P1 / 部分完成：JWT issuer/audience 已补齐，但共享 HS256 密钥仍扩大信任域

已完成部分：最新提交在用户和 OAuth token 签发/验证中加入 issuer/audience；云模式要求非空且二者不同；存在负面单元测试和部署文档。

剩余风险：用户 token 与 OAuth client token 共用 `SECRET_KEY` 和 HS256 对称信任域；密钥持有者既能验签也能签发。没有 JWKS、`kid` 轮换或非对称 issuer 隔离。当前 P0 Authorization Code 绕过使新 claims 不能提供实际保护。

### F-010 — P1 / 部分完成：API Client delegation 具备最小授权数据模型，但创建权限和执行覆盖需强化

已完成部分：client secret 仅一次返回并哈希存储；token 短 TTL、jti、数据库 token hash/revocation、agent allowlist、purpose allowlist、scope intersection 和 owner/client active checks均存在；PostgreSQL bootstrap 查询先解析 tenant 再进入 RLS。

缺口：任意登录用户看起来都可创建 OAuth client，未见组织角色/策略审批；Authorization Code 路径绕过这些安全意图；refresh token 是未实现的表面合同；应补齐“禁用 owner、移除 membership、停用 org、跨租户 client_id、token replay/revoke、agent/purpose 执行点”端到端测试。

### F-011 — P1 / 部分完成：管理员滥用有审计和自保护，但缺少高风险操作的双人控制

已完成部分：平台 admin 与 org roles 分离；修改用户权限有预期 token version、防自改、防移除最后 admin、禁用关联 clients/tokens、系统审计；组织停用和 KMS cache rotation 有 admin 门禁及审计。

剩余风险：单一 platform admin 可跨组织查看/修改；未见 step-up authentication、双人审批、break-glass 时限、理由/工单强制和独立告警。`ICODER_AUDIT_WRITE_PAUSED=true` 可完全跳过 DB 审计写入，虽为 PITR 窗口设计，但需要部署层严格控制和旁路不可关闭日志。

### F-012 — P2 / 部分完成：PostgreSQL 是云权威存储，但 SQLite 仍深植于运行时代码

云模式明确拒绝 SQLite，生产 schema 由 Alembic 管理，这是正确边界。SQLite 仍是默认本地数据库，`database.py`、run trace、STT jobs、schema drift 和多处兼容分支仍依赖它；`requirements-api.txt` 也包含 `aiosqlite`。这不是当前云数据权威性漏洞，但双方言行为差异已经让 RLS、SECURITY DEFINER、约束和锁语义只能在 PostgreSQL 证明。

建议将 SQLite 定义为“非 PHI、单租户、开发 smoke”，所有安全/迁移/并发验收以 PostgreSQL 为唯一门禁；逐步让默认开发 Compose 使用 PostgreSQL，SQLite 只保留显式轻量 profile。

### F-013 — P2 / 部分完成：CI 面较广，但触发与启动验收有缺口

优点：PR 包含前端、后端 unit、三套 SDK、OpenAPI/preflight，以及专门的 PostgreSQL PHI/RLS gate；依赖多数固定版本并运行 pip/npm audit。

缺口：integration/regression/e2e 在普通 PR 上不是默认阻断，仅在标签、主分支或定时运行；安全 job 没有 cloud app lifespan 启动，导致 F-002 逃逸；真实 LLM 会在无 secret 时跳过；`sdk-web` 使用 `npm install` 而非 `npm ci`；未见 SAST、SBOM、container scan、provenance/signing 或迁移 downgrade/rollback 总门禁。

### F-014 — P2 / 未验证：前端与三套 SDK 代码/版本齐全，但当前构建证据不足

JS、Python、.NET SDK 版本均为 beta.50，接口资源和测试数量可观；前端有 TS/Vite/Vitest/Playwright 配置。当前本机没有依赖和 .NET SDK，不能宣称构建通过；历史制品目录仍含 beta.14-beta.22 等旧包，容易与 beta.50 混淆。应用/前端仍显示 1.0.0，而 SDK 为 beta.50，应明确这是产品版本与 SDK prerelease 版本的有意差异或统一 release manifest。

### F-015 — P2 / 部分完成：候选基线身份不够强

当前 checkout 是 detached HEAD；分支指向相同提交，但最近 candidate tag 停在两次提交之前。最近提交均显示 Git 签名状态 `N`（无签名）。因此可以精确复现 SHA，却不能把旧 tag 当作当前候选，也缺少签名 tag/commit 的供应链身份保证。

### F-016 — P3 / 未完成：生成产物与历史证据显著污染主仓

至少 283 个 tracked 路径命中 `dist/`、tgz/whl/tar.gz、JUnit、`outputs/`、`golden_captures/` 或 `gate4r_diff/`。`reports/release-candidate` 中保留多代 SDK 包，`packages/icoder-web/dist` 也被追踪；还有整个 `archive/` 和大量旧报告。虽然工作树干净，但仓库不整洁，增加 clone、扫描、审查和“哪份证据有效”的成本。

建议建立证据 manifest + retention policy，把可再生二进制和历史 JUnit 移到 CI artifact/object storage；只保留小型、去敏、内容寻址的最终证明。此清理应独立提交，不能和安全修复混合。

## 5. 各审查域状态汇总

| 审查域 | 状态 | 判断 |
|---|---|---|
| Git/候选基线 | 部分完成 | SHA 可复现，工作树干净；detached、tag 落后 2 提交、无签名 |
| 目录/生成物 | 未完成 | 大量历史报告和构建产物被追踪；存在 `login_resp.json` |
| 后端 | 阻塞 | 架构和测试面广，但 OAuth P0 与 schema P0 阻断 |
| 前端 | 未验证 | CI 配置存在；本次未安装依赖/构建 |
| JS/Python/.NET SDK | 未验证 | beta.50 源码和测试存在；本次仅 Python 语法通过 |
| PostgreSQL 权威存储 | 部分完成 | 云 fail-closed；SQLite 仍为 local 默认且多处分支 |
| 迁移/干净重建 | 阻塞 | 073 为线性最新迁移；生产只接受 072 |
| RLS/跨租户 | 部分完成 | FORCE RLS、角色门禁、攻击测试存在；本次未实跑 073 |
| PHI live-path | 部分完成 | edge redaction/egress/约束存在；真实全路径未重跑 |
| 静态加密/软件 HSM | 部分完成 | 过渡方案较完整；不是硬件边界，真实 DR 未验证 |
| 密钥轮换/灾备 | 部分完成 | 自包含演练存在；真实 DB+key 联合恢复未验证 |
| 标准审计 | 部分完成 | 默认存在；audit pause 需旁路治理 |
| 高级不可抵赖/WORM | 部分完成、默认关闭 | 产品默认正确；只有模拟/AWS 合同证据，无真实云证明 |
| API Client/OAuth | 阻塞 | client_credentials 较完整；authorization_code 可匿名冒用 |
| JWT issuer/audience | 已完成（代码级） | 签发与校验已绑定；尚无本次运行证据，HS256 信任域仍大 |
| 管理员滥用 | 部分完成 | 审计/自保护存在；缺双人控制与 step-up |
| 备份/WAL/PITR | 未验证 | 文档要求存在；无可执行平台闭环/真实恢复证据 |
| CI/依赖/部署文档 | 部分完成 | 覆盖广；普通 PR 非全矩阵，缺 cloud startup gate |
| 真实云证据 | 阻塞 | 本次没有云账号、托管 DB、KMS、bucket 或监控证据 |

## 6. 迭代路线图

### Phase 0：立即冻结发布（0-2 天）

1. 禁用或修复 Authorization Code 流程；增加利用链回归测试。
2. 修正 production schema head 校验，并在 PR 中加入 clean PostgreSQL cloud-start gate。
3. 删除 `backend/login_resp.json`，完成密钥影响判断和 Git object 扫描。
4. 以上拆成最多三个主题清晰的提交，不夹带新功能。

退出条件：两个 P0 回归测试先红后绿；cloud lifespan 在 073 + 最小权限角色启动；秘密扫描无高置信命中。

### Phase 1：安全与数据发布门禁（3-7 天）

1. 将 PostgreSQL PHI/RLS/OAuth attack matrix 固化为普通 PR 阻断项。
2. 覆盖 073 SECURITY DEFINER 函数的跨租户、异常恢复、并发和权限测试。
3. 对 PHI 列库存、ORM、Alembic constraints 和 artifact scanner 建立自动一致性检查，替代仅靠常量 `71`。
4. 为高风险 admin 操作加入 step-up、理由/工单、独立告警；设计双人控制但可分阶段落地。

### Phase 2：真实恢复能力（1-2 周）

1. 定义 RPO/RTO、备份加密、WAL 连续性、密钥/keystore/floor 联合恢复合同。
2. 在 disposable 托管 PostgreSQL 执行 base backup/逻辑备份 + WAL/PITR 恢复。
3. 从备份恢复到 073，以 app role 启动，执行跨租户/PHI canary/审计连续性测试。
4. 执行升级失败与应用回滚演练，记录不可逆迁移的 maintenance-window 策略。

说明：此阶段不包含阿里云 WORM 适配；普通 PostgreSQL 恢复和 PHI/WAL 安全必须独立完成。

### Phase 3：供应链与仓库治理（1 周）

1. 全量 SDK/frontend/backend clean checkout 构建与 lockfile 验证。
2. SBOM、依赖漏洞、container scan、artifact provenance/signing。
3. 清理或外移 tracked 二进制、JUnit 和过期报告；建立证据 manifest、有效期和来源分类。
4. 创建当前 SHA 的签名 candidate tag，并使 release manifest 唯一指向该 SHA 和 beta.50 制品。

### Phase 4：真实云预生产验收（依赖环境，1-2 周）

1. 在目标云建立最小权限网络、PostgreSQL、secrets/KMS/HSM 替代或正式接受 software-HSM 残余风险。
2. 验证日志、指标、告警、审计 sink、备份和恢复；执行 tenant attack 与 PHI egress canary。
3. 输出真实云证据包，所有模拟结果标注 `simulation`，不得混写为 production proof。

## 7. 推荐的下一项开发任务

任务名：**P0 Release Gate — OAuth Authorization Code fail-closed + Alembic head/cloud-start consistency**

范围：只处理 F-001、F-002 及其测试/文档；不增加新产品能力，不实现阿里云 WORM。

建议分为两个可独立审查的提交：

1. `fix(security): fail closed unsafe oauth authorization code flow`
2. `fix(database): bind cloud startup gate to alembic head 073`

若短期没有完整 OAuth Authorization Server 需求，最安全且最快的选择是明确移除/返回 `unsupported_grant_type`，只保留已治理的 client_credentials；完整用户授权流程另立设计任务。

## 8. 验收标准

### OAuth

- 未认证请求不能获得 authorization code。
- 未注册/禁用 client、未注册 redirect URI、无/错误 PKCE、过期 code、重复兑换、client/redirect 不匹配全部失败。
- code 原子单次消费且持久化或采用可证明的共享短期存储；多 worker 行为一致。
- token subject 是真实授权用户，不得自动等于 client owner；包含正确 org/issuer/audience/jti。
- 若不支持 refresh grant，不返回 refresh token；若支持，必须持久化、哈希、轮换和撤销。
- 包含从 `/authorize` 到受保护资源的负面端到端测试。

### 数据库启动

- 自动证明 Alembic 只有一个 head，当前为 `073`。
- 空 PostgreSQL 16 以 migration role 执行 `upgrade head` 成功。
- 非 superuser、非 BYPASSRLS app role 完成 cloud lifespan 启动。
- 启动后校验所有 RLS/NOT NULL/PHI constraints 和可选审计 feature flag 两种模式。
- 增加测试确保新增 migration 未同步 production gate 时 PR 失败。

### 仓库与证据

- `backend/login_resp.json` 不再存在于当前树；秘密扫描覆盖 Git objects 并输出机器可读结果。
- 所有测试结果标注 commit SHA、运行环境、模拟/真实类型和时间；旧报告不作为当前通过证据。
- 完成后工作树干净，每个提交只含对应主题。

## 9. 风险与依赖

- 完整 OAuth Authorization Code 实现需要产品确认：是否真的需要用户 delegation、哪些客户端是 public/confidential、redirect URI 注册和 consent UX。若未确认，应先禁用。
- PostgreSQL clean-start/RLS 验收需要 Docker 或可抛弃 PostgreSQL 16；真实恢复需要托管数据库和备份权限。
- 软件 HSM 继续用于生产需要书面风险接受、独立 secret 注入、ACL、备份和 monotonic floor 外部存储。
- 真正 KMS/HSM、真实审计 sink、监控和备份均为部署环境依赖，不能由本地 fixture 证明。
- 阿里云 WORM 适配明确暂缓；路线图不以其为依赖，也不把暂缓视为当前缺陷。

## 10. 最终发布判断

`eecfb4ea`：**NO-GO**。

重新评审的最低入口：F-001、F-002、F-003 关闭；在 clean PostgreSQL 16 上完成 migration + least-privilege cloud startup + RLS/OAuth attack gate；并提供与当前 SHA 对应的 CI 结果。真实云、PITR 和 software-HSM 风险接受仍是进入生产前的独立强制条件。
