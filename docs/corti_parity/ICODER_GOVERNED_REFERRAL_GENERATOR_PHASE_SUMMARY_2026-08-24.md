# iCoDer Referral Generator 受治理本地能力阶段总结（2026-08-24）

## 阶段结论

`referral-gen` 已从外部模型模板收敛为可运行、可审计、可测试的本地开发上线候选切片：

- Agent：`icoder/referral-gen@1.1.0`
- Provider：`icoder.governed-referral.v1`
- 输出合同：`icoder/ReferralOutput/v3`（追加版本，旧版未覆盖）
- 执行：确定性规则引擎，不需要 LLM、网络、外部工具或知识库，成本为 0
- 安全：只装配明确标题下的逐字事实；禁止临床推断、新诊断、新治疗和外部知识；人工复核、生产发送与写回始终被阻断

本阶段证明的是合成、明确标题输入下的开发能力，不证明完整 Corti Referral Generator 复刻、自由叙事临床质量、医院接入或生产上线。严格 26-Agent live-provider 语义验证和 production-ready 验证仍为 0/26。

机器证据见 [`phase_evidence.json`](../../reports/agent_hub/local_semantic_e2e_referral_phase_20260824/phase_evidence.json)，真实本地 HTTP 证据见 [`local_semantic_e2e_referral_phase_20260824`](../../reports/agent_hub/local_semantic_e2e_referral_phase_20260824/)，部署预检见 [`development_preflight_referral_phase_20260824`](../../reports/deployment/development_preflight_referral_phase_20260824/)。

## 本轮实现

### 受治理转诊草案

Provider 只识别输入中明确标注的中英文转诊字段，并保留脱敏文本的精确字符 span。核心字段包括患者姓名、出生日期、病案号、转出医生、接收专科、转诊原因、紧急度、期望时限和请求动作；支持材料包括主诉/当前问题、药物、过敏和检查结果。

状态机固定为：

- 任一核心字段缺失：`INPUT_REQUIRED`，不生成转诊信；
- 核心字段齐全但支持材料缺失：`PARTIAL`，草案对缺失项明确写“未记录”；
- 核心和支持材料齐全：`READY_FOR_REVIEW`；
- 所有状态均要求人工复核，禁止自动发送和写回。

输入上限为 40,000 字符，证据项上限为 160；不可信边界和 canary 内容被截断。姓名、病案号等经过统一 PHI 脱敏后仍可作为“已提供但已脱敏”的证据使用，原始 PHI 不进入报告。

### 中国场景适配

- 双向转诊方向；
- 转出/接收机构与科室；
- 中文常见字段标题；
- 区域转诊平台发送、HIS/EMR 写回默认阻断；
- 无区域政策、医院目录或接诊能力数据时不猜测目标机构、专科或时限。

### Runtime、合同和审计闭环

- Provider 已进入统一 Provider Registry、Run/A2A 路由、结构化投影和 Trace；
- v3 合同具有 26 个必需字段、递归 field schema、7 条字段关系和 1 条证据绑定；
- 合同注册表现为 26/26 可见 Agent 已登记、120 个追加版本，无漂移、无无效或重复引用；
- schema 生成器 dry-run 为 26 个可见 Agent、`changed_agents=[]`；
- Corti 20-Agent 映射门禁恢复为 catalog/development/China profile 各 20/20；
- 宽回归发现并修复审计主键以“上下文 + 当前时间”生成导致的 Windows 同时钟碰撞，普通审计写入现使用独立 UUIDv4，显式导入/回放 ID 保持兼容。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| 聚焦 Provider/投影/合同测试 | 141/141 |
| Referral A2A | 2/2 |
| 26-Agent 离线安全 E2E | 78/78 |
| 本地真实 HTTP happy / adversarial / reference | 16/16 / 16/16 / 16/16 |
| 三轮稳定性 | 96/96，fresh=96，seeded=0 |
| 字段关系对抗回放 | 184/184（18 Agent、74 条关系） |
| 证据绑定对抗回放 | 42/42（12 Agent、21 条绑定） |
| 更宽相关回归 | 1108 passed、5 skipped、6 deselected、0 failed；798.89 秒 |
| Corti 20-Agent 开发映射 | 20/20 |
| 静态部署预检 | 90/90；11 项外部限制保留 |

本轮宽回归比上一阶段 822 项更宽，覆盖后端 Provider、Runtime、Corti parity、整个 `integration/icoder` 和 Agent Run API。测试在 C 盘隔离 SQLite 上串行运行，未使用真实 LLM、外部网络、FAISS/BGE 或可见 Uvicorn，未观察到内存访问冲突。

当前运行矩阵：26 个用户可见 Agent 全部具备可解析 Provider 和开发候选结构；10 个仍强依赖外部模型，1 个具有可选外部增强，15 个纯本地，16 个具备离线本地基线，16 个已通过隔离本地语义 HTTP 门禁。

## 与 Corti 当前公开 Referral Generator 的逐项差距

公开对照以 Corti 的 [Referral Generator Agent](https://www.corti.ai/agents/referral-generator-agent)、[Agent Library](https://corti.ai/agents)、[标准 Textgen 模板](https://docs.corti.ai/textgen/templates-standard) 和 [Text Generation](https://corti.ai/text-generation) 为准。公开页面要求单次患者接触中的转诊原因、接收医生/专科、转出医生、患者标识、紧急度与时限，生成专业医师间转诊信；缺失信息必须显式标记，且不得新增诊断、治疗或推断意图。

| 能力 | iCoDer 本阶段 | 对 Corti 的结论 |
|---|---|---|
| 必填信息检查 | 核心字段逐项检查，缺失即 `INPUT_REQUIRED` 且不出信 | 开发合同已覆盖 |
| 缺失信息诚实表达 | 支持材料缺失进入 `PARTIAL` 并写“未记录” | 开发合同已覆盖 |
| 不新增诊断/治疗/意图 | 常量约束、投影强制、对抗测试和关系门禁 | 开发合同已覆盖，但尚无独立临床金标准 |
| 医师间转诊信 | 固定模板逐字装配 | 仅部分覆盖；不是生成式专业文本质量等价 |
| 自由叙事理解与综合 | 只接受明确标题字段 | 未覆盖 |
| 临床相关性筛选与冲突处理 | 不做临床相关性判断；重复/矛盾内容依赖人工复核 | 未覆盖 |
| 多文档病历综合 | 无 EHR/文档集合/时间线综合 | 未覆盖 |
| 专科和机构模板 | 无专科模板、医院目录、接诊能力或当地规则 | 未覆盖 |
| 闭环转诊 | 发送和写回固定阻断 | 无区域平台投递、回执、拒收、改派和闭环追踪 |
| 真实质量 | 仅 Pack 自有合成样例 | 无医生盲评、遗漏率、严重错误率或 Corti 同例对照 |

因此，当前可以诚实声称“Referral Generator 的显式字段、缺失门禁、不推断和中国双向转诊草案已成为开发候选基线”，不能声称“已复刻 Corti 的自由叙事生成质量”或“已可在医院生产发送”。

## 尚未收敛的 10 个外部模型 Agent

`claim-check`、`clinical-documentation-improvement-agent`、`clinical-education`、`clinical-guidelines`、`denial-appeals`、`drg-analyzer`、`medical-coding-agent`、`principal-diagnosis-review`、`prior-auth`、`triage`。

这些 Agent 不能仅通过把 LLM 替换成关键词规则就宣称 Corti 等价。下一开发阶段应优先将 `prior-auth` 收敛为“明确材料和政策引用的受治理证据装配基线”，在没有合法、版本固定的医保/商保政策时必须输出政策不可用并阻断提交；实时 payer/医保平台、授权政策库、医院工作流和独立审核继续作为外部门禁。

## 环境与不可突破门禁

E 盘测试前仅余 0.66 MiB。35 个未被 Git 跟踪且名称明确为测试数据库的文件被移动到 `C:\Users\huawei\AppData\Local\Temp\icoder-disposable-test-dbs-20260824-referral-cleanup\`，共 68,247,552 bytes；没有删除文件。受保护数据库仍为 8,536,064 bytes、SHA-256 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`、修订 `041`，源码迁移头为 `056`。

以下门禁仍必须由外部证据关闭：真实医院数据与接口、区域转诊平台、授权政策/知识资产、真实云和 PostgreSQL 多副本、容量/灾备/可用性、法务与数据合规、医疗器械/安全认证、独立临床 reviewer、医院模板及工作流验收。

