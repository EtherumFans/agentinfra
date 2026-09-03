# Corti × iCoDer 开发环境增量审计（2026-08-13）

## 本轮结论

本轮在不启用浏览器自动化、Torch、BGE 或 sentence-transformers 的条件下，完成了 CDI 复合 Query 的一次性安全重写闭环，并重新核验 Agent Hub 当前真实目录。

- 当前共有 32 个 Agent Pack。
- 26 个用户可见、非弃用 Pack 全部为 `executable`、`maturity=runnable`、`launch_candidate_ready=true`。
- 2 个非可执行 Pack（`cdi-review`、`documentation-gap`）是明确弃用、隐藏且声明替代 Agent 的迁移别名。
- 3 个非可执行 Pack（`index-navigator`、`code-reconciler`、`tabular-validator`）是隐藏的 MedCodER 内部流水线 Expert stage，不是 Agent Hub 产品入口；其执行类和 MedCodER 编排另有单元及 E2E 覆盖。
- 不存在用户可见但 metadata-only、stub 或不可执行的 Pack。
- 26 个用户可见 Agent 的 discovery → A2A URL 动态调用全部可到达；在离线模型条件下，每个端点只允许协议成功或明确安全失败，不存在 404、未注册路由或伪造临床成功。
- 所有 Pack 继续保持 `production_ready=false`；工程上线候选不替代医院、临床、法务、安全、认证和生产基础设施门禁。

## CDI 复合 Query 安全重写闭环

此前 `G8-CDI-GAP-004` 已识别严重程度与病因缺口，也生成了候选，但存活候选混合多个临床维度，被 single-dimension gate 正确留置后没有自动安全恢复路径。本轮新增 `query_dimension_rewrite` 内部子步骤：

1. 仅对本次 single-dimension gate 留置的 `NEEDS_CDI_REWRITE` 草稿触发。
2. 每次病例最多处理 8 个草稿，每个原草稿最多接受一个替代候选，不递归重试。
3. 替代候选必须保持原 `source_query_id` 与 `gap_id` 绑定，且临床维度必须与原文档缺口维度相交。
4. 每个 EvidenceSpan 仍需逐段锚定病历原文；禁止拼接不连续片段。
5. 替代候选必须重新通过 single-dimension、query eligibility 和 query necessity；之后继续进入 claim-evidence、semantic necessity 和 NLQ 门禁。
6. 模型异常、错误 gap、错误维度、重复 ID、无效证据、仍为复合问题或无安全结果时均 fail-closed，原草稿保留审计原因。
7. 原复合草稿不会成为可发送 Query；前端只向授权审计角色显示工作项，不提供直接发送操作。

该实现不是对冻结 `G8-CDI-GAP-004` 输出的事后改写。只有重新生成候选并经过相同冻结流程，才能更新对标指标。

## Agent Hub 共用输入安全边界

26 个用户可见 Agent 的 A2A 入口和统一 `/api/v1/agents/{id}/run` 入口现共用同一组高置信度提示注入检测规则。检测递归覆盖 TextPart、DataPart 与 metadata 字符串，在创建 Context、调用 Agent/模型/工具和写入运行记录之前执行。

- 覆盖英文指令层级覆盖、英文系统提示泄露、中文忽略既有指令、中文系统提示/规则泄露四类明确攻击模式。
- 仅返回稳定规则 ID 和通用错误文案，不在响应中回显攻击载荷。
- 正常临床语句中单独出现“系统”“提示”“规则”“忽略”等词不会因此被阻断。
- 这是应用层高置信度前置防线，不代表已经完成独立渗透测试、所有变体对抗测试或模型供应商侧防护验证。

## 本轮验证

| 验证范围 | 结果 |
|---|---:|
| CDI 复合重写、维度绑定、失败关闭与运行器提示契约 | 26 passed |
| CDI 全门禁组合（持久化、资格、必要性、单维度、断言证据、多 EvidenceSpan） | 114 passed |
| CDI API、A2A、隐私与 Hub 交叉回归 | 46 passed |
| Agent Pack 目录分类与注册状态 | 23 passed |
| 26 个用户可见 Agent discovery 与动态 A2A 路由 | 2 passed（覆盖 26/26 Agent） |
| A2A 输入安全、错误映射与端点回归 | 80 passed |
| 26 个用户可见 Agent 提示注入动态阻断 | 1 passed（逐个覆盖 26/26 Agent） |
| 统一 Agent Run API 阻断/正常中文输入回归 | 3 passed |
| CDI Agent Pack 完整性 | executable / launch candidate / 0 blockers |
| 前端 TypeScript 与生产构建 | passed |

前端仍有既存的 Vite 包体积及静态/动态导入警告，不是本轮类型或构建失败。所有后端测试均为独立、低内存、串行进程，未出现 Windows 访问冲突。

## Windows 崩溃证据与本轮隔离策略

Windows Application/WER 日志的只读核查显示，已观察到的故障不是单一类型：

- 2026-08-08 与 2026-08-10 的 `python.exe` 故障模块均为 `torch_cpu.dll`，异常代码为 `0xc0000005`；这能确认是原生访问冲突，但普通事件日志没有异常参数，无法可靠判定为读访问还是写访问。
- 2026-08-08 与 2026-08-09 的 `codex.exe` 记录为 `0xc0000409`，属于快速失败/安全检查终止，不是上述 `torch_cpu.dll` 的同一异常代码。
- 2026-08-12 的 `ChatGPT.exe` 记录为 `RADAR_PRE_LEAK_64` 内存泄漏预警；该记录本身不能证明它导致了访问冲突。

因此本轮继续禁止在 Codex 宿主进程链中加载 Torch/BGE/sentence-transformers，也不启动 Chromium 浏览器自动化。验证采用短生命周期、串行、低内存 Python 进程；Corti 控制台只保留人工登录会话，待宿主稳定性问题隔离后再恢复浏览器 E2E。Clash Verge 当前仅作为网络路径背景信息，没有证据将其认定为这些异常代码的根因。

## 对标指标仍未更新

冻结 40 例的原始全量结果保持不变：

| 指标 | 当前冻结值 | 目标 | 状态 |
|---|---:|---:|---:|
| 查询数差不超过 1 的一致率 | 0.75 | ≥ 0.80 | 未达标 |
| 平均绝对查询数差 | 1.00 | ≤ 0.50 | 未达标 |
| 明确缺口漏问率 | 0.10 | 0 | 未达标 |
| 无依据询问率 | 0.025 | 0 | 未达标 |

本轮实现使未来新生成候选具备恢复复合问题的安全路径，但不能倒推冻结输出已经改善。下一步应在隔离、稳定的模型环境中生成新的只读 40 例候选，逐例冻结、校验并与 Corti 基准比较；当前 Windows 原生环境继续禁止加载已知会触发 `0xc0000005` 的模型栈。

## 仍需外部完成的上线门禁

- 真实医院 HIS/EMR/FHIR/医保平台互操作与验收。
- 脱敏中国医院病例的独立 CDI、编码和临床专家标注及分层验证。
- 地方医保、DRG/DIP 规则包来源、版本、有效期、地域隔离和回滚治理。
- 中文方言、多说话人、噪声、长音频和专科术语的真实语音验证。
- 等保、个保法、数安法、网安法、医院制度及独立渗透测试。
- 生产云账号、密钥托管、灾备演练、监控告警、支付结算和数据许可。

因此当前结论仍是“开发环境工程上线候选”，不是 Corti 能力完全等价，也不是临床或生产批准。
