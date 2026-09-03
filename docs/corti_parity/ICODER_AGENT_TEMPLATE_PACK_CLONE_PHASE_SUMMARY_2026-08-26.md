# iCoDer Agent 模板 Pack/Clone 单一真源阶段总结（2026-08-26）

## 阶段结论

本阶段关闭了 Agent Hub 与“新建 Agent → 使用模板”之间的用户面语义漂移。模板目录现在由与 Hub 完全相同的可见 launch-candidate Pack 边界动态投影：**26 个受治理模板与 Hub 26 个运行 ID 完全一致**，另保留 2 个明确不含医疗能力的通用空白模板。六个旧别名和 20 份失效的手工医疗提示词已从模板源码移除。

受治理模板创建不再调用通用 Agent `create`。前端改为调用幂等的 Agent Hub Clone，使项目 Agent 保留 `source_agent_ref`、源 Runtime 身份、权限、输出合同、非目标、Expert 图和审计归属；只有 `translator-blank` 与 `summarizer-blank` 继续走通用创建路径。旧 REST Clone 如果收到受治理模板 ID，会以 409 失败关闭并返回正确的 Hub Clone 地址，不再静默生成无法代表源 Pack 的普通草稿。

这使 iCoDer 与 2026-08-26 Corti Console 中“Pre-built Agent → Customize agent”的用户路径更接近，但不等于已验证 Corti 私有定制语义或临床输出等价。

## 修复前的可复现问题

- Agent Hub 发布 26 个可见 launch candidates；旧模板接口只有 22 项。
- 12 个当前 Hub ID 不在模板目录：`claim-check`、`clinical-documentation-improvement-agent`、`clinical-education`、`code-validation-agent`、`compliance-guardrail-agent`、`discharge-summary-structuring`、`drg-analyzer`、`evidence-extractor`、`evidence-ranker`、`medical-coding-agent`、`note-completeness-agent`、`principal-diagnosis-review`。
- 模板目录仍暴露 6 个旧 ID：`cdi`、`clinical-edu`、`code-validation`、`compliance-guardrail`、`medical-coding`、`note-completeness`。
- 手工模板提示词会承诺最终分诊、自动编码、最新指南检索、自动登记等超出对应受治理 Runtime 的能力。
- `NewAgentPage` 将模板内容直接提交到通用创建接口，无法继承源 Pack 的运行身份、权限、合同和完整性绑定。

## 实现

### 后端模板投影

- `icoder_agents_hub.py` 提供公共 `load_visible_launch_candidate_packs()`，统一 Hub、租户 readiness、Clone 和模板目录的发布边界。
- `agents.py` 的模板目录从权威 Pack 动态生成，受治理模板包含 canonical `runtime_agent_id`、`source_agent_ref`、版本、人工复核状态、非目标和 Hub Clone 地址。
- 受治理模板下载返回原始 canonical Pack，并剔除 Hub 运行时注入的私有投影字段；通用空白模板继续由通用 Pack 生成器导出。
- 旧 REST Clone 对受治理模板失败关闭，避免生成丢失来源合同的伪 Clone。

### 前端创建路径

- `NewAgentPage` 按 `template_kind` 分流。
- `governed_prebuilt` 调用 `agentHubApi.clone()`，并使用服务端返回的 `customize_url` / `project_agent_id` 导航。
- `generic_blank` 保持通用创建能力，不被错误绑定到医疗 Runtime 或 Expert。

### 部署门禁

静态部署预检新增 `agent_template_catalog_is_pack_mastered_and_clone_safe`，动态验证：

- 模板总数 28；
- governed 26/26 与 Hub 完全相等；
- generic 精确为 2 项；
- 每个 governed 模板都绑定 Hub Clone transport、canonical Runtime ID 和 `source_agent_ref`；
- 前端存在治理模板 Clone 分支和对应合同测试。

## 验证证据

- 后端模板/Hub/Clone/项目 Runtime/通用 Agent 聚焦回归：**55/55**；在移除旧医疗模板正文后的最终重跑子集为 **46/46**。
- 全部 26 个可见 Agent 离线安全 E2E：**78/78**。
- 前端完整 Vitest：**144/144**。
- 前端 TypeScript + Vite 生产构建：通过（仅保留既有动态/静态 import chunk 提示）。
- 部署预检 [`deployment_preflight.json`](../../reports/deployment/agent_template_pack_clone_phase_20260826_v1/deployment_preflight.json)：**102/102**，SHA-256 `d8b116c1402bffb24b63c46a675ac5ad46daced29c410d2223f6c0ab2d89cfbe`。
- 目录事实复核：`catalog_total=28`、`governed=26`、`generic=2`、`hub=26`、`missing=[]`、`extra=[]`、`stale_aliases=[]`。
- 受保护数据库保持不变：8,536,064 bytes，最后写入 `2026-08-22 17:16:22`，SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。

## 仍开放的差距

- 本阶段证明的是模板目录、Clone、Runtime 来源和安全合同一致，不是 26 个 Agent 的临床质量等价。
- 没有在 Corti 创建或运行 Agent，因此 Corti 的 prompt 组合、上下文注入、工具权限、版本、发布和状态迁移语义仍未做 side-by-side 验证。
- 真实 Provider 的最新源级 26-Agent 回归继续有效，但 wrapper 顶层终态限制不因本阶段改变。
- 50 次 CDI/Medical Coding 独立校准、同病例 Corti 盲评、真实医院数据、权威目录许可、生产容量、法务/合规与医院验收仍为开放门禁。

