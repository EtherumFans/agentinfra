# Agent Hub、SDK 与部署模拟状态（2026-08-13）

## 结论

本阶段已关闭 Agent Hub 范围内可在开发环境验证的主要工程缺口，但不能据此宣称“已生产上线”或“已完整复刻 Corti”。

- 磁盘共 32 个 Agent Pack；26 个 Hub 可见 Agent 全部为 executable、Provider 可解析且 `launch_candidate_ready=true`。
- 其余 6 个 Pack 均隐藏：5 个 metadata-only 的内部/兼容阶段 Pack，1 个隐藏的可执行内部引擎；它们不属于 26 个用户可见 Agent。
- 26 个可见 Agent 的统一运行、Discovery、A2A 路由、输入安全、审计与输出契约已形成自动化门禁。
- 原有 6 个 Environment/Tenant 公开 501 接口已替换为真实声明式目录、Organization 租户兼容投影和安全 dry-run 部署计划。
- JavaScript SDK 编译通过；Python SDK 4/4 测试通过并成功构建 wheel；.NET SDK 使用用户级便携 .NET 8.0.424 完成新鲜编译、9/9 测试和 `1.0.0-beta.2` NuGet/符号包构建。net10.0 仍需相应 SDK/CI 验证。
- 与 Agent Hub/SDK 改动同一候选上的原子 CDI 40 例真实 E2E 为 40/40 HTTP 成功、40/40 查询数安全范围达标；该证据证明开发候选可运行，不等于临床生产批准。

## 本阶段关闭的缺口

### 1. Agent 输出契约单一事实源

此前统一运行接口维护一份手写 Agent ID 到输出契约的映射，26 个可见 Agent 中有 8 个与 Pack 的 `output_contract.schema_ref` 不一致。现已改为直接读取正在执行的 Agent Pack：

- 响应投影使用 Pack 声明的 `schema_ref`；
- 结构化结果检查 Pack 声明的 `required_fields`；
- 缺少必填字段时标记 `output_contract_violation`，保留原始输出供人工查看，并强制人工复核；
- Pure LLM 与 LLM-with-tools 的 Run Trace 审计事件也记录具体 Pack 契约，不再记录通用 Provider 契约。

### 2. A2A Task 与 Agent 全量路由

源代码中仍把已实现的 Task 状态机称为 stub，现已修正文档和注释。真实实现及验证包括：

- `tasks/get`、`tasks/cancel` 持久化状态机；
- 非法状态转换拒绝；
- 跨租户任务读取/取消隔离；
- 26 个可见 Agent 的动态 A2A URL 均可执行或安全失败，不存在“有卡片、死路由”；
- 共享输入安全边界覆盖全部 26 个 Agent。

### 3. Environment 与 Tenant 开发态部署模拟

环境目录以 `deploy/cloud/regions.yaml` 为单一事实源：

- `GET /api/platform/environments` 返回 EU、US、CN 环境及真实声明状态；
- `GET /api/platform/regions` 返回 6 个声明区域、合规/数据驻留与 SLA 元数据；
- 所有当前未开通区域明确返回 `declared_not_provisioned`；
- `POST /api/platform/environments` 仅产生 `dry_run=true` 部署计划，拒绝直接云开通；
- `GET /api/tenants/current` 将现有 Organization 主数据投影为 Corti 风格 Tenant；
- Tenant 创建仍落到 Organization 主数据，环境分配仅允许目录中的 `eu/us/cn`；
- Tenant 环境查询强制当前租户边界，并保留 `environment_provisioned=false`。

这些接口证明控制面契约与部署计划可以在开发环境工作，不证明任何云资源已经创建。

### 4. SDK

JavaScript、Python、.NET 均新增 Environment/Region/Tenant 资源：

- 列出环境；
- 列出区域；
- 生成安全 dry-run 环境计划；
- 读取当前 Tenant；
- 读取 Tenant 环境分配。

## 验证结果

| 验证组 | 结果 |
|---|---:|
| 输出契约投影与 StructuredOutputProjector | 24 passed |
| Pure LLM / LLM-with-tools / 公共投影 | 36 passed |
| Agent Hub 权威运行矩阵 | 3 passed |
| A2A Task 状态机、跨租户与协议端点 | 50 passed |
| 26-Agent Hub、统一运行、可见性和 A2A 路由 | 62 passed |
| Environment/Tenant 与本阶段总回归 | 64 passed |
| 本阶段后端 pytest 合计（各次执行） | 243 passed |
| Python SDK | 4 passed；wheel 构建成功 |
| JavaScript SDK | TypeScript 编译成功 |
| .NET SDK | net8.0：9/9 passed；beta.2 NuGet/符号包成功；net10.0 未验证 |
| 同候选原子 CDI E2E | 40/40 HTTP；40/40 查询数范围达标；27 条最终查询 |
| Windows 原生依赖失败关闭 | Torch/sentence-transformers 4 项既有测试 + PyArrow 2 项新增测试；合计 6 passed |
| Agent 示例门禁、统一契约、投影、CDI、规则、工具检索、工具预算终态与 26-Pack 安全属性加严回归 | 136 passed |
| .NET SDK net8.0 新鲜验证 | 9/9 passed；`1.0.0-beta.2` nupkg/snupkg 构建成功 |
| 云配置失败关闭与部署静态预检 | 60 passed；18/18 静态检查通过 |
| PHI、租户、MCP、CORS、审计安全组合回归 | 150 passed |
| 最终部署/安全/环境合并回归 | 215 passed |
| 前端单元测试与生产构建 | 82 passed；TypeScript + Vite 构建成功、零构建告警 |
| JavaScript / Python SDK 新鲜验证 | JS TypeScript 成功；Python 4/4 + `1.0.0b3` wheel 成功 |
| 供应链与框架迁移 | API、开发、可选 ML 三套 `pip-audit` 均 0；前端完整 `npm audit` 0；迁移回归 1716/1716 passed |

权威清单：

- `reports/agent_hub/agent_hub_runtime_matrix.json`
- `reports/agent_hub/agent_hub_runtime_matrix.md`

## 与 Corti 的剩余差距

### 26-Agent 示例级上线候选门禁

- 新增串行、可续跑的 `backend/scripts/corti_parity/run_agent_hub_examples_e2e.py`；它拒绝在进程已加载 Torch/PyArrow 时继续，并拒绝 `finish_state=failed/incomplete`、mandatory tool 未完成和 max-tool-rounds 超限，避免降级结果假绿。
- 26 个可见 Agent 的 Pack 示例现为 **26/26 通过**：统一运行、provider completion、工具无错误、必填输出契约、结构化提取、人工复核、trace 标识、生产写回阻断、高风险内容安全和临床数量溯源断言均通过。数量溯源仅放行输入/成功工具原值、可复算的时间差和同一范围内的单位继承；新的独立临床阈值仍被拦截。
- 医疗编码统一接口已复用既有 V1→V2 Corti-style 八字段投影，同时暂留 `codes` 兼容字段；CDI 统一接口已复用既有 A2A CDI 编排器；合规护栏复用官方 CG-001..CG-004 确定性规则实现。
- 证据：`backend/reports/agent_hub/examples_e2e_20260813/agent_hub_examples_e2e.md` 与同目录 JSON/逐 Agent 响应。
- 诊断提取在 BGE 禁用时使用精确目录词法 fallback（37,897 项只读 ICD-10-CN catalog），工具来源标记为 `lexical_catalog_fallback`；不做不受控模糊匹配，也不加载 Torch/PyArrow/FAISS。
- 26 个可见 Pack 的统一属性门禁覆盖提示注入、缺证据失败关闭、PHI、人工复核/条件升级和中文临床输入。公共输出指令把用户病历、检索文本和工具结果内嵌的角色变更、输出格式、工具调用及泄密指令视为不可信数据。
- 旧响应缓存之外又完成一次强制真实刷新。门禁捕获并整改了 ICD 导航虚构 GFR 阈值、ICU 摘要补造静脉途径/改善推断、Code Validation 工具预算耗尽无最终 JSON，以及业务 `review_conclusion=FAIL` 被误判为运行失败的问题；逐项真实复跑后离线全量汇总为 **26/26**，最终组合回归提升为 **136 passed**。

### SDK 与部署候选门禁

- 便携式 .NET 8.0.424 安装在用户工具目录，不修改系统 PATH；net8.0 目标 9/9 测试通过，生成 `packages/icoder-dotnet/artifacts/fresh-beta2/iCoDer.Sdk.1.0.0-beta.2.nupkg` 与 `.snupkg`。包内仅包含 net8 SDK 二进制、XML 文档、README 与 NuGet 元数据；SHA-256 分别为 `5A6C306B72EA71B4F13BF5C72BCDEF95991BB3A7A219536186B6FEAB357215B0`、`D8C41FD7EFEFC8948A3BB12313FE98717CB39685B885142C57059C01B0CB8BDD`。
- 后端容器改为 `USER icoder` 非 root 运行，并只安装 `requirements-api.txt`。BGE/FAISS/Torch/Transformers 被移入显式可选的 `requirements-ml.txt`，不得进入默认 API 进程。新增部署候选静态预检，对本地 Compose 范围、健康依赖、原生 ML 隔离、密钥排除、TLS/安全头、区域驻留、中国合规声明、E2E fail-closed 和所有 region `enabled=false` 的诚实状态进行 18 项检查；报告位于 `reports/deployment/development_preflight_20260813/`。
- 云启动配置新增失败关闭：要求 HTTPS hosted URL、`APP_ENV=cloud`、PostgreSQL、HTTPS-only CORS、edge PHI 脱敏、cloud audit、空本地单租户 fallback、region-scoped asset bucket、KMS LLM 凭据、非 mock LLM、OAuth Tenant Header，以及 environment/region 一致。
- 当前机器没有 Docker CLI；因此没有构建/启动镜像，也没有执行 SBOM、镜像漏洞、签名、注册表、容量、灾备或真实云验证。静态 PASS 不得表述为生产部署完成。
- 前端生产构建将第三方依赖拆为约 259 kB vendor chunk，业务主包由约 710 kB 降至约 477 kB；清理无效的动态导入后构建零告警，82 项前端测试通过。Axios、React Router、Vite/Vitest 等依赖升级后完整 `npm audit` 为 0。
- JavaScript SDK `1.0.0-beta.4` TypeScript 新鲜构建通过；Python SDK 4/4 测试通过并生成 `icoder_sdk-1.0.0b3-py3-none-any.whl`（SHA-256 `3FBC8E044CE1FBB854AE13F281323B1926EEB1BB2B3CC574F8292F90C68BE848`）。
- FastAPI/Starlette 升级到兼容且无已知公告的组合，JWT 从 `python-jose/ecdsa` 迁移至 PyJWT；旧测试 monkey-patch 已移除。API、开发和可选 ML 清单的 `pip-audit` 报告均为 0，位于 `reports/security/`。迁移过程按独立进程串行覆盖 1716/1716 项；修复了一个被门禁捕获的 DeepSeek 降级原因审计信息丢失问题。
- OpenAPI 重新生成后为 219 paths / 255 operations；相较原文件新增 11 paths / 12 operations，删除为 0，随后 `--check` 通过。PR CI 已加入前后端依赖审计、三类 SDK 构建、OpenAPI 漂移和部署预检门禁。
- Docker E2E 的 local-only 前端改用独立 HTTP Nginx 配置，生产 `nginx.conf` 的 TLS 策略保持不变；健康等待超时后会明确失败并上传 Compose 日志。Nightly 后端 E2E 不再整批 `continue-on-error`，真实 LLM 用例只在无 Vault 密钥时按用例自身规则 skip。

### 已接近或已覆盖

- Agent Hub 卡片、运行入口、Agent Card、A2A Discovery 与统一调用；
- 人工复核、PHI 边界、Run Trace、租户边界与安全失败；
- JavaScript/Python/.NET 三类 SDK 的核心 Agent 能力；
- Environment/Tenant 的开发态控制面契约与中国区域声明；
- 中国 ICD-10-CN、ICD-9-CM-3、CDI、DRG/DIP 工作流基础。

### 仍未达到

- CDI 原始 40 例查询数量与 Corti 的差不超过 1 一致率为 0.60，低于 0.80 目标；平均绝对查询数差 1.18，高于 0.50 目标。Corti 自身也落在预期安全范围的 20 例子集达到 0.90/0.45，说明主要差距集中在 Corti 额外提出但安全性或必要性存疑的查询，不能机械复制。
- 当前 Agent `production_ready=false` 是诚实状态：开发态门禁通过不等于临床生产批准。
- 尚无真实云账号中的 CN/EU/US 区域开通、密钥托管、灾备切换、容量压测和生产监控证据。
- .NET SDK net8.0 已有本机编译/测试/打包证据；net10.0 尚缺相应 SDK/CI 新鲜验证。
- Corti 的真实商业租户配额、计费、区域故障切换和受限 API 能力不能仅凭开发环境模拟复刻。

## 仍需外部环境完成的上线门禁

- 真实医院 HIS/EMR/FHIR、医保平台互操作与验收；
- 中国脱敏病例上的独立 CDI、编码、临床专家双盲评审；
- 地方医保、DRG/DIP 规则包的授权、版本、地域隔离和回滚治理；
- 等保、个保法、数安法、网安法、医院制度、独立渗透测试与数据出境评估；
- 生产云账号、密钥托管、灾备演练、监控告警、容量压测和运营审批；
- 真实方言、多说话人、噪声和长音频验证；
- 有 .NET 10 SDK 的 CI/开发机执行 net10.0 `dotnet test`；有 Docker/Registry 的隔离 CI 构建、扫描、签名并启动镜像。

## Windows 稳定性

本阶段继续采用单进程、低内存串行测试，不加载 Torch/BGE/sentence-transformers/PyArrow，也不运行 Corti 浏览器自动化。除原有批次外，供应链/框架迁移又完成 1716/1716 项串行回归，08:30 后新增 Python 崩溃转储为 0。Minidump ExceptionStream 已确认：2026-08-13 的 `pyarrow\arrow.dll` 先发生写访问冲突（目标 `0x66F`），随后发生读空地址冲突（目标 `0x0`）；2026-08-10 的 `torch_cpu.dll` 为读访问冲突（目标 `0x2DC79A60`）。两种访问冲突都存在，没有证据归因于 Clash Verge。新增的 `assess_pyarrow_runtime_safety()` 不导入 DLL，仅通过包元数据将已证实不安全的 Windows `pyarrow 24.0.0` 默认失败关闭；其他版本不受该窄规则影响。
