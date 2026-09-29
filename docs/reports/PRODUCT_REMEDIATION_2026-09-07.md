# 产品审查整改与第二轮全面审查

## 结论与版本

原审查的可确定代码缺陷已完成一批实现并通过回归，第二轮全面审查已启动。当前仍是开发候选平台，不能认定完整Corti对等、权威中国医保业务或医院生产就绪。新增工程测试不能替代临床效果、正式隐私合同或医院验收。

原始基线与第二次查询的远程master均为 `b8357ba22b1035a3bbb7bcafb2d9cf4871b746c8`。本报告评估的是该基线加当前工作区修改；没有提交、推送或部署。原始审查报告保留不覆盖，避免把历史结果当作修复后证据。

## 原问题逐项处理

| 原项 | 已实现的改动 | 复核状态 / 剩余边界 |
|---|---|---|
| F01 未登录政策入口回跳 | 新增公开 `/privacy`、`/terms`，登录按钮指向公开页 | 未登录隐私说明页已实测与截图；公开的是当前数据/使用边界，正式运营政策仍需部署方批准 |
| F02 CDI按钮不可见 | CDI移除未定义mono色类，统一到现有深浅主题；输入增加可访问名称，输入栏适配窄屏 | 类型/构建通过；登录后深浅色与键盘浏览复核待授权 |
| F03 占位内容满分 | 占位句识别“未记录/未明确/待补/不详”等，保留“无过敏史”等合法否定 | 原七节样例不再PASS/满分；新增12项回归；仍是文档规则，不推断临床充分性 |
| F04 工作台readiness不一致 | CDI复用Hub经过校验的租户readiness合并；未就绪/读取失败禁用执行，提供模型配置和重新检查入口 | 3项组件交互测试通过，模型配置真实健康仍由后端检查；不伪造就绪 |
| F05 多轮语义 | 单轮任务入口明确输入范围，链接到多轮详情；详情按用户/组织/Agent保存Context引用并验证后恢复，支持新建对话 | 不在浏览器保存病历正文；退出清除引用；切换组织中止流、丢弃旧响应。跨浏览器历史正文恢复不在本实现范围 |
| F06 项目/Client误解 | 选择器明确“显示偏好”，不改变组织、授权或费用归属 | 保持后端组织/Agent/机器凭据授权模型，未制造虚假的项目隔离 |
| F07 启动文档过时 | 重写QUICKSTART，说明Python/Node依赖、3000/8000、双数据库变量、development seed、CORS和本地规则路径 | 复用已有依赖验证；未证明全新机器干净安装 |
| F08 部署/授权文档失真 | 云文档改为共享表organization_id+RLS；API_CLIENT_MODEL删除未实现ROPC流程及虚假scope示例，说明client_credentials与受控嵌入 | 地区、SLA与医院对接仍需目标环境验收 |
| F09 费用含义 | 聊天费用提示区分估算、开发账本和供应商账单 | 不新增未经授权的支付、发票或自动充值 |
| F10 测试身份偏差 | CDI真实JWT回归覆盖admin/coder/qc/clinician/insurance/dept_head的本租户读写与其他租户拒绝，另跑现有角色转换矩阵 | 这不是全API六角色笛卡尔积；全权限渗透和医院真实身份联邦仍未验证 |

额外修复：CDI前端补齐coder/dept_head到auditor映射；首页增加角色任务入口、默认编码页签，文书入口恢复指向真实文书工作台。

## 后端合同与恢复整改

1. **资产有效性**：原门禁只检查effective_from非空。现在解析真实日期，拒绝未生效/过期/无效日期，已声明日期的开发风险用途也拒绝过期资产；云与结算等严格用途要求目标地区精确匹配，缺失地区也拒绝。新增8项用例。没有将仓库字典标记为已授权。
2. **七阶段传递**：桥接器为各阶段传同一原文、SHA256版本、document_id和normalization；上游候选通过现有签名证明合同传递。解包统一Run响应，保留run/trace引用；失败不当成功输出，每阶段设置120秒上限。原文证据位置不依赖中间格式化提示词。
3. **阶段失败**：拒绝、超时及返回取消状态均形成stage_errors；汇总强制INCOMPLETE与人工复核、阻止AUTO_PASS。已有出院阶段阻断码保持兼容。7阶段×3失败模式及桥接用例已执行。真实提供商中途取消/多进程停止仍未验收，线程中的外部调用取消效果不能由这些用例推断。
4. **A2A恢复**：扩大测试发现SQLite下恢复查询对每个组织重复选择所有任务，错误组织可能先占调度槽。新增执行记录和ContextTaskRef显式organization_id过滤，保留PG RLS防线。多组织恢复专用回归与现有租约恢复测试通过。
5. **Memory范围**：仍保留最近100条有界检索，按创建时间与ID稳定排序；多取1条用于准确报告candidate_limit/candidates_scanned/candidates_truncated。101条测试明确老事实被排除时不能宣称全量召回。没有把扩大窗口伪装为完整语义索引。

## 第二轮全面审查矩阵

| 维度 | 本轮判断 | 验证范围 |
|---|---|---|
| Corti功能与方法 | 部分实现，不能等同临床质量 | Agent/Expert、五类Connector、Context、持久Memory扩展、A2A已形成工程合同；临床推理、语音与第三方效果仍缺同输入对比 |
| 中国本土化 | 界面和治理改善，权威资产仍受阻 | 中文占位语义改善；日期/地区门禁补齐；字典授权、官方DRG/DIP、地区规则及支付未闭合 |
| 架构 | 传递与恢复边界更明确 | 七阶段版本文档/证明透传、失败汇总和A2A恢复整改；超大模块及多事件循环桥接仍有维护成本 |
| UI与可访问性 | 已修代码，部分实测 | 公开页实测；CDI主题/标签/窄屏及readiness组件验证；登录后浏览、深浅色/键盘截图尚未完成 |
| UX | 入门、角色及费用语义改善 | 单轮/多轮、项目偏好、角色入口明确；医院任务分工仍需实际用户试点 |
| 安全与租户 | 专项回归通过，非完整认证 | 真实JWT六角色、跨组织、保留删除、Connector同意和恢复；localStorage凭据XSS暴露面仍存在，未贸然改变整个认证协议 |
| 可靠性 | 恢复缺陷关闭，生产证据不足 | 任务租约/事件和隔离SQLite回归通过；3项PG测试跳过，真实多worker/灾备/密钥轮换仍需环境 |
| 可观测性 | 错误和检索边界更可解释 | stage失败不显示完整成功；Memory截断明确；尚未取得医院生产报警和RTO/RPO证据 |
| 性能 | 增加可复现实验，不能外推容量 | 1/4/8线程各200次本地规则调用，P50/P95/P99留档；不含HTTP、PG、LLM和排队等待 |
| 部署与市场 | 开发定位保持 | 启动与授权文档修正；区域、采购、医院付费意愿、SLA及正式隐私合同不能自动证明 |

外部基准于本轮重新读取：[Corti Agentic概览](https://docs.corti.ai/agentic/overview)、[Corti Memory](https://docs.corti.ai/agentic/registry/memory)、[国家医保局DRG/DIP2.0](https://www.nhsa.gov.cn/art/2024/7/23/art_52_13319.html)。Corti v2仍列五类Connector和A2A1.0，Agent SDK仍标private preview；Memory connector仍只检索当前请求，跨会话持久化属应用层。未用厂商宣传数字为本产品评分。

## 本次执行证据

- 完整后端回归：**314通过、3跳过，22.31秒**；随后39项阶段合同和19项资产合同在最终小修后通过。按测试模块最新版本去重为**316通过、3跳过、0失败**，不把重复执行累加为新用例。
- 前端：**27个测试文件、181项通过**；TypeScript无错误，Vite构建成功。另有构建后的人工浏览检查尚待完成。
- 本地规则性能：600次预期结果一致；1/4/8线程P95约0.768/2.573/5.318毫秒，包含函数执行与事件循环创建，不包含请求排队。
- 数据环境：独立SQLite、合成输入、无外部模型调用。没有新增软件安装；前端node_modules是指向既有依赖的联接，不是干净安装验证。
- 登录后界面审查被自动审批阻断：已确认源码demo seed与本次development启动，审批仍要求用户明确授权管理员登录。等待该授权后才能完成CDI、角色主页和Context续接的浏览器验收；未将组件测试写成截图通过。

证据目录：`artifacts/product-review-2026-09-07/`，本轮文件均以`review2-`或`remediation-`区分；主要为review2-final.xml、review2-stage-final.xml、remediation-frontend-tests.log、review2-performance.json、remediation-privacy.png。

可点击证据：[最新用例计数及32个变更文件SHA256](<C:/Users/30805/.codex/worktrees/e237/iCoDer Agent/artifacts/product-review-2026-09-07/review2-evidence-summary.json>)、[后端完整JUnit](<C:/Users/30805/.codex/worktrees/e237/iCoDer Agent/artifacts/product-review-2026-09-07/review2-final.xml>)、[前端测试](<C:/Users/30805/.codex/worktrees/e237/iCoDer Agent/artifacts/product-review-2026-09-07/remediation-frontend-tests.log>)、[最终构建](<C:/Users/30805/.codex/worktrees/e237/iCoDer Agent/artifacts/product-review-2026-09-07/review2-build.log>)、[性能基线](<C:/Users/30805/.codex/worktrees/e237/iCoDer Agent/artifacts/product-review-2026-09-07/review2-performance.json>)、[公开隐私说明截图](<C:/Users/30805/.codex/worktrees/e237/iCoDer Agent/artifacts/product-review-2026-09-07/remediation-privacy.png>)、[公开使用说明截图](<C:/Users/30805/.codex/worktrees/e237/iCoDer Agent/artifacts/product-review-2026-09-07/remediation-terms.png>)。

## 不能自动关闭的验收事项

| 事项 | 已完成的可自动部分 | 仍需的外部输入 |
|---|---|---|
| 权威字典/规则 | 来源状态保留、完整性门禁、日期和地区硬拒绝 | 授权证明、正式版本/地区/生效期、独立编码专家审核 |
| 临床质量 | 合成规则回归与拒绝/失败合同 | 冻结用途/阈值、合法病例集、双人标注/仲裁、临床PI签署 |
| 生产基础设施 | 本地恢复、租户与保留删除回归 | PG16应用角色、多worker环境、真实密钥系统、备份与断网演练、RTO/RPO |
| 医院嵌入/支付 | 明确授权及模拟边界 | HIS/SSO/患者索引、合同、授权服务、真实支付与开票验收 |
| 全量Memory与容量 | 截断报告、101条召回边界测试、合成性能基线 | 冻结真实数据规模和召回目标、授权语义服务及目标容量环境 |
| 全面界面复核 | 公开页、构建和组件行为 | 本地演示管理员登录授权；随后继续深浅色/窄屏/键盘与会话续接验证 |

因此本轮不是“全部目标完成”的发布声明。可确定修复及回归已交付；依赖用户授权、业务资产或目标环境的验证仍明确开放。
