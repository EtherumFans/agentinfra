# Agent Hub 发布候选自动化阶段总结（2026-08-15）

> **声明**：本文记录开发环境的构建、契约与工件证据，不构成临床上线、Corti 临床等价或正式软件包发布声明。
> **日期**：2026-08-15
> **阶段**：Agent Hub release-candidate automation
> **状态**：DEVELOPMENT GATE PASSED；EXTERNAL RELEASE AND CLINICAL GATES OPEN

## 阶段结论

本阶段关闭了开发路线图中的发布自动化工程缺口：三种公共 SDK 现在必须使用同一规范化 beta 版本，JavaScript、Python、.NET、浏览器组件、Console、Agent Hub 运行矩阵、OpenAPI 和部署预检可由同一只构建工作流验证，最终工件生成 SHA-256 清单。工作流只有 `contents: read` 权限，不包含 npm、PyPI 或 NuGet 发布步骤，不会把“可打包”误报为“已上线”。

当前 26 个 Hub 可见 Agent 继续满足 executable、provider-resolvable、launch-candidate-ready 和完整输出合同门禁。该结论只证明工程入口和失败关闭边界，不证明其临床输出与 Corti 等价。

## 本阶段完成

1. 新增 `.github/workflows/release-candidate.yml`，由手动触发或 `rc-v*` 标签触发，包含版本合同、JavaScript SDK、Python SDK、.NET SDK、Embedded/Web、Console、平台门禁和工件汇总 8 个作业。
2. 新增 `scripts/release/validate_release_candidate.py`：
   - 读取 npm、PEP 440 和 NuGet 版本并统一规范化；
   - Python 包元数据与运行时 `__version__` 不一致时失败关闭；
   - 必需工件缺失时失败关闭；
   - `rc-v*` 标签与 SDK 元数据版本不一致时失败关闭；
   - 逐文件记录相对路径、字节数和 SHA-256；
   - 固定记录 `publication.performed=false`，不执行任何注册表写入。
3. JavaScript 与 .NET 保持 `1.0.0-beta.14`，Python 从 `1.0.0b13` 对齐为 `1.0.0b14`；PR CI 新增跨语言版本门禁，后续版本漂移会阻断合并。
4. Python `license` 元数据改为当前 SPDX 字符串格式，消除 setuptools 已声明的未来弃用警告。
5. `@icoder/web` 的 Unix 专用 `cp ... || true` 构建命令改为跨平台 Node 脚本，Windows 与 Linux 均通过同一构建入口复制静态资产。
6. 合并 `ReviewResponse` 重复的 Pydantic `model_config`，保留 `from_attributes=false` 与空受保护命名空间，消除 `model_used` 导入警告并增加回归测试。

## 验证证据

- 发布验证器：**5/5 passed**。
- JavaScript SDK：**21/21 passed**，`1.0.0-beta.14` tarball 成功。
- Python SDK：**29/29 passed**，`1.0.0b14` wheel 与 sdist 成功。
- Embedded `2.0.0` 与 Web `1.0.0-beta.1`：TypeScript 构建和 tarball 成功；Web 已在 Windows 使用新跨平台脚本实跑。
- Console：**114/114 passed**，TypeScript/Vite 生产构建成功并生成本地 bundle tarball。
- Agent Hub/部署安全组合：**52/52 passed**；Review/配置定向回归 **41/41 passed**，不再出现 Pydantic 警告。
- OpenAPI `--check`：通过。
- 运行矩阵：磁盘 Pack 32、Hub 可见 26、隐藏 6；可见 Agent **26/26** executable、provider-resolvable、launch-candidate-ready、contract-complete。
- 部署候选静态预检：通过，无失败检查。
- 本地清单 `reports/release-candidate/LOCAL_RELEASE_MANIFEST.json` 收录 6 个本机可构建工件及 SHA-256。由于本机没有 `dotnet`，没有伪造 NuGet 本地成功；net8.0/net10.0 测试、双框架资产和 NuGet/Symbol 包是 GitHub 发布候选工作流的阻断门禁。
- 工作流 YAML 可解析，`git diff --check` 无新增空白错误。

所有本阶段命令均删除 `ICODER_CREDENTIAL_LLM`、`DEEPSEEK_API_KEY`，固定 `LLM_PROVIDER=mock`、禁止外部 LLM 并禁用本机原生 MedCodER；未调用真实 LLM、ASR 或 Corti credits，8000/8011 未监听。

## 无密钥 E2E 的解释

隔离 mock 后端的 26-Agent HTTP E2E 报告位于 `reports/agent_hub/http_e2e_20260815_postfix_final/happy/agent_hub_examples_e2e.json`。其中规则型 Compliance Agent 通过 1 个，25 个依赖 LLM 的 Agent 返回明确 `llm_degraded`/provider unavailable。

这组结果是无密钥失败关闭证据，不是 26-Agent 能力成功率。真实 DeepSeek 的 Diagnosis、Medical Coding、Note Completeness 和 Code Validation 成功证据仍以 `AGENT_HUB_DEDICATED_A2A_REAL_LLM_PHASE_SUMMARY_2026-08-15.md` 中的最终运行记录为准；其余 Agent 仍需要新的安全临时凭证和统一去标识样本执行真实全量 E2E。

## 相对 Corti 的剩余差距

1. npm、PyPI、NuGet 尚未正式发布；组织所有权、命名空间、签名密钥、发布审批、撤回策略和支持承诺属于外部发布门禁。
2. 新工作流已写入并完成本地可执行部分验证，但尚未在 GitHub hosted runner 上产生一次完整 8-job 工件；尤其 .NET 8/10 和 NuGet 资产仍等待 CI 真实运行。
3. 当前清单提供 SHA-256 可审查性，但尚无 Sigstore/GitHub attestation、SBOM、注册表 provenance 或生产镜像签名；这些需要确定的供应链和生产权限。
4. 发布自动化不改变临床质量差距：仍缺同一去标识病例、同一目录版本、Corti/iCoDer 双边预测、独立盲评、严重错误率和医院编码员验收。
5. 真实托管云、PostgreSQL 多副本、KMS、对象存储、队列、灾备、容量/SLA、等保/隐私/法律和医院系统联调仍是外部门禁。
6. Windows 原生 Torch/FAISS/PyArrow 风险没有被发布工作流掩盖；本机继续禁用该栈，生产候选仍应使用隔离 Linux worker 并完成容器运行和故障注入。

## 凭证与后续动作

此前真实 LLM 测试已经完成，本阶段没有再次使用真实密钥。用户仍应在原 PowerShell 清除临时变量、关闭该窗口，并在 DeepSeek 控制台注销或轮换曾在对话中暴露的密钥。

下一步开发环境优先级是：在 GitHub runner 执行一次完整发布候选工作流；在有 Docker/Linux 的隔离环境验证 ML worker、SBOM 和镜像扫描；使用新临时凭证运行 26 happy + 26 adversarial + 两轮稳定性报告。之后才能进入同病例 Corti 双边临床质量比较。

## 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-15 | 新增发布候选工作流、跨语言版本门禁、SHA-256 清单、跨平台 Web 构建与阶段差距说明 | Agent Hub 上线候选与 Corti 对标持续收敛 |
